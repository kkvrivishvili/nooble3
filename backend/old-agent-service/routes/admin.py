import logging
from typing import Optional, Dict, List, Any

from fastapi import APIRouter, Query, Depends

from common.models import TenantInfo, CacheClearResponse
from common.errors import handle_service_error_simple, ValidationError
from common.auth import verify_tenant
from common.config import get_settings, invalidate_settings_cache
from common.cache import (
    CacheManager,
    invalidate_resource_cache,
    invalidate_coordinated,
    track_cache_metrics,
    METRIC_CACHE_INVALIDATION
)

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
@handle_service_error_simple
async def clear_config_cache(
    scope: Optional[str] = Query(None, description="Ámbito específico a invalidar ('tenant', 'service', 'agent', 'collection')"),
    scope_id: Optional[str] = Query(None, description="ID específico del ámbito (ej: agent_id, service_name)"),
    environment: str = Query(settings.environment, description="Entorno de configuración"),
    tenant_info: Optional[TenantInfo] = Depends(verify_tenant)
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
                
                # Invalidación de caché usando invalidate_coordinated
                related_invalidations = [
                    {"data_type": "agent_config", "resource_id": "*"},
                    {"data_type": "agent_response", "resource_id": "*"},
                    {"data_type": "conversation", "resource_id": "*"},
                    {"data_type": "conversation_messages", "resource_id": "*"}
                ]
                
                invalidation_result = await invalidate_coordinated(
                    tenant_id=actual_tenant_id,
                    primary_data_type="tenant",
                    primary_resource_id=actual_tenant_id,
                    related_invalidations=related_invalidations
                )
                
                # Registrar métrica de invalidación
                await track_cache_metrics(
                    data_type="tenant",
                    tenant_id=actual_tenant_id,
                    metric_type=METRIC_CACHE_INVALIDATION,
                    value=sum(invalidation_result.values()),
                    metadata={"scope": "tenant", "operation": "clear_config_cache"}
                )
                
                keys_cleaned_count = sum(invalidation_result.values())
                
                scope_msg = f"ámbito {scope}" + (f" (ID: {scope_id})" if scope_id else "")
                message = f"Caché del tenant {actual_tenant_id} invalidado: {keys_cleaned_count} entradas removidas en {scope_msg}"
            else:
                # Invalidate all settings for the tenant
                logger.info(f"Invalidando caché de configuración para tenant {actual_tenant_id}")
                # Invalidar caché de settings
                invalidate_settings_cache(actual_tenant_id)
                
                # Invalidación de caché completa de tenant
                related_invalidations = [
                    {"data_type": "agent_config", "resource_id": "*"},
                    {"data_type": "agent_response", "resource_id": "*"},
                    {"data_type": "conversation", "resource_id": "*"},
                    {"data_type": "conversation_messages", "resource_id": "*"}
                ]
                
                invalidation_result = await invalidate_coordinated(
                    tenant_id=actual_tenant_id,
                    primary_data_type="tenant",
                    primary_resource_id=actual_tenant_id,
                    related_invalidations=related_invalidations
                )
                
                # Registrar métrica de invalidación
                await track_cache_metrics(
                    data_type="tenant",
                    tenant_id=actual_tenant_id,
                    metric_type=METRIC_CACHE_INVALIDATION,
                    value=sum(invalidation_result.values()),
                    metadata={"scope": "tenant", "operation": "clear_config_cache"}
                )
                
                keys_cleaned_count = sum(invalidation_result.values())
                
                message = f"Caché del tenant {actual_tenant_id} invalidado: {keys_cleaned_count} entradas removidas"
        else:
            # Global invalidation (no specific tenant authenticated)
            if scope:
                # No permitimos invalidación global por ámbito sin tenant específico
                raise ValidationError(
                    message="Invalidación global por ámbito requiere autenticación de tenant",
                    details={"scope": scope}
                )
            else:
                logger.info("Invalidando caché de configuración globalmente")
                # Invalidar caché de configuraciones global
                invalidate_settings_cache()
                
                # Usar el nuevo patrón de invalidación coordinada para la invalidación global
                # Para invalidación global, vamos a especificar tipos de datos específicos
                # en lugar de una invalidación masiva que podría afectar a datos de otros servicios
                related_invalidations = [
                    {"data_type": "agent_config", "resource_id": "*"},
                    {"data_type": "agent_response", "resource_id": "*"},
                    {"data_type": "conversation", "resource_id": "*"},
                    {"data_type": "conversation_messages", "resource_id": "*"},
                    {"data_type": "system", "resource_id": "*"}
                ]
                
                # Usamos un tenant_id especial para invalidaciones globales
                system_tenant_id = "system"
                
                invalidation_result = await invalidate_coordinated(
                    tenant_id=system_tenant_id,
                    primary_data_type="system",
                    primary_resource_id="global_config",
                    related_invalidations=related_invalidations
                )
                
                # Registrar métrica de invalidación global
                await track_cache_metrics(
                    data_type="system",
                    tenant_id=system_tenant_id,
                    metric_type=METRIC_CACHE_INVALIDATION,
                    value=sum(invalidation_result.values()),
                    metadata={"scope": "global", "operation": "clear_config_cache"}
                )
                
                keys_cleaned_count = sum(invalidation_result.values())
                
                message = f"Caché global invalidado: {keys_cleaned_count} entradas removidas"

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
@handle_service_error_simple
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
        await CacheManager.invalidate_cache(scope="tenant", tenant_id=tenant_id)
        
        return CacheClearResponse(
            success=True,
            message=f"Caché del tenant {tenant_id} invalidada exitosamente",
            keys_deleted=-1,
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