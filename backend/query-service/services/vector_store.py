# Actualización de query-service/services/vector_store.py

import logging
from typing import Optional, Any

from common.db.supabase import get_tenant_vector_store
from common.cache import CacheManager
from common.context import with_context, Context
from common.errors import handle_errors, CollectionNotFoundError

logger = logging.getLogger(__name__)

@with_context(tenant=True, collection=True)
@handle_errors(error_type="simple", log_traceback=False)
async def get_vector_store_for_collection(tenant_id: str, collection_id: str, ctx: Context = None) -> Optional[Any]:
    """
    Obtiene un vector store para una colección específica con soporte de caché.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        Vector store para la colección o None si no se encuentra
    """
    # Buscar en caché unificada
    vector_store = await CacheManager.get(
        data_type="vector_store",
        resource_id=collection_id,
        tenant_id=tenant_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        search_hierarchy=True
    )
    
    if vector_store:
        logger.debug(f"Vector store para colección {collection_id} obtenido de caché")
        return vector_store
    
    # Si no está en caché, obtener de Supabase
    try:
        vector_store = get_tenant_vector_store(
            tenant_id=tenant_id,
            collection_id=collection_id
        )
        
        if vector_store:
            # Cachear para futuras solicitudes (usando ttl estandarizado)
            await CacheManager.set(
                data_type="vector_store",
                resource_id=collection_id,
                value=vector_store,
                tenant_id=tenant_id,
                agent_id=ctx.get_agent_id() if ctx else None,
                ttl=CacheManager.ttl_medium
            )
            
        return vector_store
    except Exception as e:
        logger.error(f"Error obteniendo vector store: {str(e)}")
        return None

@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def invalidate_vector_store_cache(tenant_id: str, collection_id: str, ctx: Context = None) -> bool:
    """
    Invalida la caché del vector store para una colección.
    
    Esta función debe llamarse cuando se modifican documentos en una colección.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        bool: True si se invalidó correctamente
    """
    try:
        # Invalidar caché relacionada con esta colección usando CacheManager
        deleted = await CacheManager.invalidate(
            data_type="vector_store",
            resource_id=collection_id,
            tenant_id=tenant_id
        )
        
        logger.info(f"Caché de vector store invalidada para colección {collection_id}: {deleted} claves")
        return True
    except Exception as e:
        logger.error(f"Error al invalidar caché de vector store: {str(e)}")
        return False