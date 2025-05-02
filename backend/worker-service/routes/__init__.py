"""
Rutas y endpoints del worker-service.
"""

from fastapi import FastAPI

from .health import health_router

def register_routes(app: FastAPI):
    """Registra todos los routers en la aplicación FastAPI."""
    app.include_router(health_router, tags=["Health"])
