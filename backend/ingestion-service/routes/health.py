"""
Endpoints para verificación de salud del servicio.
"""

import logging

from fastapi import APIRouter

from common.models import HealthResponse
from common.errors import handle_service_error_simple
from common.config import get_settings
from common.cache.redis import get_redis_client
from common.db.supabase import get_supabase_client
from common.utils.http import check_service_health

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health", response_model=HealthResponse)
@handle_service_error_simple
async def get_service_status() -> HealthResponse:
    """
    Verifica el estado del servicio y sus dependencias críticas.
    
    Este endpoint proporciona información detallada sobre el estado operativo 
    del servicio de ingesta y sus componentes dependientes.
    """
    # Verificar Redis
    redis_client = await get_redis_client()
    redis_status = "available" if redis_client and await redis_client.ping() else "unavailable"
    
    # Verificar Supabase
    supabase_status = "available"
    try:
        supabase = get_supabase_client()
        supabase.table("tenants").select("tenant_id").limit(1).execute()
    except Exception as e:
        logger.warning(f"Supabase no disponible: {str(e)}")
        supabase_status = "unavailable"
    
    # Verificar servicio de embeddings
    settings = get_settings()
    embedding_service_status = "available"
    try:
        embedding_service_available = await check_service_health(
            settings.embedding_service_url,
            "embedding-service"
        )
        if not embedding_service_available:
            embedding_service_status = "unavailable"
    except Exception as e:
        logger.warning(f"Error verificando servicio de embeddings: {str(e)}")
        embedding_service_status = "unavailable"
    
    # Determinar estado general - necesitamos Redis y Supabase
    components = {
        "redis": redis_status,
        "supabase": supabase_status,
        "embedding_service": embedding_service_status
    }
    
    is_healthy = (redis_status == "available" and 
                 supabase_status == "available")
    
    # Si el servicio de embeddings está caído, todavía podemos funcionar parcialmente
    status = "healthy" if is_healthy else "degraded"
    
    # Si no tenemos Redis, estamos en estado crítico y no podemos procesar
    if redis_status == "unavailable":
        status = "critical"
    
    return HealthResponse(
        success=True,  
        status=status,
        components=components,
        version=settings.service_version,
        message="Servicio de ingesta operativo" if is_healthy else 
                "Servicio de ingesta con funcionalidad limitada"
    )