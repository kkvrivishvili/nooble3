"""
Endpoint único para generación de embeddings.
"""

import logging
import time
from fastapi import APIRouter, Body

from models.embeddings import EnhancedEmbeddingRequest, EnhancedEmbeddingResponse
from provider.openai import OpenAIEmbeddingProvider
from common.errors import handle_errors, ServiceError
from common.context import with_context, Context
from config.settings import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

@router.post("/internal/enhanced_embed", response_model=EnhancedEmbeddingResponse)
@handle_errors(error_type="json", log_traceback=True)
@with_context
async def generate_embeddings(
    request: EnhancedEmbeddingRequest = Body(...),
    ctx: Context = None
) -> EnhancedEmbeddingResponse:
    """
    Genera embeddings para los textos proporcionados.
    
    Este endpoint es usado exclusivamente por el servicio de agentes
    para generar embeddings que luego se pasan al servicio de query.
    """
    start_time = time.time()
    
    # Validar request
    if not request.texts:
        raise ServiceError("No se proporcionaron textos")
    
    # Validar longitud de textos
    for i, text in enumerate(request.texts):
        if len(text) > settings.max_text_length:
            raise ServiceError(
                f"Texto {i} excede el límite de {settings.max_text_length} caracteres"
            )
    
    # Validar tamaño de batch
    if len(request.texts) > settings.max_batch_size:
        raise ServiceError(
            f"Batch excede el límite de {settings.max_batch_size} textos"
        )
    
    try:
        # Crear proveedor
        provider = OpenAIEmbeddingProvider(model=request.model)
        
        # Generar embeddings
        result = await provider.generate_embeddings(
            texts=request.texts,
            tenant_id=request.tenant_id,
            collection_id=str(request.collection_id) if request.collection_id else None,
            chunk_ids=request.chunk_ids,
            metadata=request.metadata
        )
        
        # Preparar respuesta
        processing_time = time.time() - start_time
        
        return EnhancedEmbeddingResponse(
            success=True,
            message="Embeddings generados correctamente",
            embeddings=result["embeddings"],
            model=provider.model,
            dimensions=provider._get_dimensions(),
            processing_time=processing_time,
            total_tokens=result["usage"].get("total_tokens", 0)
        )
        
    except Exception as e:
        logger.error(f"Error generando embeddings: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(f"Error interno: {str(e)}")
