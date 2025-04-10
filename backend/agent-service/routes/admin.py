import logging
from typing import Optional

from fastapi import APIRouter, Query, Depends

from common.models import TenantInfo, CacheClearResponse
from common.errors import ServiceError, handle_errors
from common.auth import verify_tenant, get_auth_info
from common.config import get_settings, invalidate_settings_cache
from common.cache.redis import delete_pattern
from common.cache.counters import invalidate_tenant_cache

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

@router.post(
    "/clear-config-cache",
    tags=["Admin"],
    summary="Limpiar Caché de Configuración",
    description="Invalida el caché de configuraciones para forzar la recarga (global o específico del tenant).",
    response_model=CacheClearResponse
)
@handle_errors(error_type="simple", log_traceback=False)
async def clear_config_cache(
    scope: Optional[str] = Query(None, description="Ámbito específico a invalidar ('tenant', 'service', 'agent', 'collection')"),
    scope_id: Optional[str] = Query(None, description="ID específico del ámbito (ej: agent_id, service_name)"),
    environment: str = Query(settings.environment, description="Entorno de configuración"),
    tenant_info: Optional[TenantInfo] = Depends(get_auth_info)
):
    """
    Invalida el caché de configuraciones para el tenant autenticado (o globalmente),
    con soporte para invalidación específica por ámbito.
    """
    actual_tenant_id = tenant_info.tenant_id if tenant_info else None
    keys_cleaned_count = -1
    message = ""
    scope_info = scope or ("all_within_tenant" if actual_tenant_id else "global")
    pattern_used = ""

    try:
        if actual_tenant_id:
            # Invalidation for a specific authenticated tenant
            if scope:
                # Usar función para aplicar cambios de configuración para tenant
                # No disponible directamente en el código mostrado, simulamos su comportamiento
                logger.info(f"Aplicando cambios de configuración para tenant {actual_tenant_id}, scope: {scope}, scope_id: {scope_id}")
                # Invalidar caché de configuraciones
                invalidate_settings_cache(actual_tenant_id)
                
                # Limpiar caché Redis
                pattern_used = f"tenant_config:{actual_tenant_id}:{environment}:{scope}"
                if scope_id:
                    pattern_used += f":{scope_id}"
                pattern_used += ":*"
                
                # Eliminación de patrón
                keys_cleaned_count = await delete_pattern(pattern_used)
                
                scope_msg = f"ámbito {scope}" + (f" (ID: {scope_id})" if scope_id else "")
                message = f"Caché de configuraciones invalidado para tenant {actual_tenant_id} en {scope_msg}"
            else:
                # Invalidate all settings for the tenant
                logger.info(f"Invalidando caché de configuración para tenant {actual_tenant_id}")
                # Invalidar caché de settings
                invalidate_settings_cache(actual_tenant_id)
                
                # Eliminar caché de Redis
                pattern_used = f"tenant_config:{actual_tenant_id}:*"
                keys_cleaned_count = await delete_pattern(pattern_used)
                
                message = f"Caché de configuraciones invalidado para tenant {actual_tenant_id}"
        else:
            # Global invalidation (no specific tenant authenticated)
            if scope:
                # No permitimos invalidación global por ámbito sin tenant específico
                raise ServiceError(
                    message="Invalidación global por ámbito requiere autenticación de tenant",
                    status_code=400,
                    error_code="INVALID_REQUEST"
                )
            else:
                logger.info("Invalidando caché de configuración globalmente")
                # Invalidar caché global
                invalidate_settings_cache()
                
                # Eliminar caché de Redis global
                pattern_used = "tenant_config:*"
                keys_cleaned_count = await delete_pattern(pattern_used)
                
                message = "Caché de configuraciones invalidado globalmente"

        return CacheClearResponse(
            success=True,
            message=message,
            keys_deleted=keys_cleaned_count if keys_cleaned_count is not None else -1,
            metadata={
                "pattern": pattern_used,
                "scope": scope_info,
                "tenant_id": actual_tenant_id or "all"
            }
        )

    except Exception as e:
        logger.exception(f"Error inesperado limpiando caché de configuraciones: {str(e)}")
        return CacheClearResponse(
            success=False,
            message=f"Error limpiando caché: {str(e)}",
            keys_deleted=0,
            metadata={
                "pattern": pattern_used,
                "scope": scope_info,
                "tenant_id": actual_tenant_id or "all",
                "error": str(e)
            }
        )

@router.post(
    "/clear-tenant-cache",
    tags=["Admin"],
    summary="Limpiar Caché de Tenant",
    description="Invalida toda la caché asociada a un tenant específico.",
    response_model=CacheClearResponse
)
@handle_errors(error_type="simple", log_traceback=False)
async def clear_tenant_cache(
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Invalida toda la caché asociada a un tenant específico,
    incluyendo agentes, conversaciones, embeddings, etc.
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        # Invalidar toda la caché del tenant
        keys_deleted = await invalidate_tenant_cache(tenant_id)
        
        return CacheClearResponse(
            success=True,
            message=f"Caché del tenant {tenant_id} invalidada exitosamente",
            keys_deleted=keys_deleted,
            metadata={
                "tenant_id": tenant_id
            }
        )
    except Exception as e:
        logger.error(f"Error al invalidar caché del tenant: {str(e)}")
        return CacheClearResponse(
            success=False,
            message=f"Error al invalidar caché del tenant: {str(e)}",
            keys_deleted=0,
            metadata={
                "tenant_id": tenant_id,
                "error": str(e)
            }
        )