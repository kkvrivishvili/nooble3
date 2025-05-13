import logging
import time

from fastapi import FastAPI
from .agents import router as agents_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .admin import router as admin_router
from .public import router as public_router

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI):
    """Registra todas las rutas en la aplicación FastAPI."""
    app.include_router(agents_router, prefix="/agents", tags=["Agents"])
    app.include_router(chat_router, tags=["Chat"])
    app.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
    app.include_router(admin_router, prefix="/admin", tags=["Admin"])
    app.include_router(public_router, tags=["Public"])
    
    # Endpoints de verificación de salud movidos a routes/health.py
    from .health import router as health_router
    app.include_router(health_router, tags=["Health"])