"""
Funciones para almacenamiento y gestión de documentos en Supabase.

Este módulo proporciona funciones centralizadas para:
- Actualización de estados de documentos
- Gestión de trabajos de procesamiento
- Invalidación coordinada de cachés
- Acceso a documentos con caché optimizada
- Descarga de archivos desde Storage
"""

import logging
import os
import tempfile
import uuid
from typing import Dict, Any, Optional, List, Tuple
from supabase.storage import StorageException

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import ServiceError, DocumentProcessingError, handle_errors, ErrorCode
from common.cache import (
    get_with_cache_aside,
    generate_resource_id_hash,
    invalidate_document_update,
    CacheManager
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
        ctx: Contexto de la operación
        
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
        
        # Invalidar caché si se actualizó correctamente
        try:
            # Utilizar CacheManager directamente para invalidar el recurso
            await CacheManager.invalidate(
                data_type="document",
                resource_id=document_id,
                tenant_id=tenant_id
            )
        except Exception as cache_error:
            # No fallar si hay error de caché, solo registrar
            logger.warning(f"Error invalidando caché para documento {document_id}: {str(cache_error)}")
            
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
        ctx: Contexto de la operación
        
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
            # Usar CacheManager directamente
            await CacheManager.set(
                data_type="job_status",
                resource_id=str(job_id),
                value={
                    "status": status,
                    "progress": progress,
                    "error": error,
                    "stats": processing_stats
                },
                tenant_id=tenant_id,
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

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def download_file_from_storage(
    tenant_id: str,
    file_key: str,
    ctx: Context = None
) -> str:
    """
    Descarga un archivo desde Supabase Storage y lo guarda temporalmente.
    
    Implementa el patrón Cache-Aside para evitar descargas innecesarias
    de archivos previamente procesados.
    
    Args:
        tenant_id: ID del tenant propietario del archivo
        file_key: Clave del archivo en Storage (ruta completa)
        ctx: Contexto de la operación proporcionado por with_context
        
    Returns:
        str: Ruta al archivo temporal descargado
        
    Raises:
        ServiceError: Si hay problemas al descargar el archivo
    """
    # Asegurar que tenemos un tenant_id válido
    if ctx and ctx.has_tenant_id():
        tenant_id = ctx.get_tenant_id()
        
    if not tenant_id:
        raise ServiceError(
            message="Se requiere un tenant_id válido para descargar archivos",
            error_code="TENANT_REQUIRED",
            status_code=400
        )
    
    # Generar un identificador único para este archivo que usaremos como clave de caché
    # Esto sigue el estándar de caché del sistema
    cache_key = generate_resource_id_hash(file_key)
    
    # PASO 1: Verificar si ya tenemos en caché la ubicación de este archivo
    # Implementación del patrón Cache-Aside
    cached_path = await CacheManager.get(
        data_type="file",
        resource_id=cache_key,
        tenant_id=tenant_id
    )
    
    # Si encontramos el archivo en caché y existe en el sistema de archivos, retornarlo
    if cached_path and os.path.exists(cached_path):
        logger.info(f"Archivo encontrado en caché: {cached_path}")
        return cached_path
    
    # PASO 2: No está en caché o el archivo fue eliminado, descargar de nuevo
    # Crear directorio temporal con nombre único basado en tenant y timestamp
    temp_dir = tempfile.mkdtemp(prefix=f"ingestion_{tenant_id}_")
    
    # Extraer nombre de archivo desde file_key
    filename = os.path.basename(file_key)
    if not filename:
        filename = f"file_{uuid.uuid4().hex}"  # Generar un nombre si no se puede extraer
    
    # Construir ruta completa al archivo temporal
    temp_file_path = os.path.join(temp_dir, filename)
    
    try:
        # Obtener cliente de Supabase
        supabase = get_supabase_client()
        
        # Separar bucket y path dentro del bucket desde file_key
        # Formato esperado: bucket_name/path/to/file.ext
        parts = file_key.split('/', 1)
        if len(parts) < 2:
            raise ServiceError(
                message=f"Formato de file_key inválido: {file_key}",
                error_code="INVALID_FILE_KEY",
                status_code=400
            )
            
        bucket_name, object_path = parts
        
        # Descargar archivo
        start_time = time.time()
        logger.info(f"Descargando archivo {object_path} desde bucket {bucket_name}")
        
        with open(temp_file_path, 'wb+') as f:
            res = supabase.storage.from_(bucket_name).download(object_path)
            f.write(res)
        
        download_time = time.time() - start_time
        
        # Verificar que el archivo se descargó correctamente
        if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
            raise ServiceError(
                message="Archivo descargado vacío o no existente",
                error_code="DOWNLOAD_ERROR",
                status_code=500
            )
        
        # PASO 3: Guardar en caché la ubicación del archivo con TTL adecuado
        # Usar el TTL estándar según el tipo de dato (archivo)
        await CacheManager.set(
            data_type="file",
            resource_id=cache_key,
            value=temp_file_path,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_extended  # 24 horas para archivos
        )
            
        logger.info(f"Archivo descargado exitosamente en {temp_file_path} en {download_time:.2f}s")
        return temp_file_path
        
    except StorageException as e:
        # Limpiar directorio temporal en caso de error
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        # Propagar error con contexto enriquecido
        raise ServiceError(
            message=f"Error al descargar archivo desde Storage: {str(e)}",
            error_code="STORAGE_ERROR",
            status_code=500,
            details={
                "tenant_id": tenant_id,
                "file_key": file_key,
                "original_error": str(e)
            }
        ) from e
    except Exception as e:
        # Limpiar directorio temporal en caso de error
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        # Propagar cualquier otro error
        raise ServiceError(
            message=f"Error inesperado al descargar archivo: {str(e)}",
            error_code="DOWNLOAD_ERROR",
            status_code=500,
            details={
                "tenant_id": tenant_id,
                "file_key": file_key
            }
        ) from e
