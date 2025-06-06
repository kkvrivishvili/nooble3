"""
Punto de entrada del Agent Orchestrator Service refactorizado con Domain Actions.
"""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.helpers.health import register_health_routes
from config.settings import get_settings
from queue.action_worker import ActionWorker
from services.websocket_manager import WebSocketManager

settings = get_settings()
logger = logging.getLogger(__name__)

# Componentes globales
action_worker = None
websocket_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    global action_worker, websocket_manager
    
    logger.info("Iniciando Agent Orchestrator Service con Domain Actions")
    
    # Inicializar componentes
    action_worker = ActionWorker()
    websocket_manager = WebSocketManager()
    
    # Iniciar worker de acciones en background
    worker_task = asyncio.create_task(action_worker.start())
    
    # Iniciar limpieza periódica de WebSocket connections
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    try:
        yield
    finally:
        logger.info("Deteniendo Agent Orchestrator Service")
        
        # Detener worker
        if action_worker:
            await action_worker.stop()
        
        # Cancelar tareas background
        worker_task.cancel()
        cleanup_task.cancel()
        
        try:
            await asyncio.gather(worker_task, cleanup_task, return_exceptions=True)
        except:
            pass

async def periodic_cleanup():
    """Limpieza periódica de conexiones WebSocket obsoletas."""
    global websocket_manager
    
    while True:
        try:
            await asyncio.sleep(60)  # Cada minuto
            if websocket_manager:
                await websocket_manager.cleanup_stale_connections()
        except Exception as e:
            logger.error(f"Error en limpieza periódica: {str(e)}")

# Crear aplicación
app = FastAPI(
    title="Agent Orchestrator Service",
    description="API Gateway + WebSocket Manager + Domain Actions Processor",
    version=settings.service_version,
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar manejo de errores
setup_error_handling(app)

# Registrar rutas
from routes.chat import router as chat_router
from routes.websocket import router as websocket_router

app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(websocket_router, tags=["WebSocket"])

# Registrar health checks estándar
register_health_routes(app)

# Configurar logging
init_logging(settings.log_level, service_name="agent-orchestrator-service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8008, 
        reload=True,
        log_level="info"
    )