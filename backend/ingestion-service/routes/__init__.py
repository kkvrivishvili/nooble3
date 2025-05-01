"""
Registro de rutas para el servicio de ingesta.
"""

from fastapi import FastAPI
import logging

from .ingestion import router as ingestion_router
from .documents import router as documents_router
from .health import router as health_router
from .jobs import router as jobs_router
from .collections import router as collections_router

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI):
    """Registra todas las rutas en la aplicación FastAPI."""
    app.include_router(ingestion_router, tags=["Ingestion"])
    app.include_router(documents_router, tags=["Documents"])
    app.include_router(collections_router, tags=["Collections"])
    app.include_router(jobs_router, tags=["Jobs"])
    app.include_router(health_router, tags=["Health"])