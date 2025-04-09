"""
Sistema de colas para procesamiento asíncrono de documentos.
"""

import json
import logging
import time
import uuid
import asyncio
from typing import Dict, Any, Optional, List

from common.cache.redis import get_redis_client
from common.cache.manager import CacheManager
from common.errors import ServiceError, DocumentProcessingError
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

from config import get_settings
from services.extraction import process_file_from_storage
from services.chunking import split_document_intelligently
from services.embedding import process_and_store_chunks
from services.storage import update_document_status, update_processing_job
from common.context.vars import validate_tenant_context

logger = logging.getLogger(__name__)
settings = get_settings()

# Nombre de la cola
INGESTION_QUEUE = "ingestion_queue"
JOB_PREFIX = "job:"
JOB_STATUS_PREFIX = "job_status:"
JOB_LOCK_PREFIX = "job_lock:"  # Prefijo para los bloqueos de trabajos
JOB_LOCK_EXPIRY = 600  # 10 minutos en segundos (tiempo máximo para procesar un trabajo)

async def initialize_queue():
    """Inicializa el sistema de colas."""
    # Comprobar la disponibilidad del servicio de caché mediante CacheManager
    try:
        # Intentar una operación simple para verificar disponibilidad
        test_value = await CacheManager.get(
            data_type="system",
            resource_id="queue_test"
        )
        
        logger.info("Sistema de colas inicializado correctamente")
        return True
    except Exception as e:
        logger.warning(f"Redis no disponible - procesamiento asíncrono deshabilitado: {str(e)}")
        return False

async def shutdown_queue():
    """Limpia recursos del sistema de colas."""
    # No se requiere acción específica para cerrar CacheManager
    logger.info("Sistema de colas cerrado correctamente")

async def queue_document_processing_job(
    tenant_id: str,
    document_id: str,
    file_key: str,
    metadata: Optional[Dict] = None
) -> bool:
    """
    Encola un trabajo de procesamiento de documento.
    
    Args:
        tenant_id: ID del tenant
        document_id: ID del documento
        file_key: Clave del archivo en storage
        metadata: Metadatos adicionales
        
    Returns:
        bool: True si se encoló correctamente
    """
    try:
        supabase = get_supabase_client()
        
        result = await supabase.table(get_table_name("processing_jobs")) \
            .insert({
                "tenant_id": tenant_id,
                "document_id": document_id,
                "file_key": file_key,
                "metadata": metadata or {},
                "status": "pending"
            }) \
            .execute()
            
        if result.error:
            logger.error(f"Error encolando trabajo: {result.error}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error inesperado encolando trabajo: {str(e)}")
        return False

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
            lock_key = f"{JOB_LOCK_PREFIX}{job_id}"
            lock_exists = await CacheManager.exists(
                data_type="system",
                resource_id=lock_key
            )
            
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
                                await CacheManager.delete(
                                    data_type="system",
                                    resource_id=lock_key
                                )
                                
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
                                await CacheManager.delete(
                                    data_type="system",
                                    resource_id=lock_key
                                )
                                
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

async def process_next_job() -> bool:
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
    
    try:
        # Parsear los datos del trabajo
        job = json.loads(job_data)
        job_id = job.get("job_id")
        tenant_id = job.get("tenant_id")
        
        # Validar que el tenant sea válido para procesar trabajos
        tenant_id = validate_tenant_context(tenant_id)
        
        # Adquirir un lock para este trabajo
        lock_key = f"{JOB_LOCK_PREFIX}:{job_id}"
        lock_acquired = await CacheManager.set_nx(lock_key, "1", job_lock_expire_seconds)
        
        if not lock_acquired:
            logger.warning(
                f"Lock no adquirido para job_id={job_id}, otro worker podría estar procesándolo", 
                extra={"job_id": job_id, "tenant_id": tenant_id}
            )
            return True  # Consideramos el trabajo como procesado y seguimos
        
        # Inicializar variables antes del bloque try para evitar referencias indefinidas en caso de excepción
        document_id = job.get("document_id")
        file_key = job.get("file_key")  # Nueva referencia a Supabase Storage
        collection_id = job.get("collection_id")
        
        # Validar que todos los campos requeridos existan
        required_fields = {"job_id": job_id, "tenant_id": tenant_id, "document_id": document_id, 
                          "file_key": file_key, "collection_id": collection_id}
        
        missing_fields = [field for field, value in required_fields.items() if not value]
        
        if missing_fields:
            error_msg = f"Campos requeridos faltantes en el trabajo: {', '.join(missing_fields)}"
            logger.error(error_msg)
            
            # Si tenemos suficiente información, actualizar el estado del trabajo
            if job_id and tenant_id:
                await update_processing_job(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    status="failed",
                    error=error_msg
                )
                
                # Si también tenemos document_id, actualizar el estado del documento
                if document_id:
                    await update_document_status(
                        document_id=document_id,
                        tenant_id=tenant_id,
                        status="failed",
                        metadata={"error": error_msg}
                    )
            
            return False
            
        # Actualizar el estado del trabajo a "processing" para indicar que está en progreso
        await update_processing_job(
            job_id=job_id,
            tenant_id=tenant_id,
            status="processing"
        )

        # Procesar usando el nuevo servicio unificado
        processed_text = await process_file_from_storage(
            tenant_id=tenant_id,
            collection_id=collection_id,
            file_key=file_key
        )

        # Dividir en chunks y generar embeddings
        chunks = await split_document_intelligently(
            text=processed_text,
            document_id=document_id,
            metadata={"tenant_id": tenant_id, "collection_id": collection_id}
        )
        
        await process_and_store_chunks(
            chunks=chunks,
            document_id=document_id,
            tenant_id=tenant_id,
            collection_id=collection_id
        )

        # Actualizar estados
        await update_processing_job(
            job_id=job_id,
            tenant_id=tenant_id,
            status="completed"
        )

        await update_document_status(
            document_id=document_id,
            tenant_id=tenant_id,
            status="processed",
            metadata={"chunks_count": len(chunks)}
        )

        # Limpiar recursos
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

        # Liberar el bloqueo después de procesar el trabajo con éxito
        lock_key = f"{JOB_LOCK_PREFIX}:{job_id}"
        await CacheManager.delete(data_type="system", resource_id=lock_key)
        
        return True

    except Exception as e:
        logger.error(f"Error procesando trabajo {job_id}: {str(e)}", exc_info=True)

        error_message = str(e)

        # Actualizar estado del trabajo a fallido
        await update_processing_job(
            job_id=job_id,
            tenant_id=tenant_id,
            status="failed",
            error=error_message
        )

        # Actualizar estado del documento
        await update_document_status(
            document_id=document_id,
            tenant_id=tenant_id,
            status="failed",
            metadata={"error": error_message}
        )

        # Limpiar recursos
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
        
        # Liberar el bloqueo si lo habíamos adquirido
        if job_id:
            lock_key = f"{JOB_LOCK_PREFIX}:{job_id}"
            await CacheManager.delete(data_type="system", resource_id=lock_key)

        return False