"""
Registro de rutas para el servicio de embeddings.
"""

from fastapi import FastAPI
import logging

from .embeddings import router as embeddings_router
from .models import router as models_router
from .health import router as health_router

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI):
    """Registra todas las rutas en la aplicación FastAPI."""
    app.include_router(embeddings_router, tags=["Embeddings"])
    app.include_router(models_router, tags=["Models"])
    app.include_router(health_router, tags=["Health"])