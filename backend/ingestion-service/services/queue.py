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

logger = logging.getLogger(__name__)
settings = get_settings()

# Nombre de la cola
INGESTION_QUEUE = "ingestion_queue"
JOB_PREFIX = "job:"
JOB_STATUS_PREFIX = "job_status:"

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
            
            # Verificar si el trabajo está estancado
            job_data = await CacheManager.get(
                tenant_id=tenant_id,
                data_type="job_status",
                resource_id=str(job_id)
            )
            
            if not job_data:
                # El trabajo no está en la cola, pero está en estado processing
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
    """Procesa el siguiente trabajo en la cola usando Supabase Storage"""
    # Utilizamos CacheManager para operaciones de cola para mantener consistencia
    
    job_data = await CacheManager.lpop(queue_name=INGESTION_QUEUE)
    if not job_data:
        return False

    # Inicializar variables antes del bloque try para evitar referencias indefinidas en caso de excepción
    job_id = None
    tenant_id = None
    document_id = None
    
    try:
        job = json.loads(job_data)
        job_id = job.get("job_id")
        tenant_id = job.get("tenant_id")
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

        return False