"""
Endpoints para la gestión de documentos ya procesados.
"""

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, Path, HTTPException

from common.models import TenantInfo, DocumentListResponse, DocumentDetailResponse, DeleteDocumentResponse
from common.errors import (
    ServiceError, handle_errors, ErrorCode,
    DocumentProcessingError, NotFoundError
)
from common.context import with_context, Context
from common.auth import verify_tenant
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="Listar documentos",
    description="Obtiene la lista de documentos para un tenant o colección específica"
)
@with_context(tenant=True, collection=True)
@handle_errors(error_type="simple", log_traceback=False)
async def list_documents(
    collection_id: Optional[str] = Query(None, description="Filtrar por ID de colección"),
    status: Optional[str] = Query(None, description="Filtrar por estado (pending, processing, completed, failed)"),
    limit: int = Query(50, description="Número máximo de documentos a devolver"),
    offset: int = Query(0, description="Desplazamiento para paginación"),
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Lista los documentos para el tenant actual, con filtros opcionales.
    
    Args:
        collection_id: Filtrar por ID de colección
        status: Filtrar por estado del documento
        limit: Límite de resultados
        offset: Desplazamiento para paginación
        tenant_info: Información del tenant
        
    Returns:
        DocumentListResponse: Lista paginada de documentos
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Construir consulta base
        query = supabase.table(get_table_name("documents")) \
            .select("*") \
            .eq("tenant_id", tenant_id)
        
        # Aplicar filtros si existen
        if collection_id:
            query = query.eq("collection_id", collection_id)
            
        if status:
            query = query.eq("status", status)
            
        # Aplicar paginación
        query = query.order("created_at", desc=True) \
            .range(offset, offset + limit - 1)
            
        result = await query.execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error obteniendo documentos: {result.error}",
                error_code="DATABASE_ERROR"
            )
        
        # Calcular conteo total para metadatos de paginación
        count_query = supabase.table(get_table_name("documents")) \
            .select("count", count="exact") \
            .eq("tenant_id", tenant_id)
            
        if collection_id:
            count_query = count_query.eq("collection_id", collection_id)
            
        if status:
            count_query = count_query.eq("status", status)
            
        count_result = await count_query.execute()
        total_count = count_result.count if hasattr(count_result, "count") else len(result.data)
        
        # Transformar resultados para la respuesta
        documents = result.data
        
        return DocumentListResponse(
            success=True,
            message="Documentos obtenidos exitosamente",
            documents=documents,
            total=total_count,
            count=len(documents),
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error listando documentos: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al listar documentos: {str(e)}",
            error_code="DOCUMENT_LIST_ERROR"
        )

@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Obtener documento",
    description="Obtiene detalles de un documento específico"
)
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def get_document(
    document_id: str = Path(..., description="ID del documento"),
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Obtiene detalles completos de un documento específico.
    
    Args:
        document_id: ID del documento
        tenant_info: Información del tenant
        
    Returns:
        DocumentDetailResponse: Detalle completo del documento
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Obtener documento
        result = await supabase.table(get_table_name("documents")) \
            .select("*") \
            .eq("document_id", document_id) \
            .eq("tenant_id", tenant_id) \
            .single() \
            .execute()
            
        if not result.data:
            raise NotFoundError(
                message=f"Documento con ID {document_id} no encontrado",
                details={"document_id": document_id}
            )
            
        document = result.data
        
        # Obtener estadísticas de chunks si el documento está completado
        chunks_stats = {}
        if document.get("status") == "completed":
            try:
                chunks_result = await supabase.table(get_table_name("document_chunks")) \
                    .select("count", count="exact") \
                    .eq("tenant_id", tenant_id) \
                    .filter("metadata->document_id", "eq", document_id) \
                    .execute()
                    
                chunks_stats["total_chunks"] = chunks_result.count if hasattr(chunks_result, "count") else 0
            except Exception as chunks_err:
                logger.error(f"Error obteniendo estadísticas de chunks: {str(chunks_err)}")
                chunks_stats["total_chunks"] = 0
        
        # Obtener detalles del trabajo de procesamiento
        processing_info = {}
        try:
            job_result = await supabase.table(get_table_name("processing_jobs")) \
                .select("*") \
                .eq("document_id", document_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
                
            if job_result.data:
                processing_info = job_result.data[0]
        except Exception as job_err:
            logger.error(f"Error obteniendo detalles del trabajo: {str(job_err)}")
        
        return DocumentDetailResponse(
            success=True,
            message="Documento obtenido exitosamente",
            document_id=document_id,
            title=document.get("title"),
            description=document.get("description"),
            collection_id=document.get("collection_id"),
            file_name=document.get("file_name"),
            file_type=document.get("file_type"),
            file_size=document.get("file_size"),
            status=document.get("status"),
            created_at=document.get("created_at"),
            updated_at=document.get("updated_at"),
            tags=document.get("tags", []),
            stats=chunks_stats,
            processing_info=processing_info,
            metadata=document.get("metadata", {})
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo documento: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al obtener documento: {str(e)}",
            error_code="DOCUMENT_FETCH_ERROR"
        )

@router.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    summary="Eliminar documento",
    description="Elimina un documento y todos sus chunks"
)
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def delete_document(
    document_id: str = Path(..., description="ID del documento a eliminar"),
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
):
    """
    Elimina un documento y todos sus chunks asociados.
    
    Args:
        document_id: ID del documento a eliminar
        tenant_info: Información del tenant
        
    Returns:
        DeleteDocumentResponse: Resultado de la eliminación
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Verificar que el documento exista y pertenezca al tenant
        document_result = await supabase.table(get_table_name("documents")) \
            .select("*") \
            .eq("document_id", document_id) \
            .eq("tenant_id", tenant_id) \
            .single() \
            .execute()
            
        if not document_result.data:
            raise NotFoundError(
                message=f"Documento con ID {document_id} no encontrado",
                details={"document_id": document_id}
            )
            
        document = document_result.data
        collection_id = document.get("collection_id")
        
        # Contar chunks a eliminar
        chunks_result = await supabase.table(get_table_name("document_chunks")) \
            .select("count", count="exact") \
            .eq("tenant_id", tenant_id) \
            .filter("metadata->document_id", "eq", document_id) \
            .execute()
            
        chunks_count = chunks_result.count if hasattr(chunks_result, "count") else 0
        
        # Eliminar chunks
        if chunks_count > 0:
            await supabase.table(get_table_name("document_chunks")) \
                .delete() \
                .eq("tenant_id", tenant_id) \
                .filter("metadata->document_id", "eq", document_id) \
                .execute()
        
        # Eliminar trabajos de procesamiento asociados
        try:
            await supabase.table(get_table_name("processing_jobs")) \
                .delete() \
                .eq("document_id", document_id) \
                .eq("tenant_id", tenant_id) \
                .execute()
        except Exception as job_err:
            logger.error(f"Error eliminando trabajos de procesamiento: {str(job_err)}")
        
        # Eliminar documento
        await supabase.table(get_table_name("documents")) \
            .delete() \
            .eq("document_id", document_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
            
        return DeleteDocumentResponse(
            success=True,
            message=f"Documento {document_id} eliminado exitosamente",
            document_id=document_id,
            chunks_deleted=chunks_count,
            collection_id=collection_id
        )
        
    except Exception as e:
        logger.error(f"Error eliminando documento: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al eliminar documento: {str(e)}",
            error_code="DOCUMENT_DELETE_ERROR"
        )