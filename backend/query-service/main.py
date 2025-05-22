"""
Query Service - Punto de entrada.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.db.supabase import init_supabase
from common.helpers.health import register_health_routes
from config.settings import get_settings

settings = get_settings()
logger = logging.getLogger("query-service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación."""
    logger.info("Iniciando Query Service")
    await init_supabase()
    yield
    logger.info("Query Service detenido")

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Query Service",
    description="Servicio RAG para búsqueda y generación de respuestas",
    version=settings.service_version,
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handling
setup_error_handling(app)

# Rutas
from routes.collections import router as collections_router
from routes.internal import router as internal_router

app.include_router(collections_router, prefix="/api/v1/collections", tags=["Collections"])
app.include_router(internal_router, prefix="/api/v1", tags=["Internal"])

# Health checks estándar
register_health_routes(app)

# Logging
init_logging(settings.log_level, service_name="query-service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)