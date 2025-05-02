"""
Worker Service para tareas programadas y procesamiento en segundo plano.

Este servicio gestiona:
1. Tareas programadas de reconciliación de tokens
2. Procesamiento asíncrono de trabajos largos
3. Sincronización entre sistemas
"""

import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings
from common.utils.logging import init_logging
from services.scheduler import initialize_scheduler
from routes import register_routes
from routes.health import set_scheduler

# Configuración
settings = get_settings()
logger = logging.getLogger("worker_service")
init_logging(settings.log_level, service_name="worker-service")

# Variables globales para mantener referencias a recursos
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación, inicializando 
    y cerrando recursos como el scheduler.
    """
    global scheduler
    
    # Inicializar recursos al arrancar
    logger.info("Iniciando Worker Service")
    scheduler = await initialize_scheduler()
    
    # Establecer referencia al scheduler para health checks
    set_scheduler(scheduler)
    
    yield
    
    # Liberar recursos al cerrar
    logger.info("Cerrando Worker Service")
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler detenido correctamente")

# Inicializar FastAPI
app = FastAPI(
    title="Worker Service",
    description="Servicio para tareas programadas y procesamiento en segundo plano",
    version="1.0.0",
    lifespan=lifespan
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar las rutas
register_routes(app)

# Punto de entrada principal
if __name__ == "__main__":
    import uvicorn
    
    # Obtener configuración
    port = int(os.environ.get("PORT", 8080))
    
    # Iniciar servidor
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.debug_mode
    )
