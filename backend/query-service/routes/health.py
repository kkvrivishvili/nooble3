"""
Endpoints para verificación de salud y estado del servicio.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma, proporcionando
endpoints consistentes para verificación de liveness y estado detallado.
"""

import time
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.config import get_settings
from common.utils.http import check_service_health
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Variable global para registrar el inicio del servicio
service_start_time = time.time()

@router.get(
    "/health",
    response_model=None,
    summary="Estado básico del servicio",
    description="Verificación rápida de disponibilidad del servicio (liveness check)"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio (liveness check).
    
    Este endpoint proporciona información sobre la disponibilidad básica del servicio
    y sus componentes esenciales como caché y base de datos. Es ideal para
    health checks de Kubernetes y sistemas de monitoreo.
    
    Returns:
        HealthResponse: Estado básico del servicio
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar el servicio de embeddings (específico de este servicio)
    embedding_service_status = await check_embedding_service()
    components["embedding_service"] = "available" if embedding_service_status else "unavailable"
    
    # Generar respuesta estandarizada usando el helper común
    return get_service_health(
        components=components,
        service_version=settings.service_version
    )

@router.get(
    "/status",
    response_model=None,
    summary="Estado detallado del servicio",
    description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene el estado detallado del servicio con métricas adicionales.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado de componentes críticos (cache, DB)
    - Estado de servicios dependientes (embedding-service)
    - Versión y entorno de ejecución
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio
    """
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="query-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "embedding_service": check_embedding_service_status
        },
        # Métricas adicionales específicas del servicio
        extra_metrics={
            "vector_databases": ["pinecone", "supabase", "redis"],
            "supported_query_types": ["similarity", "hybrid", "mmr"]
        }
    )


async def check_embedding_service() -> bool:
    """
    Verifica la disponibilidad del servicio de embeddings usando la función común.
    
    Returns:
        bool: True si el servicio está disponible, False en caso contrario
    """
    return await check_service_health(
        service_url=settings.embedding_service_url, 
        service_name="embedding-service"
    )

async def check_embedding_service_status() -> str:
    """
    Verifica el estado del servicio de embeddings y devuelve el estado en formato
    compatible con el helper detailed_status_check.
    
    Returns:
        str: Estado del servicio ("available" o "unavailable")
    """
    is_available = await check_embedding_service()
    return "available" if is_available else "unavailable"