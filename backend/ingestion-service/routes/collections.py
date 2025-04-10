"""
Endpoints para manejo de colecciones de documentos.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends

from common.models import TenantInfo, CollectionsListResponse
from common.errors import ServiceError, handle_errors
from common.context import with_context
from common.auth import verify_tenant
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

router = APIRouter(tags=["collections"])
logger = logging.getLogger(__name__)

@router.get(
    "",
    response_model=CollectionsListResponse,
    summary="Listar colecciones",
    description="Obtiene la lista de colecciones disponibles para el tenant con estadísticas"
)
@handle_errors(error_type="simple", log_traceback=False)
@with_context(tenant=True)
async def list_collections(
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Lista todas las colecciones para el tenant actual con estadísticas.
    
    Args:
        tenant_info: Información del tenant
        
    Returns:
        CollectionsListResponse: Lista de colecciones con estadísticas
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Obtener colecciones básicas
        collections_result = await supabase.table(get_table_name("collections")) \
            .select("*") \
            .eq("tenant_id", tenant_id) \
            .execute()
            
        if collections_result.error:
            raise ServiceError(
                message=f"Error obteniendo colecciones: {collections_result.error}",
                error_code="DATABASE_ERROR"
            )
        
        # Obtener estadísticas de documentos por colección
        collections_with_stats = []
        
        for collection in collections_result.data:
            collection_id = collection.get("collection_id")
            
            # Contar documentos
            docs_result = await supabase.table(get_table_name("documents")) \
                .select("count", count="exact") \
                .eq("tenant_id", tenant_id) \
                .eq("collection_id", collection_id) \
                .execute()
                
            doc_count = docs_result.count if hasattr(docs_result, "count") else 0
            
            # Contar chunks
            chunks_result = await supabase.table(get_table_name("document_chunks")) \
                .select("count", count="exact") \
                .eq("tenant_id", tenant_id) \
                .filter("metadata->collection_id", "eq", collection_id) \
                .execute()
                
            chunk_count = chunks_result.count if hasattr(chunks_result, "count") else 0
            
            # Añadir estadísticas
            collections_with_stats.append({
                **collection,
                "document_count": doc_count,
                "chunk_count": chunk_count
            })
        
        return CollectionsListResponse(
            success=True,
            message="Colecciones obtenidas exitosamente",
            collections=collections_with_stats
        )
        
    except Exception as e:
        logger.error(f"Error listando colecciones: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al listar colecciones: {str(e)}",
            error_code="COLLECTION_LIST_ERROR"
        )