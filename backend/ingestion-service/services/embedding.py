"""
Funciones para generar embeddings para fragmentos de documentos.
"""

import logging
import time
from typing import List, Dict, Any, Optional

from common.errors import (
    ServiceError, EmbeddingGenerationError,
    EmbeddingModelError, TextTooLargeError
)
from common.utils.http import call_service
from common.config import get_settings
from common.cache.manager import CacheManager

logger = logging.getLogger(__name__)
settings = get_settings()

async def generate_embeddings_for_chunks(
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    model: Optional[str] = None,
    collection_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Genera embeddings para una lista de fragmentos.
    
    Args:
        chunks: Lista de fragmentos con texto y metadatos
        tenant_id: ID del tenant
        model: Modelo de embedding a utilizar
        collection_id: ID de la colección para caché
        
    Returns:
        List[Dict[str, Any]]: Lista de fragmentos con embeddings
    """
    if not chunks:
        return []
    
    model_name = model or settings.default_embedding_model
    
    try:
        # Preparar textos para el batch
        texts = [chunk["text"] for chunk in chunks]
        
        # Preparar solicitud al servicio de embeddings
        payload = {
            "model": model_name,
            "texts": texts,
            "tenant_id": tenant_id
        }
        
        if collection_id:
            payload["collection_id"] = collection_id
        
        # Llamar al servicio de embeddings
        response = await call_service(
            url=f"{settings.embedding_service_url}/internal/embed",
            data=payload,
            tenant_id=tenant_id,
            collection_id=collection_id,
            operation_type="embedding",
            use_cache=True,
            cache_ttl=86400  # 24 horas para embeddings
        )
        
        # Verificar respuesta y extraer embeddings
        if not response.get("success", False):
            error_info = response.get("error", {})
            error_msg = response.get("message", "Error desconocido generando embeddings")
            error_details = error_info.get("details", {})
            
            logger.error(f"Error en servicio de embeddings: {error_msg}")
            
            # Determinar tipo de error basado en el código
            error_code = error_details.get("error_code")
            if error_code == "TEXT_TOO_LARGE_ERROR":
                raise TextTooLargeError(
                    message=f"Texto demasiado grande para generar embeddings: {error_msg}",
                    details=error_details
                )
            elif error_code == "EMBEDDING_MODEL_ERROR":
                raise EmbeddingModelError(
                    message=f"Error con modelo de embedding: {error_msg}",
                    details=error_details
                )
            else:
                raise EmbeddingGenerationError(
                    message=f"Error generando embeddings: {error_msg}",
                    details=error_details
                )
        
        # Extraer embeddings y combinar con chunks originales
        embeddings = response.get("data", {}).get("embeddings", [])
        if len(embeddings) != len(chunks):
            logger.error(f"Error: cantidad de embeddings ({len(embeddings)}) diferente a chunks ({len(chunks)})")
            raise EmbeddingGenerationError(
                message="Cantidad de embeddings no coincide con cantidad de fragmentos",
                details={
                    "embeddings_count": len(embeddings),
                    "chunks_count": len(chunks)
                }
            )
        
        # Combinar embeddings con chunks originales
        chunks_with_embeddings = []
        for i, chunk in enumerate(chunks):
            chunks_with_embeddings.append({
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "embedding": embeddings[i]
            })
        
        return chunks_with_embeddings
        
    except Exception as e:
        logger.error(f"Error generando embeddings: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise EmbeddingGenerationError(
            message=f"Error inesperado generando embeddings: {str(e)}",
            details={"chunks_count": len(chunks) if chunks else 0}
        )

async def process_and_store_chunks(
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    collection_id: str,
    document_id: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Procesa fragmentos, genera embeddings y almacena en Supabase.
    
    Args:
        chunks: Lista de fragmentos con texto y metadatos
        tenant_id: ID del tenant
        collection_id: ID de la colección
        document_id: ID del documento
        model: Modelo de embeddings a utilizar
        
    Returns:
        Dict[str, Any]: Estadísticas del procesamiento
    """
    if not chunks:
        return {"chunks_processed": 0, "chunks_stored": 0}
    
    start_time = time.time()
    
    try:
        # Generar embeddings
        chunks_with_embeddings = await generate_embeddings_for_chunks(
            chunks=chunks,
            tenant_id=tenant_id,
            model=model,
            collection_id=collection_id
        )
        
        # Almacenar en Supabase
        from common.db.supabase import get_supabase_client
        from common.db.tables import get_table_name
        
        supabase = get_supabase_client()
        table_name = get_table_name("document_chunks")
        
        # Preparar datos para inserción
        chunks_to_insert = []
        for i, chunk in enumerate(chunks_with_embeddings):
            # Metadatos originales
            metadata = chunk["metadata"].copy()
            
            # Asegurarse de que metadatos tenga los campos necesarios
            if "document_id" not in metadata:
                metadata["document_id"] = document_id
            if "collection_id" not in metadata:
                metadata["collection_id"] = collection_id
            if "chunk_id" not in metadata:
                metadata["chunk_id"] = f"{document_id}_{i+1}"
            if "chunk_index" not in metadata:
                metadata["chunk_index"] = i
            
            # Preparar entrada para Supabase
            chunks_to_insert.append({
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "content": chunk["text"],
                "embedding": chunk["embedding"],
                "metadata": metadata
            })
        
        # Insertar en lotes para evitar problemas con RPC
        batch_size = 50
        stored_count = 0
        
        for i in range(0, len(chunks_to_insert), batch_size):
            batch = chunks_to_insert[i:i+batch_size]
            result = await supabase.table(table_name).insert(batch).execute()
            
            if result.error:
                logger.error(f"Error almacenando lote de fragmentos: {result.error}")
            else:
                stored_count += len(batch)
        
        # Calcular estadísticas
        processing_time = time.time() - start_time
        
        stats = {
            "chunks_processed": len(chunks),
            "chunks_stored": stored_count,
            "embedding_model": model or settings.default_embedding_model,
            "processing_time": processing_time,
            "average_chunk_length": sum(len(c["text"]) for c in chunks) / len(chunks)
        }
        
        # Invalidar caché de vector store para esta colección
        # para que las consultas puedan acceder a los nuevos datos
        from services.vector_store import invalidate_vector_store_cache
        await invalidate_vector_store_cache(tenant_id, collection_id)
        
        logger.info(f"Procesados {stored_count} fragmentos en {processing_time:.2f}s")
        return stats
        
    except Exception as e:
        logger.error(f"Error procesando y almacenando fragmentos: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(
            message=f"Error procesando y almacenando fragmentos: {str(e)}",
            error_code="EMBEDDING_STORAGE_ERROR",
            details={
                "document_id": document_id,
                "collection_id": collection_id,
                "chunks_count": len(chunks) if chunks else 0
            }
        )