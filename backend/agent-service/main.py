"""
Punto de entrada principal para el servicio de agentes.

Este módulo inicializa la aplicación FastAPI, registra las rutas,
y configura los middleware necesarios.
"""

import logging
import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from common.context import get_context, set_context
from common.config import setup_logging

from config import get_settings
from services import LangChainAgentService, ServiceRegistry
from routes import agents_router, health_router, internal_router

# Configurar logging
setup_logging()
logger = logging.getLogger(__name__)

# Obtener configuraciones
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación.
    
    Args:
        app: Aplicación FastAPI
    """
    # Inicializar servicios
    logger.info("Inicializando servicios...")
    agent_service = LangChainAgentService()
    await agent_service.initialize()
    
    # Registrar servicios en el estado de la aplicación
    app.state.agent_service = agent_service
    app.state.service_registry = ServiceRegistry()
    
    # Informar inicialización completa
    logger.info(f"Servicio de agentes inicializado y listo en {settings.port}")
    
    yield
    
    # Limpieza al finalizar
    logger.info("Cerrando servicios...")


# Crear aplicación
app = FastAPI(
    title="Agent Service",
    description="Servicio para la gestión de agentes inteligentes",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar los orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def context_middleware(request: Request, call_next):
    """
    Middleware para propagar el contexto a través de las solicitudes.
    
    Args:
        request: Solicitud HTTP
        call_next: Siguiente middleware o endpoint
        
    Returns:
        Response: Respuesta HTTP
    """
    # Extraer IDs de contexto de los headers
    tenant_id = request.headers.get("x-tenant-id")
    agent_id = request.headers.get("x-agent-id")
    conversation_id = request.headers.get("x-conversation-id")
    
    # Establecer contexto
    if tenant_id or agent_id or conversation_id:
        context = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "conversation_id": conversation_id
        }
        set_context(context)
    
    # Medir tiempo de respuesta
    start_time = time.time()
    
    # Procesar la solicitud
    response = await call_next(request)
    
    # Calcular tiempo de respuesta
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# Obtener instancia del servicio de agentes
def get_agent_service():
    """Obtiene la instancia del servicio de agentes."""
    return app.state.agent_service


def get_service_registry():
    """Obtiene la instancia del registro de servicios."""
    return app.state.service_registry


# Incluir rutas
app.include_router(
    health_router,
    prefix="/health",
    tags=["health"]
)

app.include_router(
    agents_router,
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(get_agent_service)]
)

app.include_router(
    internal_router,
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(get_agent_service)]
)


# Para desarrollo local
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
