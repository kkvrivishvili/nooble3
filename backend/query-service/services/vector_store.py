"""
Gestión de búsqueda vectorial.
"""

import logging
from typing import List, Dict, Any, Optional

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import ServiceError
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def search_by_embedding(
    tenant_id: str,
    collection_id: str,
    query_embedding: List[float],
    top_k: int = 4,
    threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Busca documentos por similitud vectorial.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        query_embedding: Vector de búsqueda
        top_k: Número de resultados
        threshold: Umbral mínimo de similitud
        
    Returns:
        Lista de documentos con similitud
    """
    try:
        supabase = await get_supabase_client()
        
        # Usar RPC para búsqueda vectorial
        response = await supabase.rpc(
            'match_documents',
            {
                'query_embedding': query_embedding,
                'match_count': top_k,
                'filter': {
                    'tenant_id': tenant_id,
                    'collection_id': collection_id
                },
                'threshold': threshold
            }
        ).execute()
        
        if not response.data:
            return []
        
        # Formatear resultados
        results = []
        for doc in response.data:
            results.append({
                'id': doc['id'],
                'content': doc['content'],
                'metadata': doc.get('metadata', {}),
                'similarity': doc['similarity']
            })
        
        logger.info(f"Encontrados {len(results)} documentos similares")
        return results
        
    except Exception as e:
        logger.error(f"Error en búsqueda vectorial: {str(e)}")
        raise ServiceError(f"Error buscando documentos: {str(e)}")

async def get_collection_info(tenant_id: str, collection_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene información de una colección."""
    try:
        supabase = await get_supabase_client()
        table = get_table_name("collections")
        
        response = await supabase.table(table)\
            .select("*")\
            .eq("id", collection_id)\
            .eq("tenant_id", tenant_id)\
            .single()\
            .execute()
        
        return response.data if response.data else None
        
    except Exception as e:
        logger.error(f"Error obteniendo colección: {str(e)}")
        return None
