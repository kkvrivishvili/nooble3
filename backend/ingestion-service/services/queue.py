"""
Sistema de colas para procesamiento asíncrono de documentos.
"""

import json
import logging
import time
import uuid
import asyncio
from typing import Dict, Any, Optional, List

from common.config import get_settings, get_tier_limits
from common.errors import ServiceError, handle_errors, ErrorCode
from common.context import Context, with_context, get_full_context
from common.db import get_supabase_client
from common.db.tables import get_table_name
from common.cache.manager import CacheManager
from services.storage import update_document_status, update_processing_job
from services.extraction import extract_text_from_file, validate_file, get_extractor_for_mimetype

# Importar servicios de LlamaIndex
from services.llama_core import (
    split_text_with_llama_index, 
    generate_embeddings_with_llama_index,
    store_chunks_in_vector_store,
    load_and_process_file_with_llama_index,
    validate_file_with_llama_index
)
from services.llama_extractors import process_upload_with_llama_index, process_text_with_llama_index

logger = logging.getLogger(__name__)
settings = get_settings()

# Nombre de la cola
INGESTION_QUEUE = "ingestion_queue"
JOB_PREFIX = "job:"
JOB_STATUS_PREFIX = "job_status:"
JOB_LOCK_PREFIX = "job_lock"  # Prefijo para los bloqueos de trabajos
JOB_LOCK_EXPIRY = 600  # 10 minutos en segundos (tiempo máximo para procesar un trabajo)

async def initialize_queue():
    """Inicializa el sistema de colas."""
    # Comprobar la disponibilidad del servicio de caché mediante CacheManager
    try:
        # Intentar una operación simple para verificar disponibilidad
        try:
            test_value = await CacheManager.get(
                data_type="system",
                resource_id="queue_test"
            )
        except Exception as cache_err:
            logger.warning(f"CacheManager no disponible: {str(cache_err)}")
            test_value = None
        
        if test_value is not None:
            logger.info("Sistema de colas inicializado correctamente")
            return True
        else:
            logger.warning("Redis no disponible - procesamiento asíncrono deshabilitado")
            return False
    except Exception as e:
        logger.warning(f"Redis no disponible - procesamiento asíncrono deshabilitado: {str(e)}")
        return False

async def shutdown_queue():
    """Limpia recursos del sistema de colas."""
    # No se requiere acción específica para cerrar CacheManager
    logger.info("Sistema de colas cerrado correctamente")

@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def queue_document_processing_job(
    tenant_id: str,
    document_id: str,
    collection_id: str,
    file_key: str = None,
    url: str = None,
    text_content: str = None,
    file_info: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Context = None
) -> str:
    """
    Encola un trabajo de procesamiento de documento.
    
    Args:
        tenant_id: ID del tenant
        document_id: ID del documento
        collection_id: ID de la colección a la que pertenece el documento
        file_key: Clave del archivo en storage (para archivos subidos)
        url: URL del documento (para ingestión desde URLs)
        text_content: Texto del documento (para ingestión de texto plano)
        file_info: Información del archivo (tipo, tamaño, etc.)
        metadata: Metadatos adicionales del documento
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        str: ID del trabajo creado
        
    Raises:
        ServiceError: Si hay un error al encolar el trabajo
    """
    job_id = str(uuid.uuid4())
    
    try:
        # Tenant ya validado por el decorador with_context
        # El parámetro tenant_id tiene prioridad sobre el contexto
        if tenant_id is None:
            tenant_id = ctx.get_tenant_id()
        
        # Construir los datos completos del trabajo
        job_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "collection_id": collection_id,
            "status": "pending",
            "created_at": int(time.time()),
            "metadata": metadata or {}
        }
        
        # Agregar información específica según el tipo de fuente
        if file_key:
            job_data["file_key"] = file_key
            job_data["source_type"] = "file"
        elif url:
            job_data["url"] = url
            job_data["source_type"] = "url"
        elif text_content:
            job_data["text_content"] = text_content
            job_data["source_type"] = "text"
        else:
            logger.error("Se requiere al menos una fuente: file_key, url o text_content")
            raise ServiceError(
                message="Se requiere especificar una fuente para el documento",
                error_code="MISSING_DOCUMENT_SOURCE",
                status_code=400
            )
            
        # Almacenar información del archivo si se proporciona
        if file_info:
            job_data["file_info"] = file_info
        
        supabase = get_supabase_client()
        
        # Insertar trabajo en la tabla de trabajos de procesamiento
        result = await supabase.table(get_table_name("processing_jobs")) \
            .insert(job_data) \
            .execute()
            
        if result.error:
            logger.error(f"Error encolando trabajo: {result.error}")
            raise ServiceError(
                message=f"Error al encolar el trabajo: {result.error.message}",
                error_code="JOB_QUEUE_ERROR",
                status_code=500
            )
            
        # Encolar el trabajo en Redis para procesamiento con manejo de errores
        try:
            await CacheManager.rpush(
                INGESTION_QUEUE,
                json.dumps(job_data),
                tenant_id=tenant_id
            )
        except Exception as cache_err:
            logger.warning(f"Error al encolar en Redis: {str(cache_err)}")
            
        return job_id
    except ServiceError:
        # Re-lanzar ServiceError para mantener el contexto
        raise
    except Exception as e:
        logger.error(f"Error inesperado encolando trabajo: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado al encolar el trabajo: {str(e)}",
            error_code="JOB_QUEUE_ERROR",
            status_code=500
        )

async def check_stuck_jobs():
    """Verifica trabajos estancados y los marca como fallidos."""
    # Utilizamos CacheManager para operaciones de caché
    
    # Obtener todos los trabajos en estado "processing"
    try:
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("processing_jobs")) \
            .select("*") \
            .eq("status", "processing") \
            .execute()
        
        if not result.data:
            return
        
        current_time = time.time()
        max_processing_time = 3600  # 1 hora máximo
        
        for job in result.data:
            job_id = job.get("job_id")
            tenant_id = job.get("tenant_id")
            document_id = job.get("document_id")
            
            # NUEVO: Verificar si existe un bloqueo para este trabajo
            lock_key = f"{JOB_LOCK_PREFIX}:{job_id}"
            # Verificar bloqueo usando CacheManager.get en lugar de exists
            val = await CacheManager.get(
                data_type="lock",
                resource_id=lock_key,
                tenant_id=tenant_id
            )
            lock_exists = val is not None
            
            # Si el bloqueo no existe o ha expirado, el trabajo probablemente está estancado
            if not lock_exists:
                # Verificar el tiempo desde la última actualización
                if "updated_at" in job:
                    updated_time = job.get("updated_at")
                    # Convertir updated_at a timestamp si es string
                    if isinstance(updated_time, str):
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(updated_time.replace('Z', '+00:00'))
                            updated_timestamp = dt.timestamp()
                            
                            if current_time - updated_timestamp > max_processing_time:
                                # Trabajo estancado, marcarlo como fallido
                                logger.warning(f"Detectado trabajo estancado {job_id} para tenant {tenant_id}. Última actualización hace {current_time - updated_timestamp} segundos.")
                                
                                # Liberar explícitamente cualquier bloqueo antiguo que pudiera existir
                                try:
                                    await CacheManager.delete(
                                        data_type="lock",
                                        resource_id=lock_key,
                                        tenant_id=tenant_id
                                    )
                                except Exception as err:
                                    logger.debug(f"Error liberando lock Redis para job {job_id}: {err}")
                                
                                await update_processing_job(
                                    job_id=job_id,
                                    tenant_id=tenant_id,
                                    status="failed",
                                    error="Trabajo estancado - timeout excedido"
                                )
                                
                                await update_document_status(
                                    document_id=document_id,
                                    tenant_id=tenant_id,
                                    status="failed",
                                    metadata={"error": "Procesamiento interrumpido por timeout"}
                                )
                                
                                # Limpiar recursos asociados
                                await CacheManager.delete(
                                    data_type="job",
                                    resource_id=f"{job_id}:file",
                                    tenant_id=tenant_id
                                )
                                await CacheManager.delete(
                                    data_type="job",
                                    resource_id=f"{job_id}:text",
                                    tenant_id=tenant_id
                                )
                                await CacheManager.delete(
                                    data_type="job",
                                    resource_id=f"{job_id}:data",
                                    tenant_id=tenant_id
                                )
                        except Exception as parse_err:
                            logger.error(f"Error procesando timestamp: {str(parse_err)}")
                    
            else:
                # El bloqueo existe, pero verificamos si el tiempo de procesamiento es excesivo
                # Podríamos extender el bloqueo para jobs legítimamente complejos
                if "updated_at" in job:
                    updated_time = job.get("updated_at")
                    # Convertir updated_at a timestamp si es string
                    if isinstance(updated_time, str):
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(updated_time.replace('Z', '+00:00'))
                            updated_timestamp = dt.timestamp()
                            
                            # Para trabajos que han excedido por mucho el tiempo máximo, forzar limpieza
                            if current_time - updated_timestamp > (max_processing_time * 2):
                                logger.warning(f"Trabajo {job_id} excede el tiempo máximo por un margen excesivo. Forzando liberación.")
                                
                                # Forzar liberación del bloqueo
                                try:
                                    await CacheManager.delete(
                                        data_type="lock",
                                        resource_id=lock_key,
                                        tenant_id=tenant_id
                                    )
                                except Exception as err:
                                    logger.debug(f"Error liberando lock Redis forzado para job {job_id}: {err}")
                                
                                await update_processing_job(
                                    job_id=job_id,
                                    tenant_id=tenant_id,
                                    status="failed",
                                    error="Trabajo interrumpido por exceder tiempo máximo de procesamiento"
                                )
                                
                                await update_document_status(
                                    document_id=document_id,
                                    tenant_id=tenant_id,
                                    status="failed",
                                    metadata={"error": "Procesamiento interrumpido por exceder tiempo máximo"}
                                )
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"Error verificando trabajos estancados: {str(e)}", exc_info=True)

async def process_next_job_with_retry(max_retries: int = 3) -> bool:
    """Procesa el siguiente trabajo con sistema de reintentos."""
    for attempt in range(max_retries):
        try:
            return await process_next_job()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Intento {attempt + 1} fallido, reintentando...")
            await asyncio.sleep(2 ** attempt)  # Backoff exponencial
    return False

@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def process_next_job(ctx: Context = None) -> bool:
    """
    Procesa el siguiente trabajo de la cola de ingesta.
    
    Toma un trabajo de la cola, lo marca como en procesamiento, y
    llama al método de procesamiento correspondiente según el tipo de trabajo.
    
    Returns:
        bool: True si se procesó un trabajo, False si no había trabajos
        
    Raises:
        ServiceError: Si no hay un tenant válido en el contexto
    """
    settings = get_settings()
    job_lock_expire_seconds = settings.job_lock_expire_seconds
    
    # Tomar el siguiente trabajo de la cola
    job_data = await CacheManager.lpop(queue_name=INGESTION_QUEUE)
    
    if not job_data:
        return False  # No hay trabajos en la cola
    
    # Inicializar variables fuera del bloque try para usarlas en finally
    job_id = None
    tenant_id = None
    document_id = None
    lock_acquired = False
    lock_key = None
    
    try:
        # Parsear los datos del trabajo
        job = json.loads(job_data)
        job_id = job.get("job_id")
        tenant_id = job.get("tenant_id")
        document_id = job.get("document_id")
        collection_id = job.get("collection_id")
        file_key = job.get("file_key")  # Referencia a Supabase Storage
        url = job.get("url")            # URL si es ingestión web
        text_content = job.get("text_content")  # Contenido texto si es directo
        
        # Propagar contexto del trabajo para logging y errores
        async with Context(
            tenant_id=tenant_id,
            collection_id=collection_id
        ):
            # Crear contexto para logging y errores
            context = {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "collection_id": collection_id
            }
            
            # Validar que el tenant sea válido para procesar trabajos
            if tenant_id is None:
                tenant_id = ctx.get_tenant_id()
            
            # Adquirir un lock para este trabajo
            lock_key = f"{JOB_LOCK_PREFIX}:{job_id}"
            lock_acquired = await CacheManager.set(
                data_type="lock",
                resource_id=lock_key,
                value="1",
                tenant_id=tenant_id,
                ttl=job_lock_expire_seconds,
                nx=True
            )
            
            if not lock_acquired:
                logger.warning(
                    f"Lock no adquirido para job_id={job_id}, otro worker podría estar procesándolo", 
                    extra=context
                )
                return True  # Consideramos el trabajo como procesado y seguimos
            
            # Validar que tenemos la información necesaria según el tipo de fuente
            source_type = None
            if file_key:
                source_type = "file"
            elif url:
                source_type = "url"
            elif text_content:
                source_type = "text"
            else:
                error_msg = "Fuente de documento no especificada (se requiere file_key, url o text_content)"
                logger.error(error_msg, extra=context)
                
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error=error_msg
                )
                
                if document_id:
                    await update_document_status(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        status="failed",
                        metadata={"error": error_msg}
                    )
                    
                # No lanzamos excepción para permitir que el finally libere el lock
                return False
            
            context["source_type"] = source_type
            
            # Validar que tenemos la información básica necesaria
            if not document_id or not collection_id:
                missing = []
                if not document_id:
                    missing.append("document_id")
                if not collection_id:
                    missing.append("collection_id")
                    
                error_msg = f"Campos requeridos faltantes: {', '.join(missing)}"
                logger.error(error_msg, extra=context)
                
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error=error_msg
                )
                
                if document_id:
                    await update_document_status(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        status="failed",
                        metadata={"error": error_msg}
                    )
                    
                # No lanzamos excepción para permitir que el finally libere el lock
                return False
                
            # Actualizar el estado del trabajo a "processing"
            await update_processing_job(
                job_id=job_id,
                tenant_id=tenant_id,
                status="processing"
            )

            # Procesar según el tipo de fuente
            processed_text = None
            
            if source_type == "file":
                # Procesamiento de archivo almacenado
                processed_text = await process_upload_with_llama_index(
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    file_key=file_key
                )
            elif source_type == "url":
                # Aquí iría el procesamiento para URL (pendiente de implementar)
                raise ServiceError(
                    message="Procesamiento de URL no implementado",
                    error_code="NOT_IMPLEMENTED",
                    status_code=501,
                    context=context
                )
            elif source_type == "text":
                # El texto ya está disponible
                processed_text = await process_text_with_llama_index(
                    text=text_content,
                    tenant_id=tenant_id,
                    collection_id=collection_id
                )
            
            # Verificar que tenemos texto procesado
            if not processed_text:
                logger.error(f"No se pudo procesar el documento {document_id}")
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error="No se pudo extraer texto del documento",
                    ctx=ctx
                )
                await update_document_status(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    status="failed",
                    metadata={"error": "No se pudo extraer texto del documento"}
                )
                return False

            # Dividir en chunks y generar embeddings
            document_metadata = {
                "tenant_id": tenant_id, 
                "collection_id": collection_id,
                "document_id": document_id,
                "source_type": source_type,
                "job_id": job_id
            }
            
            logger.info(f"Dividiendo documento {document_id} en chunks")
            chunks = await split_text_with_llama_index(
                text=processed_text,
                document_id=document_id,
                metadata=document_metadata,
                ctx=ctx
            )
            
            if not chunks:
                logger.error(f"No se pudieron generar chunks para el documento {document_id}")
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error="No se pudieron generar chunks para el documento",
                    ctx=ctx
                )
                await update_document_status(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    status="failed",
                    metadata={"error": "No se pudieron generar chunks para el documento"}
                )
                return False
            
            logger.info(f"Almacenando {len(chunks)} chunks en vector store para documento {document_id}")
            processing_stats = await store_chunks_in_vector_store(
                chunks=chunks,
                document_id=document_id,
                tenant_id=tenant_id,
                collection_id=collection_id,
                ctx=ctx
            )
            
            # Actualizar estado del documento y trabajo a completado
            await update_document_status(
                document_id=document_id,
                tenant_id=tenant_id,
                status="completed",
                metadata={
                    "chunks_count": len(chunks),
                    "processing_stats": processing_stats
                }
            )
            
            await update_processing_job(
                job_id=job_id,
                tenant_id=tenant_id,
                status="completed",
                progress=100,
                processing_stats=processing_stats,
                ctx=ctx
            )
            
            logger.info(f"Procesamiento completado para documento {document_id}")
            return True
    except Exception as e:
        error_context = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "error": str(e)
        }
        
        logger.error(f"Error procesando trabajo: {str(e)}", extra=error_context, exc_info=True)

        try:
            # Solo intentar actualizar si tenemos la información mínima necesaria
            if job_id and tenant_id:
                error_message = str(e)
                
                # Actualizar estado del trabajo a fallido
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error=error_message
                )

                # Actualizar estado del documento si tenemos el ID
                if document_id:
                    await update_document_status(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        status="failed",
                        metadata={"error": error_message}
                    )
                    
                # Limpiar recursos de caché asociados al trabajo
                await _cleanup_job_resources(job_id, tenant_id)
        except Exception as cleanup_error:
            # Si falla la limpieza, solo registrarlo pero continuar
            logger.error(f"Error en limpieza tras fallo: {str(cleanup_error)}", 
                        extra=error_context, 
                        exc_info=True)
        
        return False
    finally:
        # Garantizar que el lock se libere en cualquier circunstancia
        if lock_acquired and lock_key:
            try:
                await CacheManager.delete(
                    data_type="lock",
                    resource_id=lock_key,
                    tenant_id=tenant_id
                )
                logger.debug(f"Lock liberado para job_id={job_id}", extra={"job_id": job_id})
            except Exception as unlock_error:
                logger.error(f"Error liberando lock para job_id={job_id}: {str(unlock_error)}")

@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def get_job_status(job_id: str, tenant_id: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Obtiene el estado de un trabajo de procesamiento.
    
    Args:
        job_id: ID del trabajo
        tenant_id: ID del tenant
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        Dict[str, Any]: Información del estado del trabajo
        
    Raises:
        ServiceError: Si hay un error al obtener el estado del trabajo
    """
    # Validar el formato del ID del trabajo
    if not job_id or not tenant_id:
        raise ServiceError(
            code=ErrorCode.INVALID_PARAMETER,
            message="ID de trabajo o tenant no válido"
        )
    
    # Obtener el estado del trabajo de Redis
    try:
        # La clave del estado del trabajo incluye el prefijo, tenant y el ID
        status_key = f"{JOB_STATUS_PREFIX}{tenant_id}:{job_id}"
        
        # Intentar obtener el estado
        status_data = await CacheManager.get(
            data_type="system",
            resource_id=status_key
        )
        
        if not status_data:
            logger.warning(f"No se encontró información de estado para el trabajo {job_id}")
            return {
                "job_id": job_id,
                "status": "not_found",
                "message": "No se encontró información para este trabajo"
            }
            
        return status_data
        
    except Exception as e:
        logger.error(f"Error al obtener estado del trabajo {job_id}: {str(e)}")
        raise ServiceError(
            code=ErrorCode.DATABASE_ERROR,
            message=f"Error al obtener estado del trabajo: {str(e)}"
        )

@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def retry_failed_job(job_id: str, tenant_id: str, ctx: Context = None) -> bool:
    """
    Reintenta un trabajo fallido.
    
    Args:
        job_id: ID del trabajo
        tenant_id: ID del tenant
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        bool: True si se reintentó correctamente
        
    Raises:
        ServiceError: Si hay un error al reintentar el trabajo
    """
    # Obtener información actual del trabajo
    job_status = await get_job_status(job_id, tenant_id, ctx)
    
    if not job_status or job_status.get("status") == "not_found":
        raise ServiceError(
            code=ErrorCode.NOT_FOUND,
            message="Trabajo no encontrado"
        )
        
    if job_status.get("status") != "failed":
        raise ServiceError(
            code=ErrorCode.INVALID_STATE,
            message=f"No se puede reintentar un trabajo con estado '{job_status.get('status')}'"
        )
    
    # Restaurar el trabajo a la cola
    try:
        # Actualizar estado a 'pending'
        status_key = f"{JOB_STATUS_PREFIX}{tenant_id}:{job_id}"
        job_status["status"] = "pending"
        job_status["updated_at"] = time.time()
        job_status["retries"] = job_status.get("retries", 0) + 1
        
        # Guardar estado actualizado
        await CacheManager.set(
            data_type="system",
            resource_id=status_key,
            data=job_status
        )
        
        # Añadir trabajo nuevamente a la cola
        await CacheManager.push_to_list(
            data_type="system",
            resource_id=INGESTION_QUEUE,
            value=job_id
        )
        
        logger.info(f"Trabajo {job_id} reintentado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error al reintentar trabajo {job_id}: {str(e)}")
        raise ServiceError(
            code=ErrorCode.DATABASE_ERROR,
            message=f"Error al reintentar trabajo: {str(e)}"
        )

@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def cancel_job(job_id: str, tenant_id: str, ctx: Context = None) -> bool:
    """
    Cancela un trabajo pendiente o en proceso.
    
    Args:
        job_id: ID del trabajo
        tenant_id: ID del tenant
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        bool: True si se canceló correctamente
        
    Raises:
        ServiceError: Si hay un error al cancelar el trabajo
    """
    # Obtener información actual del trabajo
    job_status = await get_job_status(job_id, tenant_id, ctx)
    
    if not job_status or job_status.get("status") == "not_found":
        raise ServiceError(
            code=ErrorCode.NOT_FOUND,
            message="Trabajo no encontrado"
        )
        
    if job_status.get("status") in ["completed", "failed", "cancelled"]:
        raise ServiceError(
            code=ErrorCode.INVALID_STATE,
            message=f"No se puede cancelar un trabajo con estado '{job_status.get('status')}'"
        )
    
    # Marcar el trabajo como cancelado
    try:
        # Actualizar estado a 'cancelled'
        status_key = f"{JOB_STATUS_PREFIX}{tenant_id}:{job_id}"
        job_status["status"] = "cancelled"
        job_status["updated_at"] = time.time()
        job_status["message"] = "Trabajo cancelado por el usuario"
        
        # Guardar estado actualizado
        await CacheManager.set(
            data_type="system",
            resource_id=status_key,
            data=job_status
        )
        
        # Actualizar el documento asociado para reflejar la cancelación
        document_id = job_status.get("document_id")
        if document_id:
            await update_document_status(
                document_id=document_id,
                tenant_id=tenant_id,
                status="cancelled",
                metadata={"message": "Procesamiento cancelado por el usuario"}
            )
        
        # Limpiar recursos del trabajo
        await _cleanup_job_resources(job_id, tenant_id, ctx)
        
        logger.info(f"Trabajo {job_id} cancelado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error al cancelar trabajo {job_id}: {str(e)}")
        raise ServiceError(
            code=ErrorCode.DATABASE_ERROR,
            message=f"Error al cancelar trabajo: {str(e)}"
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True, convert_exceptions=False)
async def _cleanup_job_resources(job_id: str, tenant_id: str, ctx: Context = None):
    """
    Limpia los recursos temporales asociados a un trabajo.
    
    Args:
        job_id: ID del trabajo
        tenant_id: ID del tenant
    """
    try:
        # Limpiar recursos de caché asociados al trabajo
        await CacheManager.delete(
            data_type="job",
            resource_id=f"{job_id}:file",
            tenant_id=tenant_id
        )
        await CacheManager.delete(
            data_type="job",
            resource_id=f"{job_id}:text",
            tenant_id=tenant_id
        )
        await CacheManager.delete(
            data_type="job",
            resource_id=f"{job_id}:data",
            tenant_id=tenant_id
        )
    except Exception as e:
        # Solo registrar el error, no propagarlo
        logger.error(f"Error limpiando recursos del trabajo {job_id}: {str(e)}", 
                    extra={"job_id": job_id, "tenant_id": tenant_id},
                    exc_info=True)