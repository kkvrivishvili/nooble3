import logging

from fastapi import FastAPI
from .agents import router as agents_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .admin import router as admin_router
from .public import router as public_router  # Nueva importación

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI):
    """Registra todas las rutas en la aplicación FastAPI."""
    app.include_router(agents_router, prefix="/agents", tags=["Agents"])
    app.include_router(chat_router, tags=["Chat"])
    app.include_router(conversations_router, prefix="/conversations", tags=["Conversations"])
    app.include_router(admin_router, prefix="/admin", tags=["Admin"])
    app.include_router(public_router, tags=["Public"])
    
    # También registrar endpoints de verificación de salud (health check)
    from common.models import HealthResponse
    from common.errors import handle_errors
    
    @app.get("/status", response_model=HealthResponse, tags=["Health"])
    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    @handle_errors(error_type="simple", log_traceback=False)
    async def get_service_status() -> HealthResponse:
        """Verifica el estado del servicio y sus dependencias."""
        from common.config import get_settings
        from common.db.supabase import get_supabase_client
        from common.cache.manager import CacheManager
        from main import http_client
        
        settings = get_settings()
        
        # Verificar sistema de caché unificado
        cache_status = "unavailable"
        try:
            await CacheManager.get(data_type="system", resource_id="health_check")
            cache_status = "available"
        except Exception as e:
            logger.warning(f"Cache no disponible: {str(e)}")
        
        # Verificar Supabase
        supabase_status = "available"
        try:
            supabase = get_supabase_client()
            await supabase.table("tenants").select("tenant_id").limit(1).execute()
        except Exception as e:
            logger.warning(f"Supabase no disponible: {str(e)}")
            supabase_status = "unavailable"
        
        # Verificar servicio de consulta
        query_service_status = "available"
        try:
            if http_client:
                response = await http_client.get(f"{settings.query_service_url}/status", timeout=5.0)
                if response.status_code != 200:
                    query_service_status = "degraded"
            else:
                query_service_status = "unknown"
        except Exception as e:
            logger.warning(f"Servicio de consulta no disponible: {str(e)}")
            query_service_status = "unavailable"
        
        # Verificar servicio de embeddings
        embedding_service_status = "available"
        try:
            if http_client:
                response = await http_client.get(f"{settings.embedding_service_url}/status", timeout=5.0)
                if response.status_code != 200:
                    embedding_service_status = "degraded"
            else:
                embedding_service_status = "unknown"
        except Exception as e:
            logger.warning(f"Servicio de embeddings no disponible: {str(e)}")
            embedding_service_status = "unavailable"
        
        # Determinar estado general - cache y Supabase deben estar disponibles, y al menos un servicio dependiente
        critical_services_ok = cache_status == "available" and supabase_status == "available"
        dependent_services_ok = (query_service_status in ["available", "degraded"] or 
                                embedding_service_status in ["available", "degraded"])
        
        overall_status = "healthy" if (critical_services_ok and dependent_services_ok) else "degraded"
        
        return HealthResponse(
            success=True,
            status=overall_status,
            components={
                "cache": cache_status,
                "supabase": supabase_status,
                "query_service": query_service_status,
                "embedding_service": embedding_service_status
            },
            version=settings.service_version,
            message=f"Servicio de agente {'operativo' if overall_status == 'healthy' else 'con funcionalidad limitada'}"
        )