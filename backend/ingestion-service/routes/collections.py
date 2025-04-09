"""
Endpoints para gestión de colecciones de documentos (proxy al query-service).
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4

from common.models import (
    TenantInfo, CollectionsListResponse, CollectionInfo, 
    CollectionCreationResponse, CollectionUpdateResponse, 
    CollectionStatsResponse, DeleteCollectionResponse
)
from common.errors import (
    ServiceError, handle_service_error_simple, ErrorCode,
    CollectionNotFoundError
)
from common.context import with_context, set_current_collection_id
from common.auth import verify_tenant
from common.utils.http import call_service
from common.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "",
    response_model=CollectionsListResponse,
    summary="Listar colecciones",
    description="Obtiene la lista de colecciones disponibles para el tenant"
)
@handle_service_error_simple
@with_context(tenant=True)
async def list_collections(
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Lista todas las colecciones para el tenant actual (proxy al query-service).
    
    Args:
        tenant_info: Información del tenant
        
    Returns:
        CollectionsListResponse: Lista de colecciones
    """
    settings = get_settings()
    
    try:
        # Realizar llamada al servicio de consultas
        response = await call_service(
            url=f"{settings.query_service_url}/collections",
            data={},
            tenant_id=tenant_info.tenant_id,
            operation_type="health_check"  # Usar timeout corto para esta consulta
        )
        
        # Verificar éxito de la operación
        if not response.get("success", False):
            error_msg = response.get("message", "Error desconocido al obtener colecciones")
            logger.warning(f"Error al obtener colecciones: {error_msg}")
            raise ServiceError(
                message=error_msg,
                error_code="COLLECTIONS_FETCH_ERROR"
            )
        
        # Retornar respuesta tal como viene del servicio de consultas
        return response
    except Exception as e:
        if isinstance(e, ServiceError):
            raise e
        logger.error(f"Error al obtener colecciones: {str(e)}")
        raise ServiceError(
            message=f"Error al obtener colecciones: {str(e)}",
            error_code="COLLECTIONS_FETCH_ERROR"
        )

@router.post(
    "",
    response_model=CollectionCreationResponse,
    status_code=201,
    summary="Crear colección",
    description="Crea una nueva colección para organizar documentos"
)
@handle_service_error_simple
@with_context(tenant=True)
async def create_collection(
    name: str,
    description: Optional[str] = None,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Crea una nueva colección para el tenant actual (proxy al query-service).
    
    Args:
        name: Nombre de la colección
        description: Descripción opcional
        tenant_info: Información del tenant
        
    Returns:
        CollectionCreationResponse: Datos de la colección creada
    """
    settings = get_settings()
    
    try:
        # Realizar llamada al servicio de consultas
        response = await call_service(
            url=f"{settings.query_service_url}/collections",
            data={
                "name": name,
                "description": description
            },
            tenant_id=tenant_info.tenant_id,
            operation_type="default"
        )
        
        # Verificar éxito de la operación
        if not response.get("success", False):
            error_msg = response.get("message", "Error desconocido al crear colección")
            logger.warning(f"Error al crear colección: {error_msg}")
            raise ServiceError(
                message=error_msg,
                error_code="COLLECTION_CREATION_ERROR"
            )
        
        # Retornar respuesta tal como viene del servicio de consultas
        return response
    except Exception as e:
        if isinstance(e, ServiceError):
            raise e
        logger.error(f"Error al crear colección: {str(e)}")
        raise ServiceError(
            message=f"Error al crear colección: {str(e)}",
            error_code="COLLECTION_CREATION_ERROR"
        )

@router.get(
    "/{collection_id}/stats",
    response_model=CollectionStatsResponse,
    summary="Estadísticas de colección",
    description="Obtiene estadísticas detalladas de una colección"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def get_collection_stats(
    collection_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Obtiene estadísticas detalladas de una colección (proxy al query-service).
    
    Args:
        collection_id: ID de la colección
        tenant_info: Información del tenant
        
    Returns:
        CollectionStatsResponse: Estadísticas de la colección
    """
    # Establecer collection_id en el contexto
    set_current_collection_id(collection_id)
    settings = get_settings()
    
    try:
        # Realizar llamada al servicio de consultas
        response = await call_service(
            url=f"{settings.query_service_url}/collections/{collection_id}/stats",
            data={},
            tenant_id=tenant_info.tenant_id,
            collection_id=collection_id,
            operation_type="default"
        )
        
        # Verificar éxito de la operación
        if not response.get("success", False):
            error_msg = response.get("message", "Error desconocido al obtener estadísticas")
            logger.warning(f"Error al obtener estadísticas de colección: {error_msg}")
            raise ServiceError(
                message=error_msg,
                error_code="COLLECTION_STATS_ERROR"
            )
        
        # Retornar respuesta tal como viene del servicio de consultas
        return response
    except Exception as e:
        if isinstance(e, ServiceError):
            raise e
        logger.error(f"Error al obtener estadísticas de colección: {str(e)}")
        raise ServiceError(
            message=f"Error al obtener estadísticas de colección: {str(e)}",
            error_code="COLLECTION_STATS_ERROR"
        )