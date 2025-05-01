"""
Endpoints para verificación de salud del servicio.
"""

import logging

from fastapi import APIRouter

from common.models import HealthResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.config import get_settings
from common.cache.manager import CacheManager
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.utils.http import check_service_health

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health", response_model=None)
@router.get("/status", response_model=None)  # Alias para compatibilidad con agent-service
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def get_service_status(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado del servicio y sus dependencias críticas.
    
    Este endpoint proporciona información detallada sobre el estado operativo 
    del servicio de ingesta y sus componentes dependientes.
    """
    # Verificar sistema de caché unificado
    cache_status = "unavailable"
    try:
        # Intentar una operación simple con CacheManager
        await CacheManager.get(
            data_type="system",
            resource_id="health_check"
        )
        cache_status = "available"
    except Exception as e:
        logger.warning(f"Cache no disponible: {str(e)}")
    
    # Verificar Supabase
    supabase_status = "available"
    try:
        supabase = get_supabase_client()
        supabase.table(get_table_name("tenants")).select("tenant_id").limit(1).execute()
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
    
    # Determinar estado general - necesitamos cache y Supabase
    components = {
        "cache": cache_status,
        "supabase": supabase_status,
        "embedding_service": embedding_service_status
    }
    
    is_healthy = (cache_status == "available" and 
                 supabase_status == "available")
    
    # Si el servicio de embeddings está caído, todavía podemos funcionar parcialmente
    status = "healthy" if is_healthy else "degraded"
    
    # Si no tenemos caché, estamos en estado crítico y no podemos procesar
    if cache_status == "unavailable":
        status = "critical"
    
    return HealthResponse(
        success=True,  
        status=status,
        components=components,
        version=settings.service_version,
        message="Servicio de ingesta operativo" if is_healthy else 
                "Servicio de ingesta con funcionalidad limitada"
    )