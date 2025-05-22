"""
Módulo de rutas para el Query Service.

Contiene los endpoints API del servicio refactorizado:
- Endpoints internos para procesamiento RAG
- Endpoints para operaciones sobre colecciones
"""

from .internal import router as internal_router
from .collections import router as collections_router

__all__ = [
    "internal_router",
    "collections_router"
]
