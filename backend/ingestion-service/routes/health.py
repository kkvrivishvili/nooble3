"""
Endpoints para verificación de salud y estado del servicio de ingestión.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma. El endpoint /health
proporciona una verificación rápida de disponibilidad, mientras que
/status ofrece información detallada sobre el estado del servicio.
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

# Variable global para registrar el inicio del servicio (para cálculo de uptime)
service_start_time = time.time()

@router.get("/health", 
           response_model=None,
           summary="Estado básico del servicio",
           description="Verificación rápida de disponibilidad del servicio (liveness check)")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio de ingestión (liveness check).
    
    Este endpoint permite verificar rápidamente si el servicio está operativo.
    Ideal para health checks de Kubernetes y sistemas de monitoreo.
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar el servicio de embeddings (específico de este servicio)
    embedding_service_status = await check_embedding_service_status()
    components["embedding_service"] = embedding_service_status
    
    # Verificar la cola de trabajos (específico del servicio de ingestión)
    queue_status = await check_jobs_queue()
    components["jobs_queue"] = queue_status
    
    # Generar respuesta estandarizada usando el helper común
    return get_service_health(
        components=components,
        service_version=settings.service_version
    )

@router.get("/status", 
            response_model=None,
            summary="Estado detallado del servicio",
            description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene estado detallado del servicio de ingestión con métricas y dependencias.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado de componentes críticos (cache, DB)
    - Estado de servicios dependientes (embedding-service)
    - Estado de la cola de trabajos
    - Versión y entorno de ejecución
    """
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="ingestion-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "embedding_service": check_embedding_service_status,
            "jobs_queue": check_jobs_queue
        },
        # Métricas adicionales específicas del servicio
        extra_metrics={
            "supported_file_types": ["pdf", "docx", "txt", "md", "html"],
            "max_file_size_mb": settings.max_file_size_mb,
            "chunking_strategies": ["recursive", "fixed", "sentence"]
        }
    )

async def check_embedding_service_status() -> str:
    """
    Verifica el estado del servicio de embeddings.
    
    Returns:
        str: Estado del servicio ("available" o "unavailable")
    """
    try:
        is_available = await check_service_health(
            service_url=settings.embedding_service_url,
            service_name="embedding-service"
        )
        return "available" if is_available else "unavailable"
    except Exception as e:
        logger.warning(f"Error verificando servicio de embeddings: {str(e)}")
        return "unavailable"

async def check_jobs_queue() -> str:
    """
    Verifica el estado de la cola de trabajos.
    
    Esta función comprueba si la cola de Redis utilizada para los trabajos
    de ingestión está disponible y operativa.
    
    Returns:
        str: Estado de la cola ("available", "degraded" o "unavailable")
    """
    try:
        import redis.asyncio as redis
        if not settings.redis_url:
            return "unavailable"
            
        redis_client = redis.from_url(settings.redis_url)
        
        # Verificar conexión básica
        await redis_client.ping()
        
        # Verificar cola de trabajos (health check más específico)
        job_queue_name = f"queue:ingestion:jobs"
        queue_info = await redis_client.hgetall(f"queue-info:{job_queue_name}")
        
        # Si no existe info sobre la cola, está degradada
        if not queue_info:
            return "degraded"
            
        return "available"
    except Exception as e:
        logger.warning(f"Error verificando cola de trabajos: {str(e)}")
        return "unavailable"