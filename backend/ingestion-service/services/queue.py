"""
Sistema de colas para procesamiento asíncrono de documentos.
"""

import json
import logging
import time
import uuid
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
    collection_id: str,
    file_content: bytes = None,
    text_content: str = None,
    url: str = None,
    file_info: Dict[str, Any] = None,
    batch_id: Optional[str] = None
) -> str:
    """
    Encola un trabajo de procesamiento de documento.
    
    Args:
        tenant_id: ID del tenant
        document_id: ID del documento
        collection_id: ID de la colección
        file_content: Contenido del archivo en bytes (opcional)
        text_content: Contenido de texto (opcional)
        url: URL a procesar (opcional)
        file_info: Información del archivo
        batch_id: ID del lote (opcional)
        
    Returns:
        str: ID del trabajo
    """
    # Verificar que se proporcionó al menos una fuente de contenido
    if not file_content and not text_content and not url:
        raise ServiceError(
            message="Se debe proporcionar contenido de archivo, texto o URL",
            error_code="MISSING_CONTENT_SOURCE"
        )
    
    # Generar ID para el trabajo
    job_id = str(uuid.uuid4())
    
    try:
        # Crear registro del trabajo en la base de datos
        job_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "collection_id": collection_id,
            "status": "pending",
            "progress": 0,
            "file_info": file_info or {},
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        if batch_id:
            job_data["batch_id"] = batch_id
        
        # Guardar en Supabase
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("processing_jobs")).insert(job_data).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error creando trabajo de procesamiento: {result.error}",
                error_code="JOB_CREATION_ERROR"
            )
        
        # Actualizar estado del documento a "pending"
        await update_document_status(document_id, tenant_id, "pending")
        
        # Preparar datos para la cola
        queue_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "collection_id": collection_id,
            "has_file": file_content is not None,
            "has_text": text_content is not None,
            "has_url": url is not None,
            "file_type": file_info.get("type") if file_info else None,
            "url": url,
            "batch_id": batch_id,
            "created_at": time.time()
        }
        
        # Encolar trabajo
        redis = await get_redis_client()
        if not redis:
            raise ServiceError(
                message="Cola de procesamiento no disponible",
                error_code="QUEUE_UNAVAILABLE"
            )
        
        # Guardar el archivo/texto en Redis temporalmente
        if file_content:
            await redis.set(
                f"{JOB_PREFIX}{job_id}:file", 
                file_content,
                ex=settings.queue_ttl
            )
        
        if text_content:
            await redis.set(
                f"{JOB_PREFIX}{job_id}:text", 
                text_content,
                ex=settings.queue_ttl
            )
        
        # Guardar datos del trabajo en Redis
        await redis.set(
            f"{JOB_PREFIX}{job_id}:data",
            json.dumps(queue_data),
            ex=settings.queue_ttl
        )
        
        # Encolar el trabajo
        await redis.lpush(INGESTION_QUEUE, json.dumps(queue_data))
        
        # Establecer estado inicial
        await redis.set(
            f"{JOB_STATUS_PREFIX}{job_id}",
            json.dumps({"status": "pending", "progress": 0}),
            ex=settings.queue_ttl
        )
        
        logger.info(f"Trabajo {job_id} encolado para documento {document_id}")
        return job_id
        
    except Exception as e:
        logger.error(f"Error encolando trabajo: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(
            message=f"Error encolando trabajo: {str(e)}",
            error_code="QUEUE_ERROR"
        )

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