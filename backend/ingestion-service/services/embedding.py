"""
Funciones para generar embeddings para fragmentos de documentos.
"""

import logging
from typing import List, Dict, Any, Optional

from common.errors import (
    ServiceError, EmbeddingGenerationError,
    handle_errors
)
from common.context import with_context, Context

# Importar el módulo central de LlamaIndex
from services.llama_core import (
    generate_embeddings_with_llama_index,
    store_chunks_in_vector_store
)

logger = logging.getLogger(__name__)

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def generate_embeddings_for_chunks(
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    model: Optional[str] = None,
    collection_id: Optional[str] = None,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Genera embeddings para una lista de fragmentos.
    
    Args:
        chunks: Lista de fragmentos con texto y metadatos
        tenant_id: ID del tenant
        model: Modelo de embedding a utilizar
        collection_id: ID de la colección para caché
        ctx: Contexto de la operación
        
    Returns:
        List[Dict[str, Any]]: Lista de fragmentos con embeddings
        
    Raises:
        EmbeddingModelError: Si el modelo no está disponible para el tier del tenant
        EmbeddingGenerationError: Si hay un error generando los embeddings
    """
    if not chunks:
        return []
    
    try:
        # Preparar textos para el batch
        texts = [chunk["text"] for chunk in chunks]
        
        # Usar el módulo central de LlamaIndex para generar embeddings
        embeddings, metadata = await generate_embeddings_with_llama_index(
            texts=texts,
            tenant_id=tenant_id,
            model_name=model,
            ctx=ctx
        )
        
        # Verificar resultados
        if len(embeddings) != len(chunks):
            raise EmbeddingGenerationError(
                message=f"Discrepancia en el número de embeddings: {len(embeddings)} vs {len(chunks)} fragmentos",
                details={"chunks_count": len(chunks), "embeddings_count": len(embeddings)}
            )
        
        # Añadir embeddings a los fragmentos
        result = []
        for i, chunk in enumerate(chunks):
            chunk_with_embedding = chunk.copy()
            chunk_with_embedding["embedding"] = embeddings[i]
            result.append(chunk_with_embedding)
        
        logger.info(f"Embeddings generados para {len(result)} fragmentos usando LlamaIndex")
        return result
        
    except Exception as e:
        logger.error(f"Error generando embeddings: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        
        raise EmbeddingGenerationError(
            message=f"Error generando embeddings: {str(e)}",
            details={
                "model": model,
                "chunks_count": len(chunks) if chunks else 0
            }
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def process_and_store_chunks(
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    collection_id: str,
    document_id: str,
    model: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Procesa fragmentos, genera embeddings y almacena en Supabase.
    
    Args:
        chunks: Lista de fragmentos con texto y metadatos
        tenant_id: ID del tenant
        collection_id: ID de la colección
        document_id: ID del documento
        model: Modelo de embeddings a utilizar
        ctx: Contexto de la operación
        
    Returns:
        Dict[str, Any]: Estadísticas del procesamiento
    """
    # Usar directamente el módulo central de LlamaIndex para todo el proceso
    return await store_chunks_in_vector_store(
        chunks=chunks,
        tenant_id=tenant_id,
        collection_id=collection_id,
        document_id=document_id,
        embedding_model=model,
        ctx=ctx
    )