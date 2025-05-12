"""
Funciones para almacenamiento y gestión de vectores en Supabase.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import ServiceError, DocumentProcessingError, handle_errors
from common.cache import (
    get_with_cache_aside,
    generate_resource_id_hash,
    invalidate_document_update,


)
from common.context import with_context, Context

logger = logging.getLogger(__name__)

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def update_document_status(
    document_id: str,
    tenant_id: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Context = None
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
        try:
            # Utilizar función centralizada para invalidar recursos
            await invalidate_resource(
                data_type="document",
                resource_id=document_id,
                tenant_id=tenant_id,
                metadata={"update_type": "status_change"}
            )
        except Exception as cache_error:
            # No fallar si hay error de caché, solo registrar
            logger.warning(f"Error actualizando caché para documento {document_id}: {str(cache_error)}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado del documento: {str(e)}")
        return False

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def update_processing_job(
    job_id: str,
    tenant_id: str,
    status: str,
    progress: float = None,
    error: str = None,
    processing_stats: Dict[str, Any] = None,
    ctx: Context = None
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
            # Usar función centralizada para almacenar recursos en caché
            await set_resource(
                data_type="job_status",
                resource_id=str(job_id),
                value={
                    "status": status,
                    "progress": progress,
                    "error": error,
                    "stats": processing_stats
                },
                tenant_id=tenant_id,
                metadata={"operation": "job_update"},
                ttl=24*60*60  # 24 horas (en segundos)
            )
            
        except Exception as cache_error:
            # No fallar si hay error de caché, solo registrar
            logger.warning(f"Error actualizando caché para trabajo {job_id}: {str(cache_error)}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado del trabajo: {str(e)}")
        return False

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=False, convert_exceptions=False)
async def invalidate_vector_store_cache(tenant_id: str, collection_id: str, ctx: Context = None) -> bool:
    """
    Invalida la caché del vector store para una colección específica.
    
    Utiliza el enfoque centralizado para la invalidación de caché,
    garantizando consistencia en todos los servicios según el patrón
    establecido en las memorias del sistema.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto de la operación
        
    Returns:
        bool: True si se invalidó correctamente
    """
    try:
        # Utilizar la función centralizada para invalidación coordinada
        # Esta función maneja automáticamente la invalidación de:
        # 1. Vector stores relacionados con la colección
        # 2. Consultas previas que usaron esta colección
        results = await invalidate_document_update(
            tenant_id=tenant_id,
            collection_id=collection_id
        )
        
        # Registrar métricas de invalidación
        if ctx:
            ctx.add_metric("cache_invalidation", {
                "collection_id": collection_id,
                "tenant_id": tenant_id,
                "results": results
            })
        
        logger.info(f"Invalidación coordinada aplicada para colección {collection_id}: {results}")
        return True
        
    except Exception as e:
        logger.error(f"Error en invalidación coordinada: {str(e)}")
        return False

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def get_document_with_cache(document_id: str, tenant_id: str, ctx: Context = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene un documento con caché para mejorar rendimiento.
    
    Implementa el patrón Cache-Aside centralizado para optimizar la recuperación
    de documentos y mantener consistencia con otros servicios.
    
    Args:
        document_id: ID del documento
        tenant_id: ID del tenant
        ctx: Contexto de la operación
        
    Returns:
        Optional[Dict[str, Any]]: Datos del documento o None si no existe
    """
    # Función para obtener el documento de Supabase
    async def fetch_document_from_db(resource_id, tenant_id, ctx=None):
        try:
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
                
            return result.data
        except Exception as e:
            logger.error(f"Error obteniendo documento de Supabase: {str(e)}")
            return None
    
    # Usar la implementación centralizada del patrón Cache-Aside
    result, metrics = await get_with_cache_aside(
        data_type="document",
        resource_id=document_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_document_from_db,
        generate_func=None,  # No necesitamos generar documentos si no existen
        ctx=ctx
    )
    
    # Si tenemos contexto, añadir métricas para análisis
    if ctx:
        ctx.add_metric("document_cache_metrics", metrics)
    
    return result