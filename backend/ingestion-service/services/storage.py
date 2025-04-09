"""
Funciones para almacenamiento y gestión de vectores en Supabase.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import ServiceError, DocumentProcessingError

logger = logging.getLogger(__name__)

async def update_document_status(
    document_id: str,
    tenant_id: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Actualiza el estado de un documento.
    
    Args:
        document_id: ID del documento
        tenant_id: ID del tenant
        status: Nuevo estado (pending, processing, completed, failed)
        metadata: Metadatos adicionales a actualizar
        
    Returns:
        bool: True si se actualizó correctamente
    """
    try:
        supabase = get_supabase_client()
        
        # Preparar datos para actualización
        update_data = {"status": status}
        
        # Añadir metadatos adicionales si se proporcionan
        if metadata:
            for key, value in metadata.items():
                if key not in ["document_id", "tenant_id"]:
                    update_data[key] = value
        
        # Actualizar estado
        result = await supabase.table(get_table_name("documents")) \
            .update(update_data) \
            .eq("document_id", document_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
            
        if result.error:
            logger.error(f"Error actualizando estado del documento: {result.error}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado del documento: {str(e)}")
        return False

async def update_processing_job(
    job_id: str,
    tenant_id: str,
    status: str,
    progress: float = None,
    error: str = None,
    processing_stats: Dict[str, Any] = None
) -> bool:
    """
    Actualiza el estado de un trabajo de procesamiento.
    
    Args:
        job_id: ID del trabajo
        tenant_id: ID del tenant
        status: Nuevo estado (pending, processing, completed, failed, cancelled)
        progress: Porcentaje de progreso (0-100)
        error: Mensaje de error si falló
        processing_stats: Estadísticas de procesamiento
        
    Returns:
        bool: True si se actualizó correctamente
    """
    try:
        supabase = get_supabase_client()
        
        # Preparar datos para actualización
        update_data = {"status": status}
        
        if progress is not None:
            update_data["progress"] = progress
            
        if error is not None:
            update_data["error"] = error
            
        if processing_stats is not None:
            update_data["processing_stats"] = processing_stats
            
        # Añadir timestamp de finalización si completado o fallido
        if status in ["completed", "failed", "cancelled"]:
            update_data["completion_time"] = "NOW()"
        
        # Actualizar estado
        result = await supabase.table(get_table_name("processing_jobs")) \
            .update(update_data) \
            .eq("job_id", job_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
            
        if result.error:
            logger.error(f"Error actualizando estado del trabajo: {result.error}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado del trabajo: {str(e)}")
        return False

async def invalidate_vector_store_cache(tenant_id: str, collection_id: str) -> bool:
    """
    Invalida la caché del vector store para una colección específica.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        
    Returns:
        bool: True si se invalidó correctamente
    """
    try:
        from common.cache.manager import CacheManager
        
        # Invalidar caché para esta colección
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="query_result",
            collection_id=collection_id
        )
        
        # También invalidar vector_store si existe
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="vector_store",
            collection_id=collection_id
        )
        
        logger.info(f"Caché invalidada para colección {collection_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error invalidando caché: {str(e)}")
        return False