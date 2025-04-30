"""
Endpoints para gestión de colecciones.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4

from common.models import (
    TenantInfo, CollectionsListResponse, CollectionInfo, 
    CollectionCreationResponse, CollectionUpdateResponse, 
    CollectionStatsResponse, DeleteCollectionResponse
)
from common.errors import (
    handle_errors, ErrorCode,
    CollectionNotFoundError, InvalidQueryParamsError, 
    QueryProcessingError, RetrievalError
)
from common.context import with_context, Context
from common.auth.tenant import TenantInfo, verify_tenant
from common.config import get_settings
from common.cache import CacheManager, invalidate_document_update
from common.db.supabase import get_supabase_client, get_tenant_collections, get_table_name

router = APIRouter()
logger = logging.getLogger(__name__)

@with_context(tenant=True)
@router.get(
    "/collections",
    response_model=CollectionsListResponse,
    response_model_exclude_none=True,
    response_model_exclude={"ctx"},
    summary="Listar colecciones",
    description="Obtiene la lista de colecciones disponibles para el tenant"
)
@handle_errors(error_type="simple", log_traceback=False)
async def list_collections(
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Lista todas las colecciones para el tenant actual.
    
    Args:
        tenant_info: Información del tenant
        
    Returns:
        CollectionsListResponse: Lista de colecciones
    """
    try:
        # Obtener colecciones usando la función de common/db
        collections_data = get_tenant_collections(tenant_info.tenant_id)
        
        # Transformar en modelo CollectionInfo
        collections = []
        for item in collections_data:
            collections.append(
                CollectionInfo(
                    collection_id=item["collection_id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    document_count=item.get("document_count", 0),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at")
                )
            )
        
        return CollectionsListResponse(
            success=True,
            message="Colecciones obtenidas correctamente",
            collections=collections,
            count=len(collections)
        )
    except Exception as e:
        logger.error(f"Error listando colecciones: {str(e)}")
        raise QueryProcessingError(
            message=f"Error al listar colecciones: {str(e)}",
            details={"tenant_id": tenant_info.tenant_id}
        )

@with_context(tenant=True)
@router.post(
    "/collections",
    response_model=CollectionCreationResponse,
    response_model_exclude_none=True,
    response_model_exclude={"ctx"},
    summary="Crear colección",
    description="Crea una nueva colección para organizar documentos"
)
@handle_errors(error_type="simple", log_traceback=False)
async def create_collection(
    name: str,
    description: Optional[str] = None,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Crea una nueva colección para el tenant actual.
    
    Args:
        name: Nombre de la colección
        description: Descripción opcional
        tenant_info: Información del tenant
        
    Returns:
        CollectionCreationResponse: Datos de la colección creada
    """
    try:
        # Generar UUID para la colección
        collection_id = str(uuid.uuid4())
        
        # Preparar datos para inserción
        collection_data = {
            "collection_id": collection_id,
            "tenant_id": tenant_info.tenant_id,
            "name": name,
            "description": description or "",
            "is_active": True
        }
        
        # Insertar en base de datos
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("collections")).insert(collection_data).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error al crear colección: {result.error}",
                error_code="COLLECTION_CREATION_ERROR"
            )
        
        # Extraer datos de la respuesta
        created_collection = result.data[0] if result.data else collection_data
        
        return CollectionCreationResponse(
            success=True,
            message="Colección creada exitosamente",
            collection_id=created_collection["collection_id"],
            name=created_collection["name"],
            description=created_collection.get("description", ""),
            created_at=created_collection.get("created_at")
        )
    except Exception as e:
        logger.error(f"Error creando colección: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al crear colección: {str(e)}",
            error_code="COLLECTION_CREATION_ERROR"
        )

@with_context(tenant=True, collection=True)
@router.put(
    "/collections/{collection_id}",
    response_model=CollectionUpdateResponse,
    response_model_exclude_none=True,
    response_model_exclude={"ctx"},
    summary="Actualizar colección",
    description="Modifica una colección existente"
)
@handle_errors(error_type="simple", log_traceback=False)
async def update_collection(
    collection_id: str,
    name: str,
    description: Optional[str] = None,
    is_active: bool = True,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Actualiza una colección existente.
    
    Args:
        collection_id: ID de la colección
        name: Nuevo nombre
        description: Nueva descripción
        is_active: Estado de activación
        tenant_info: Información del tenant
        
    Returns:
        CollectionUpdateResponse: Datos actualizados
    """
    try:
        # (Decorador already sets collection_id)
        
        # Verificar que la colección exista y pertenezca al tenant
        supabase = get_supabase_client()
        check_result = await supabase.table(get_table_name("collections")) \
            .select("*") \
            .eq("collection_id", collection_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .execute()
        
        if not check_result.data:
            raise CollectionNotFoundError(
                message=f"Collection with ID {collection_id} not found",
                details={"collection_id": collection_id, "tenant_id": tenant_info.tenant_id}
            )
        
        # Preparar datos para actualización
        update_data = {
            "name": name,
            "description": description,
            "is_active": is_active,
            "updated_at": "NOW()"
        }
        
        # Filtrar valores None
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        # Actualizar en base de datos
        result = await supabase.table(get_table_name("collections")) \
            .update(update_data) \
            .eq("collection_id", collection_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error al actualizar colección: {result.error}",
                error_code="COLLECTION_UPDATE_ERROR"
            )
        
        # Extraer datos de la respuesta
        updated_collection = result.data[0] if result.data else {**check_result.data[0], **update_data}
        
        return CollectionUpdateResponse(
            success=True,
            message="Colección actualizada exitosamente",
            collection_id=collection_id,
            name=updated_collection["name"],
            description=updated_collection.get("description", ""),
            is_active=updated_collection["is_active"],
            updated_at=updated_collection.get("updated_at")
        )
    except Exception as e:
        logger.error(f"Error actualizando colección: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al actualizar colección: {str(e)}",
            error_code="COLLECTION_UPDATE_ERROR"
        )

@with_context(tenant=True, collection=True)
@router.delete(
    "/collections/{collection_id}",
    response_model=DeleteCollectionResponse,
    response_model_exclude_none=True,
    response_model_exclude={"ctx"},
    summary="Eliminar colección",
    description="Elimina una colección y todos sus documentos"
)
@handle_errors(error_type="simple", log_traceback=False)
async def delete_collection(
    collection_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Elimina una colección completa y todos sus documentos asociados.
    
    Args:
        collection_id: ID de la colección a eliminar
        tenant_info: Información del tenant
        
    Returns:
        DeleteCollectionResponse: Resultado de la eliminación
    """
    try:
        # (Decorador already sets collection_id)
        
        supabase = get_supabase_client()
        
        # Verificar que la colección exista y pertenezca al tenant
        collection_result = await supabase.table(get_table_name("collections")) \
            .select("name") \
            .eq("collection_id", collection_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .execute()
        
        if not collection_result.data:
            raise CollectionNotFoundError(
                message=f"Collection with ID {collection_id} not found",
                details={"collection_id": collection_id, "tenant_id": tenant_info.tenant_id}
            )
            
        collection_name = collection_result.data[0]["name"]
        
        # Contar documentos a eliminar
        chunks_result = await supabase.table(get_table_name("document_chunks")) \
            .select("count", count="exact") \
            .eq("tenant_id", tenant_info.tenant_id) \
            .filter("metadata->collection_id", "eq", collection_id) \
            .execute()
            
        document_count = chunks_result.count if hasattr(chunks_result, "count") else 0
        
        # Eliminar todos los chunks de la colección
        await supabase.table(get_table_name("document_chunks")) \
            .delete() \
            .eq("tenant_id", tenant_info.tenant_id) \
            .filter("metadata->collection_id", "eq", collection_id) \
            .execute()
        
        # Eliminar la colección
        await supabase.table(get_table_name("collections")) \
            .delete() \
            .eq("collection_id", collection_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .execute()
            
        return DeleteCollectionResponse(
            success=True,
            message=f"Colección '{collection_name}' eliminada exitosamente",
            deleted_documents=document_count
        )
    except Exception as e:
        logger.error(f"Error eliminando colección: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al eliminar colección: {str(e)}",
            error_code="COLLECTION_DELETE_ERROR"
        )

@with_context(tenant=True, collection=True)
@router.get(
    "/collections/{collection_id}/stats",
    response_model=CollectionStatsResponse,
    response_model_exclude_none=True,
    response_model_exclude={"ctx"},
    summary="Estadísticas de colección",
    description="Obtiene estadísticas detalladas de una colección"
)
@handle_errors(error_type="simple", log_traceback=False)
async def get_collection_stats(
    collection_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Obtiene estadísticas detalladas de una colección.
    
    Args:
        collection_id: ID de la colección
        tenant_info: Información del tenant
        
    Returns:
        CollectionStatsResponse: Estadísticas de la colección
    """
    try:
        # (Decorador already sets collection_id)
        
        supabase = get_supabase_client()
        
        # Verificar que la colección exista y pertenezca al tenant
        collection_result = await supabase.table(get_table_name("collections")) \
            .select("*") \
            .eq("collection_id", collection_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .execute()
        
        if not collection_result.data:
            raise CollectionNotFoundError(
                message=f"Collection with ID {collection_id} not found",
                details={"collection_id": collection_id, "tenant_id": tenant_info.tenant_id}
            )
        
        collection_data = collection_result.data[0]
        
        # Contar documentos (chunks)
        chunks_result = await supabase.table(get_table_name("document_chunks")) \
            .select("count", count="exact") \
            .eq("tenant_id", tenant_info.tenant_id) \
            .filter("metadata->collection_id", "eq", collection_id) \
            .execute()
        
        document_count = chunks_result.count if hasattr(chunks_result, "count") else 0
        
        # Contar consultas (puede requerir una tabla específica de estadísticas)
        queries_count = 0
        try:
            query_stats = await supabase.table(get_table_name("query_logs")) \
                .select("count", count="exact") \
                .eq("tenant_id", tenant_info.tenant_id) \
                .filter("metadata->collection_id", "eq", collection_id) \
                .execute()
            
            queries_count = query_stats.count if hasattr(query_stats, "count") else 0
        except Exception:
            # Si la tabla no existe o hay otro error, continuamos con 0
            pass
        
        # Construir respuesta
        return CollectionStatsResponse(
            success=True,
            collection_id=collection_id,
            name=collection_data["name"],
            description=collection_data.get("description", ""),
            document_count=document_count,
            queries_count=queries_count,
            created_at=collection_data.get("created_at"),
            updated_at=collection_data.get("updated_at"),
            is_active=collection_data.get("is_active", True)
        )
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de colección: {str(e)}")
        raise QueryProcessingError(
            message=f"Error al obtener estadísticas de colección: {str(e)}",
            details={"collection_id": collection_id, "tenant_id": tenant_info.tenant_id}
        )