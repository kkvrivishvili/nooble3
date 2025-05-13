"""
Endpoints para generación de embeddings vectoriales.

NOTA IMPORTANTE: Este servicio solo expone endpoints internos para uso por
otros servicios del sistema (Agent Service, Ingestion Service) y no debe
tener endpoints públicos directos.
"""

import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends, Body, HTTPException

from common.models import (
    TenantInfo, InternalEmbeddingResponse
)
from common.auth import validate_model_access
from common.context import with_context, Context
from common.errors import (
    handle_errors, ValidationError, EmbeddingGenerationError, RateLimitExceeded,
    ServiceError, BatchTooLargeError, TextTooLargeError, EmbeddingModelError
)
from common.config.tiers import get_available_embedding_models
from common.tracking import track_token_usage, estimate_prompt_tokens, TOKEN_TYPE_EMBEDDING, OPERATION_QUERY, OPERATION_BATCH, OPERATION_INTERNAL
from common.cache import generate_resource_id_hash, invalidate_document_update

# Importar configuración centralizada
from config.constants import (
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    TIMEOUTS
)
from config.settings import get_settings

# Servicios locales
from services.embedding_provider import CachedEmbeddingProvider

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

_invalidation_count = 0

async def _validate_and_get_model(tenant_id: str, requested_model: str, subscription_tier: Optional[str] = None) -> Tuple[str, Dict]:
    """
    Valida y obtiene el modelo de embedding apropiado, estandarizando el manejo de modelos no permitidos.
    
    Args:
        tenant_id: ID del tenant
        requested_model: Modelo solicitado
        subscription_tier: Nivel de suscripción (opcional)
        
    Returns:
        Tuple[str, Dict]: Modelo validado y metadatos
    """
    # Obtener modelos disponibles según tier
    tier = subscription_tier or "free"
    available_models = get_available_embedding_models(tier)
    
    # Usar el modelo solicitado si está disponible para el tier del tenant
    if requested_model and requested_model in available_models:
        return requested_model, {}
    
    # Si no está disponible, utilizar el mejor modelo según el tier
    validated_model = available_models[0] if available_models else "text-embedding-3-small"
    
    # Si el modelo solicitado no está disponible para este tier, registrarlo para métricas
    if requested_model and requested_model != validated_model:
        logger.info(f"Downgrading model request: {requested_model} -> {validated_model} (tenant_tier: {tier})")
        # Información sobre el downgrade para la respuesta
        return validated_model, {"model_downgraded": True, "requested_model": requested_model}
    
    return validated_model, {}


@router.post("/internal/embed", response_model=InternalEmbeddingResponse)
@handle_errors(error_type="json", log_traceback=True)
async def internal_embed(
    texts: List[str] = Body(..., description="Textos para generar embeddings"),
    model: Optional[str] = Body(None, description="Modelo de embedding"),
    tenant_id: str = Body(..., description="ID del tenant"),
    collection_id: Optional[str] = Body(None, description="ID de la colección para especificidad en caché"),
    chunk_id: Optional[List[str]] = Body(None, description="Lista de IDs de chunks correspondientes a cada texto"),
    subscription_tier: Optional[str] = Body(None, description="Nivel de suscripción del tenant")
) -> InternalEmbeddingResponse:
    """
    Endpoint interno para uso exclusivo de los servicios de query y agent.
    
    Este endpoint está optimizado para alta eficiencia y bajo overhead, generando
    embeddings para textos sin validaciones complejas de permisos de usuario.
    
    Args:
        texts: Lista de textos para generar embeddings
        model: Modelo de embedding a utilizar (opcional)
        tenant_id: ID del tenant
        collection_id: ID de la colección (opcional, para caché)
        chunk_id: Lista de IDs de chunks correspondientes a cada texto (opcional, para caché)
        subscription_tier: Nivel de suscripción del tenant (opcional)
        
    Returns:
        InternalEmbeddingResponse: Respuesta estandarizada con embeddings generados
    """
    start_time = time.time()
    
    # Verificar entrada
    if not texts:
        return InternalEmbeddingResponse(
            success=False,
            message="No se proporcionaron textos para generar embeddings",
            error={
                "message": "No se proporcionaron textos para generar embeddings",
                "code": "VALIDATION_ERROR"
            }
        )
    
    # Asignar modelo predeterminado si no se proporciona
    model_name = model or settings.default_embedding_model
    metadata = {}
    
    # Crear tenant_info mínimo para validación si se proporciona tier
    if subscription_tier:
        model_name, model_metadata = await _validate_and_get_model(tenant_id, model_name, subscription_tier)
        metadata.update(model_metadata)
    
    try:
        # Crear proveedor de embeddings
        provider = CachedEmbeddingProvider(
            model_name=model_name,
            tenant_id=tenant_id,
            collection_id=collection_id,
            tier=subscription_tier
        )
        
        # Generar embeddings
        embeddings, batch_metadata = await provider.batch_embeddings(
            texts=texts,
            tenant_id=tenant_id,
            collection_id=collection_id,
            chunk_ids=chunk_id
        )
        
        # Registrar uso de tokens para operación interna
        total_tokens = batch_metadata.get("total_tokens", 0)
        if total_tokens > 0:
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=total_tokens,
                model=model_name,
                token_type=TOKEN_TYPE_EMBEDDING,
                operation=OPERATION_INTERNAL,
                metadata={
                    "service": "embedding-service",
                    "endpoint": "internal/embed",
                    "collection_id": collection_id
                }
            )
        
        # Preparar respuesta
        response = InternalEmbeddingResponse(
            success=True,
            data=embeddings,
            message="Embeddings generados correctamente",
            metadata={
                "model_used": model_name,
                "time_ms": int((time.time() - start_time) * 1000),
                "count": len(embeddings),
                **metadata,
                **batch_metadata
            },
            usage=batch_metadata.get("usage", {})
        )
        
        return response
    
    except Exception as e:
        error_msg = f"Error interno generando embeddings: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return InternalEmbeddingResponse(
            success=False,
            message=error_msg,
            error={
                "message": error_msg,
                "code": "EMBEDDING_ERROR",
                "details": {"error_type": e.__class__.__name__}
            }
        )


@router.post("/internal/invalidate", response_model=Dict[str, Any])
@with_context(tenant=True)
@handle_errors(error_type="json", log_traceback=True)
async def internal_invalidate_document(
    document_id: str = Body(..., description="ID del documento a invalidar"),
    tenant_id: str = Body(..., description="ID del tenant"),
    collection_id: Optional[str] = Body(None, description="ID de la colección (opcional)"),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Endpoint interno para invalidar la caché de forma coordinada cuando un documento es actualizado.
    
    Este endpoint utiliza el patrón centralizado de invalidate_document_update para garantizar
    que todas las cachés relacionadas (embeddings, vector store, consultas) se invaliden
    correctamente cuando un documento es actualizado.
    
    Args:
        document_id: ID del documento actualizado
        tenant_id: ID del tenant propietario del documento
        collection_id: ID de la colección a la que pertenece el documento (opcional)
        
    Returns:
        Dict[str, Any]: Resumen de la invalidación con conteo por tipo
    """
    global _invalidation_count
    start_time = time.time()
    
    # Validación mínima de entrada
    if not document_id or not tenant_id:
        raise ValidationError(
            message="Se requiere document_id y tenant_id para invalidar caché",
            details={"document_id": document_id, "tenant_id": tenant_id}
        )
    
    try:
        # Usar la función centralizada para invalidar caché del documento
        keys_invalidated = await invalidate_document_update(
            document_id=document_id,
            tenant_id=tenant_id,
            collection_id=collection_id
        )
        
        # Actualizar contador global para métricas
        _invalidation_count += 1
        
        # Preparar respuesta detallada
        response = {
            "success": True,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "keys_invalidated": keys_invalidated,
            "total_invalidated": sum(keys_invalidated.values()),
            "timestamp": int(time.time()),
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "invalidation_count": _invalidation_count
        }
        
        # Registrar operación
        logger.info(f"Caché invalidada para documento {document_id}: {response['total_invalidated']} claves")
        
        return response
    
    except Exception as e:
        error_msg = f"Error invalidando caché para documento {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ServiceError(
            message=error_msg,
            details={
                "document_id": document_id,
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "error_type": e.__class__.__name__
            }
        )
