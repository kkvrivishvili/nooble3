"""
Funciones para almacenamiento y gestión de vectores en Supabase.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import ServiceError, DocumentProcessingError
from common.cache.manager import CacheManager

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
        
        # Actualizar caché si se actualizó correctamente
        cache_key = f"document:{tenant_id}:{document_id}"
        try:
            # Intentar actualizar en caché para futuras consultas
            await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="document",
                resource_id=document_id
            )
        except Exception as cache_error:
            # No fallar si hay error de caché, solo registrar
            logger.warning(f"Error actualizando caché para documento {document_id}: {str(cache_error)}")
            
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
        
        # Actualizar caché para futura referencia rápida
        try:
            cache_key = f"job:{tenant_id}:{job_id}"
            
            # Guardar/actualizar el estado en caché para consultas rápidas
            await CacheManager.set(
                tenant_id=tenant_id,
                data_type="job_status",
                resource_id=str(job_id),
                value={
                    "status": status,
                    "progress": progress,
                    "error": error,
                    "stats": processing_stats
                },
                ttl=86400  # 24 horas
            )
            
        except Exception as cache_error:
            # No fallar si hay error de caché, solo registrar
            logger.warning(f"Error actualizando caché para trabajo {job_id}: {str(cache_error)}")
            
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
        # Usar CacheManager directamente para invalidar caché
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
        # Intentar continuar a pesar del error de caché
        return False

async def get_document_with_cache(document_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un documento con caché para mejorar rendimiento.
    
    Args:
        document_id: ID del documento
        tenant_id: ID del tenant
        
    Returns:
        Optional[Dict[str, Any]]: Datos del documento o None si no existe
    """
    try:
        # Primero intentar obtener de la caché
        cached_doc = await CacheManager.get(
            tenant_id=tenant_id,
            data_type="document",
            resource_id=document_id
        )
        
        if cached_doc:
            logger.debug(f"Documento {document_id} obtenido de caché")
            return cached_doc
        
        # Si no está en caché, obtener de Supabase
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("documents")) \
            .select("*") \
            .eq("document_id", document_id) \
            .eq("tenant_id", tenant_id) \
            .single() \
            .execute()
            
        if result.error:
            logger.error(f"Error obteniendo documento: {result.error}")
            return None
            
        document = result.data
        
        if document:
            # Guardar en caché para futuras consultas
            await CacheManager.set(
                tenant_id=tenant_id,
                data_type="document",
                resource_id=document_id,
                value=document,
                ttl=3600  # 1 hora
            )
            
        return document
        
    except Exception as e:
        logger.error(f"Error obteniendo documento con caché: {str(e)}")
        
        # Si hay error de caché, intentar obtener directamente de Supabase
        try:
            supabase = get_supabase_client()
            result = await supabase.table(get_table_name("documents")) \
                .select("*") \
                .eq("document_id", document_id) \
                .eq("tenant_id", tenant_id) \
                .single() \
                .execute()
                
            if result.error:
                return None
                
            return result.data
        except:
            return None