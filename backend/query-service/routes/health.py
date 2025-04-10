"""
Endpoints para verificación de salud y estado del servicio.
"""

import time
import logging
from typing import Dict, Any
from datetime import timedelta

from fastapi import APIRouter

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.config import get_settings
from common.utils.http import check_service_health

# Importación para verificación de salud
from common.cache.redis import get_redis_client
from common.db.supabase import get_supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Variable global para registrar el inicio del servicio
service_start_time = time.time()

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio",
    description="Verifica el estado operativo del servicio"
)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check():
    """
    Verifica el estado básico del servicio.
    
    Este endpoint proporciona información sobre la disponibilidad del servicio
    y sus componentes esenciales como la base de datos y Redis.
    
    Returns:
        HealthResponse: Estado detallado del servicio
    """
    settings = get_settings()
    
    # Verificar conexiones
    redis_available = await check_redis_connection()
    supabase_available = await check_supabase_connection()
    
    # Determinar estado general
    status = "healthy"
    if not redis_available or not supabase_available:
        status = "degraded"
    
    # Construir respuesta
    return HealthResponse(
        success=True,
        message="Servicio en funcionamiento",
        status=status,
        components={
            "redis": "available" if redis_available else "unavailable",
            "database": "available" if supabase_available else "unavailable",
        },
        version=settings.service_version
    )

@router.get(
    "/status",
    response_model=ServiceStatusResponse,
    summary="Estado detallado",
    description="Proporciona información detallada sobre el estado del servicio"
)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status():
    """
    Obtiene el estado detallado del servicio con métricas adicionales.
    
    Este endpoint proporciona información más detallada que /health,
    incluyendo tiempo de actividad, entorno, y estado de componentes.
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio
    """
    settings = get_settings()
    
    # Calcular tiempo de actividad
    uptime_seconds = time.time() - service_start_time
    uptime_formatted = str(timedelta(seconds=int(uptime_seconds)))
    
    # Verificar el estado de las dependencias
    redis_available = await check_redis_connection()
    supabase_available = await check_supabase_connection()
    
    # Verificar servicios externos
    embedding_service_available = await check_embedding_service()
    
    # Determinar el estado general del servicio
    status = "healthy"
    if not redis_available or not supabase_available:
        status = "degraded"
    if not embedding_service_available:
        status = "limited"
    
    # Construir la respuesta
    return ServiceStatusResponse(
        success=True,
        service_name="query-service",
        version=settings.service_version,
        environment=settings.environment,
        uptime=uptime_seconds,
        uptime_formatted=uptime_formatted,
        status=status,
        components={
            "redis": "available" if redis_available else "unavailable",
            "supabase": "available" if supabase_available else "unavailable",
            "embedding_service": "available" if embedding_service_available else "unavailable"
        },
        dependencies={
            "redis": redis_available,
            "supabase": supabase_available,
            "embedding_service": embedding_service_available
        }
    )

async def check_redis_connection() -> bool:
    """
    Verifica la disponibilidad de la conexión con Redis.
    
    Returns:
        bool: True si la conexión está disponible, False en caso contrario
    """
    try:
        redis_client = await get_redis_client()
        if not redis_client:
            return False
        return await redis_client.ping()
    except Exception as e:
        logger.error(f"Error al verificar conexión con Redis: {str(e)}")
        return False

async def check_supabase_connection() -> bool:
    """
    Verifica la disponibilidad de la conexión con Supabase.
    
    Returns:
        bool: True si la conexión está disponible, False en caso contrario
    """
    try:
        supabase = get_supabase_client()
        # Intentar una operación sencilla
        result = await supabase.table(get_table_name("tenants")).select("count", count="exact").limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"Error al verificar conexión con Supabase: {str(e)}")
        return False

async def check_embedding_service() -> bool:
    """
    Verifica la disponibilidad del servicio de embeddings usando la función común.
    
    Returns:
        bool: True si el servicio está disponible, False en caso contrario
    """
    settings = get_settings()
    return await check_service_health(
        service_url=settings.embedding_service_url, 
        service_name="embedding-service"
    )