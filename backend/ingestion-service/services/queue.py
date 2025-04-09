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
from common.errors import ServiceError, DocumentProcessingError
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

from config import get_settings
from services.document_processor import process_file, process_url, process_text, process_file_from_storage
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
    redis = await get_redis_client()
    if not redis:
        logger.warning("Redis no disponible - procesamiento asíncrono deshabilitado")
        return False
    
    logger.info("Sistema de colas inicializado correctamente")
    return True

async def shutdown_queue():
    """Limpia recursos del sistema de colas."""
    redis = await get_redis_client()
    if not redis:
        return
    
    # Aquí se podrían realizar tareas de limpieza si es necesario
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
    redis = await get_redis_client()
    if not redis:
        return
    
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
            job_data_str = await redis.get(f"{JOB_STATUS_PREFIX}{job_id}")
            if not job_data_str:
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
    redis = await get_redis_client()
    if not redis:
        logger.error("Redis no disponible")
        return False

    job_data = await redis.lpop(INGESTION_QUEUE)
    if not job_data:
        return False

    try:
        job = json.loads(job_data)
        job_id = job.get("job_id")
        tenant_id = job.get("tenant_id")
        document_id = job.get("document_id")
        file_key = job.get("file_key")  # Nueva referencia a Supabase Storage

        # Procesar usando el nuevo servicio unificado
        processed_text = await process_file_from_storage(
            tenant_id=tenant_id,
            collection_id=job.get("collection_id"),
            file_key=file_key
        )

        # Dividir en chunks y generar embeddings
        chunks = split_document_intelligently(processed_text)
        await process_and_store_chunks(
            chunks=chunks,
            document_id=document_id,
            tenant_id=tenant_id,
            metadata=job
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
        await redis.delete(
            f"{JOB_PREFIX}{job_id}:file", 
            f"{JOB_PREFIX}{job_id}:text",
            f"{JOB_PREFIX}{job_id}:data"
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
        if redis:
            await redis.delete(
                f"{JOB_PREFIX}{job_id}:file", 
                f"{JOB_PREFIX}{job_id}:text",
                f"{JOB_PREFIX}{job_id}:data"
            )

        return False