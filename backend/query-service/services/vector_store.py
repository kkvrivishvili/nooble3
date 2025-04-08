# Actualización de query-service/services/vector_store.py

import logging
from typing import Optional, Any

from common.db.supabase import get_tenant_vector_store
from common.cache.specialized import QueryResultCache
from common.context import with_context

logger = logging.getLogger(__name__)

@with_context(tenant=True, collection=True)
async def get_vector_store_for_collection(tenant_id: str, collection_id: str) -> Optional[Any]:
    """
    Obtiene un vector store para una colección específica con soporte de caché.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        
    Returns:
        Vector store para la colección o None si no se encuentra
    """
    from common.cache.contextual import get_cached_value_multi_level, cache_value_multi_level
    
    # Buscar en caché multinivel
    vector_store = await get_cached_value_multi_level(
        key_type="vector_store",
        resource_id=collection_id,
        tenant_id=tenant_id
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
            # Cachear para futuras solicitudes (10 minutos)
            await cache_value_multi_level(
                key_type="vector_store",
                resource_id=collection_id,
                value=vector_store,
                tenant_id=tenant_id,
                ttl=600
            )
            
        return vector_store
    except Exception as e:
        logger.error(f"Error obteniendo vector store: {str(e)}")
        return None

async def invalidate_vector_store_cache(tenant_id: str, collection_id: str) -> bool:
    """
    Invalida la caché del vector store para una colección.
    
    Esta función debe llamarse cuando se modifican documentos en una colección.
    """
    from common.cache.contextual import invalidate_cache_hierarchy
    
    try:
        # Invalidar toda la caché relacionada con esta colección
        deleted = await invalidate_cache_hierarchy(
            tenant_id=tenant_id,
            key_type="vector_store",
            collection_id=collection_id
        )
        
        logger.info(f"Caché de vector store invalidada para colección {collection_id}: {deleted} claves")
        return True
    except Exception as e:
        logger.error(f"Error invalidando caché de vector store: {str(e)}")
        return False