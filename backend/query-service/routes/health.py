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
from common.context import with_context, Context
from common.config import get_settings
from common.utils.http import check_service_health

# Importación para verificación de salud
from common.cache.manager import CacheManager
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

router = APIRouter()
logger = logging.getLogger(__name__)

# Variable global para registrar el inicio del servicio
service_start_time = time.time()

@router.get(
    "/health",
    response_model=None,
    summary="Estado del servicio",
    description="Verifica el estado operativo del servicio"
)
@router.get(
    "/status",
    response_model=None,
    summary="Estado del servicio (alias)",
    description="Alias para /health para mantener compatibilidad entre servicios"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio.
    
    Este endpoint proporciona información sobre la disponibilidad del servicio
    y sus componentes esenciales como la base de datos y Redis.
    
    Returns:
        HealthResponse: Estado detallado del servicio
    """
    settings = get_settings()
    
    # Verificar conexiones
    cache_available = await check_cache_connection()
    supabase_available = await check_supabase_connection()
    
    # Determinar estado general
    status = "healthy"
    if not cache_available or not supabase_available:
        status = "degraded"
    
    # Construir respuesta
    return HealthResponse(
        success=True,
        message="Servicio en funcionamiento",
        status=status,
        components={
            "cache": "available" if cache_available else "unavailable",
            "supabase": "available" if supabase_available else "unavailable",
        },
        version=settings.service_version
    )

@router.get(
    "/ready",
    response_model=None,
    summary="Estado de disponibilidad",
    description="Verifica si el servicio está listo para recibir solicitudes"
)
@router.get(
    "/status/detailed",
    response_model=None,
    summary="Estado detallado",
    description="Proporciona información detallada sobre el estado del servicio"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
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
    cache_available = await check_cache_connection()
    supabase_available = await check_supabase_connection()
    
    # Verificar servicios externos
    embedding_service_available = await check_embedding_service()
    
    # Determinar el estado general del servicio
    status = "healthy"
    if not cache_available or not supabase_available:
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
            "cache": "available" if cache_available else "unavailable",
            "supabase": "available" if supabase_available else "unavailable",
            "embedding_service": "available" if embedding_service_available else "unavailable"
        },
        dependencies={
            "cache": cache_available,
            "supabase": supabase_available,
            "embedding_service": embedding_service_available
        }
    )

async def check_cache_connection() -> bool:
    """
    Verifica la disponibilidad del sistema de caché unificado.
    
    Returns:
        bool: True si caché disponible, False en caso contrario
    """
    try:
        # En lugar de usar CacheManager.get que puede causar recursión,
        # verificamos directamente el cliente Redis usando el método de common.cache.manager
        from common.cache.manager import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            # Realizar una operación simple con Redis
            await redis_client.ping()
            return True
        return False
    except Exception as e:
        logger.error(f"Error al verificar caché: {e}")
        return False

async def check_supabase_connection() -> bool:
    """
    Verifica la disponibilidad de la conexión con Supabase.
    
    Returns:
        bool: True si la conexión está disponible, False en caso contrario
    """
    try:
        # Verificar si Supabase está habilitado
        import os
        if os.getenv("LOAD_CONFIG_FROM_SUPABASE", "false").lower() != "true":
            # Si está deshabilitado por configuración, considerarlo "successful"
            # pero reportarlo como un estado especial
            logger.info("Supabase está deshabilitado, reportando como deshabilitado pero 'saludable'")
            return True
            
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