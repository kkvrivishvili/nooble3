"""
Health and status endpoints for the Agent Service.
"""

import logging
import time
from typing import Dict, List, Optional, Any
import os

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from common.context import with_context
from common.errors import handle_errors
from common.utils.http import call_service
from common.cache import CacheManager
from common.db import get_supabase_client
from config import get_settings

# Importaciones para verificar proveedores LLM
import openai
import httpx
try:
    import groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter()


class ServiceStatus(BaseModel):
    """Status information for a dependent service."""
    name: str
    status: str
    latency_ms: float
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Response model for health endpoints."""
    status: str
    version: str
    timestamp: float
    uptime: float
    dependencies: Optional[List[ServiceStatus]] = None


START_TIME = time.time()


@router.get("/health", response_model=HealthResponse)
@handle_errors(error_type="simple", log_traceback=False)
async def health():
    """
    Basic health check endpoint.
    Returns a simple health status without checking dependencies.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.version,
        timestamp=time.time(),
        uptime=time.time() - START_TIME
    )


@router.get("/status", response_model=HealthResponse)
@with_context(tenant=True, validate_tenant=False)
@handle_errors(error_type="service", log_traceback=True)
async def status(request: Request, ctx=None):
    """
    Detailed status endpoint that checks all service dependencies.
    Verifies database connectivity, cache availability, and dependent services.
    """
    settings = get_settings()
    dependencies = []
    overall_status = "ok"
    
    # Check Supabase connection
    db_start = time.time()
    try:
        supabase = get_supabase_client()
        # Simple query to test connection
        result = await supabase.table("agents").select("count(*)", count="exact").limit(1).execute()
        dependencies.append(ServiceStatus(
            name="supabase",
            status="ok",
            latency_ms=round((time.time() - db_start) * 1000, 2)
        ))
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        dependencies.append(ServiceStatus(
            name="supabase",
            status="error",
            latency_ms=round((time.time() - db_start) * 1000, 2),
            details={"error": str(e)}
        ))
        overall_status = "degraded"
    
    # Check Redis cache
    cache_start = time.time()
    try:
        # Test cache connection
        test_key = "health_check_test"
        await CacheManager.set(
            data_type="health",
            resource_id=test_key,
            value={"status": "ok"},
            ttl=60
        )
        await CacheManager.get(data_type="health", resource_id=test_key)
        await CacheManager.delete(data_type="health", resource_id=test_key)
        
        dependencies.append(ServiceStatus(
            name="redis",
            status="ok",
            latency_ms=round((time.time() - cache_start) * 1000, 2)
        ))
    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}")
        dependencies.append(ServiceStatus(
            name="redis",
            status="error",
            latency_ms=round((time.time() - cache_start) * 1000, 2),
            details={"error": str(e)}
        ))
        overall_status = "degraded"
    
    # Check Query Service
    query_start = time.time()
    try:
        query_service_url = settings.query_service_url
        query_health = await call_service(
            f"{query_service_url}/health",
            method="GET",
            operation_type="health_check"
        )
        dependencies.append(ServiceStatus(
            name="query_service",
            status="ok" if query_health.get("status") == "ok" else "error",
            latency_ms=round((time.time() - query_start) * 1000, 2)
        ))
    except Exception as e:
        logger.error(f"Query service health check failed: {str(e)}")
        dependencies.append(ServiceStatus(
            name="query_service",
            status="error",
            latency_ms=round((time.time() - query_start) * 1000, 2),
            details={"error": str(e)}
        ))
        overall_status = "degraded"
    
    # Check Embedding Service
    embedding_start = time.time()
    try:
        embedding_service_url = settings.embedding_service_url
        embedding_health = await call_service(
            f"{embedding_service_url}/health",
            method="GET",
            operation_type="health_check"
        )
        dependencies.append(ServiceStatus(
            name="embedding_service",
            status="ok" if embedding_health.get("status") == "ok" else "error",
            latency_ms=round((time.time() - embedding_start) * 1000, 2)
        ))
    except Exception as e:
        logger.error(f"Embedding service health check failed: {str(e)}")
        dependencies.append(ServiceStatus(
            name="embedding_service",
            status="error",
            latency_ms=round((time.time() - embedding_start) * 1000, 2),
            details={"error": str(e)}
        ))
        overall_status = "degraded"
    
    # Check LLM Provider APIs
    # OpenAI
    openai_start = time.time()
    openai_status = "unknown"
    openai_error = None
    if settings.openai_api_key:
        try:
            client = openai.OpenAI(api_key=settings.openai_api_key)
            models = client.models.list(limit=1)
            if models:
                openai_status = "ok"
        except Exception as e:
            openai_status = "error"
            openai_error = str(e)
            logger.warning(f"OpenAI health check failed: {openai_error}")
    else:
        openai_status = "disabled"
    
    dependencies.append(ServiceStatus(
        name="openai_provider",
        status=openai_status,
        latency_ms=round((time.time() - openai_start) * 1000, 2),
        details={"error": openai_error} if openai_error else None
    ))
    
    # Groq
    groq_start = time.time()
    groq_status = "unknown"
    groq_error = None
    if GROQ_AVAILABLE and settings.groq_api_key:
        try:
            # Verificar la conexión a Groq
            groq_client = groq.Groq(api_key=settings.groq_api_key)
            models = groq_client.models.list()
            if models:
                groq_status = "ok"
        except Exception as e:
            groq_status = "error"
            groq_error = str(e)
            logger.warning(f"Groq health check failed: {groq_error}")
    else:
        groq_status = "disabled"
    
    dependencies.append(ServiceStatus(
        name="groq_provider",
        status=groq_status,
        latency_ms=round((time.time() - groq_start) * 1000, 2),
        details={"error": groq_error} if groq_error else None
    ))
    
    # Ollama ha sido eliminado de los proveedores soportados
    
    # Return status with all dependency checks
    response = HealthResponse(
        status=overall_status,
        version=settings.version,
        timestamp=time.time(),
        uptime=time.time() - START_TIME,
        dependencies=dependencies
    )
    
    # Set appropriate status code
    if overall_status != "ok":
        return Response(
            content=response.json(),
            media_type="application/json",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    return response
