"""
Servicios para la gestión de vector stores.

Este módulo proporciona funciones para interactuar con los vector stores,
incluyendo recuperación, búsqueda y manipulación de datos vectoriales.
"""

import logging
import json
import time
from typing import Optional, Dict, Any, List, Callable

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError, ErrorCode
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.tracking import track_operation
from common.cache import (
    get_with_cache_aside,
    invalidate_resource_cache,
    generate_resource_id_hash
)

from llama_index.vector_stores.supabase import SupabaseVectorStore

logger = logging.getLogger(__name__)

@handle_errors(error_type="service", log_traceback=True)
@with_context(tenant=True, validate_tenant=True)
@track_operation(operation_name="get_vector_store", operation_type="query")
async def get_vector_store_for_collection(
    tenant_id: str,
    collection_id: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Obtiene un vector store para una colección específica utilizando el patrón Cache-Aside.
    
    Implementa el patrón centralizado para verificar primero en caché,
    luego en Supabase, y finalmente crear si es necesario.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto de la operación
        
    Returns:
        Vector store configurado para la colección
    
    Raises:
        ServiceError: Si no se puede obtener el vector store
    """
    # Validar parámetros
    if not tenant_id or not collection_id:
        raise ServiceError(
            message="Se requieren tenant_id y collection_id",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    # Generar un identificador consistente para esta colección
    resource_id = f"vector_store:{collection_id}"
    
    # Función para buscar en Supabase si no está en caché
    async def fetch_vector_store_from_db(resource_id, tenant_id, ctx):
        try:
            # Obtener cliente Supabase
            supabase = get_supabase_client()
            
            # Verificar que la colección existe
            collections_table = get_table_name("collections")
            collection_result = (supabase.table(collections_table)
                                .select("id, name, description, embedding_model")
                                .eq("id", collection_id)
                                .eq("tenant_id", tenant_id)
                                .limit(1)
                                .execute())
            
            if not collection_result.data:
                logger.warning(f"Colección no encontrada: {collection_id} para tenant {tenant_id}")
                return None
            
            collection = collection_result.data[0]
            
            # Configurar vector store
            table_name = get_table_name("document_chunks")
            vector_store = SupabaseVectorStore(
                client=supabase,
                table_name=table_name,
                tenant_id_filter=tenant_id,
                collection_id_filter=collection_id
            )
            
            # Preparar resultado con metadatos
            result = {
                "vector_store": vector_store,
                "collection": collection,
                "metadata": {
                    "tenant_id": tenant_id,
                    "collection_id": collection_id,
                    "table_name": table_name
                }
            }
            
            return result
        except Exception as e:
            logger.error(f"Error obteniendo vector store desde Supabase: {str(e)}")
            return None
    
    # No se requiere función de generación ya que no generamos vector stores,
    # solo los configuramos desde datos existentes
    async def generate_vector_store(resource_id, tenant_id, ctx):
        # Este caso solo se alcanza si la colección no existe,
        # lo que es un error que debería ser manejado
        return None
    
    # Usar la implementación centralizada del patrón Cache-Aside
    result, metrics = await get_with_cache_aside(
        data_type="vector_store",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_vector_store_from_db,
        generate_func=generate_vector_store,  # En este caso siempre será None si no está en DB
        agent_id=ctx.get_agent_id() if ctx else None,
        ctx=ctx
    )
    
    # Verificar resultado y manejar caso de no encontrado
    if not result:
        raise ServiceError(
            message=f"Colección no encontrada: {collection_id}",
            error_code=ErrorCode.NOT_FOUND,
            details={
                "tenant_id": tenant_id,
                "collection_id": collection_id
            }
        )
    
    # Agregar métricas al contexto si está disponible
    if ctx:
        ctx.add_metric("vector_store_metrics", metrics)
        
        # Registrar la fuente del vector store para análisis
        ctx.add_metadata("vector_store_source", metrics.get("source", "unknown"))
    
    return result

@handle_errors(error_type="service")
async def invalidate_vector_store_cache(tenant_id: str, collection_id: str):
    """
    Invalida la caché para un vector store específico.
    
    Esta función debe llamarse cuando se modifica una colección o sus documentos
    para asegurar que las consultas posteriores obtengan los datos más recientes.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
    """
    resource_id = f"vector_store:{collection_id}"
    
    # Usar la función centralizada de invalidación de caché
    success = await invalidate_resource_cache(
        data_type="vector_store",
        resource_id=resource_id,
        tenant_id=tenant_id
    )
    
    if success:
        logger.info(f"Caché invalidada para vector store: {collection_id} (tenant: {tenant_id})")
    else:
        logger.warning(f"No se pudo invalidar caché para vector store: {collection_id} (tenant: {tenant_id})")
    
    return success