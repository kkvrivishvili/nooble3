"""
Routes for the Agent Service.
"""

from fastapi import APIRouter

from .agents import router as agents_router
from .health import router as health_router
from .internal import router as internal_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(internal_router, prefix="/internal", tags=["internal"])

__all__ = ["api_router"]
