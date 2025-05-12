"""
Endpoints para generación de embeddings vectoriales.
"""

import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends, Body, HTTPException

from common.models import (
    TenantInfo, EmbeddingRequest, EmbeddingResponse, 
    BatchEmbeddingRequest, BatchEmbeddingResponse, TextItem,
    FailedEmbeddingItem, InternalEmbeddingResponse
)
from common.auth import verify_tenant, validate_model_access
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

async def _validate_and_get_model(tenant_info: TenantInfo, requested_model: str) -> Tuple[str, Dict]:
    """
    Valida y obtiene el modelo de embedding apropiado, estandarizando el manejo de modelos no permitidos.
    
    Args:
        tenant_info: Información del tenant
        requested_model: Modelo solicitado por el usuario
        
    Returns:
        Tuple[str, Dict]: Modelo validado y metadatos
    """
    model_type = "embedding"  # El servicio de embeddings solo maneja modelos de embedding
    
    try:
        validated_model = await validate_model_access(tenant_info, requested_model, model_type, tenant_id=tenant_info.tenant_id)
        return validated_model, {}  # Modelo validado sin downgrade
    except ServiceError as e:
        # Comportamiento estándar: downgrade al modelo permitido
        error_context = {
            "tenant_id": tenant_info.tenant_id,
            "requested_model": requested_model,
            "model_type": model_type,
            "tier": tenant_info.subscription_tier
        }
        logger.info(f"Cambiando al modelo predeterminado: {e.message}", extra=error_context)
        
        # Obtener modelos de embedding disponibles
        allowed_models = get_available_embedding_models(tenant_info.subscription_tier, tenant_id=tenant_info.tenant_id)
        default_model = settings.default_embedding_model
            
        # Usar el primer modelo disponible o el predeterminado
        validated_model = allowed_models[0] if allowed_models else default_model
        
        # Información sobre el downgrade para la respuesta
        return validated_model, {"model_downgraded": True, "requested_model": requested_model}

@router.post("/embeddings", response_model=None, response_model_exclude_none=True)
@with_context(tenant=True, collection=True)  # Simplificado a los contextos realmente necesarios
@handle_errors(error_type="simple", log_traceback=False)
async def generate_embeddings(
    request: EmbeddingRequest,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
) -> EmbeddingResponse:
    """
    Genera embeddings vectoriales para una lista de textos.
    
    Este endpoint transforma texto en vectores densos que capturan el significado semántico,
    utilizando modelos de embeddings como OpenAI o alternativas locales como Ollama.
    """
    start_time = time.time()
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    # await check_tenant_quotas(tenant_info)
    
    # Obtener textos a procesar
    texts = request.texts
    if not texts:
        raise ValidationError(
            message="No se proporcionaron textos para generar embeddings",
            details={"tenant_id": tenant_id}
        )
    
    # Obtener parámetros de la solicitud
    model_name = request.model or settings.default_embedding_model
    
    # Obtener IDs de contexto directamente del objeto Context
    agent_id = ctx.get_agent_id()  # Puede ser None si no hay contexto de agente
    conversation_id = ctx.get_conversation_id()  # Puede ser None si no hay contexto de conversación
    collection_id = ctx.get_collection_id() or request.collection_id  # Priorizar contexto, pero permitir override
    
    # Validar modelo usando la función estandarizada
    model_name, metadata = await _validate_and_get_model(tenant_info, model_name)
    
    # Crear proveedor de embeddings con caché
    embedding_provider = CachedEmbeddingProvider(model_name=model_name, tenant_id=tenant_id)
    
    try:
        # Generar embeddings con soporte de caché
        embeddings = await embedding_provider.get_batch_embeddings(texts)
        
        # Calcular total de tokens usando la función centralizada
        total_tokens = 0
        for text in texts:
            total_tokens += await estimate_prompt_tokens(text)
        
        # Determinar si es OpenAI o Ollama para metadatos enriquecidos
        provider = "openai" if "openai" in model_name.lower() else "ollama" if "ollama" in model_name.lower() else "other"
        
        # Generar clave de idempotencia específica para embeddings
        # Crear hash único basado en el contenido, evitando textos muy grandes
        content_hash = hashlib.md5("".join([text[:50] for text in texts]).encode()).hexdigest()[:10]
        operation_id = f"embed:{len(texts)}:{content_hash}"
        idempotency_key = f"embed:{tenant_id}:{operation_id}:{int(time.time())}"
        
        # Registrar uso de tokens con el sistema centralizado usando constantes estandarizadas
        try:
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=total_tokens,
                model=model_name,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                token_type=TOKEN_TYPE_EMBEDDING,  # Usar constante estandarizada
                operation=OPERATION_QUERY,        # Usar constante estandarizada
                idempotency_key=idempotency_key,  # Prevenir doble conteo
                metadata={
                    "provider": provider,
                    "operation_id": operation_id,
                    "num_texts": len(texts),
                    "total_chars": sum(len(text) for text in texts),
                    "average_length": sum(len(text) for text in texts) / len(texts) if texts else 0
                }
            )
        except Exception as track_err:
            logger.warning(f"Error al registrar uso de tokens: {str(track_err)}", 
                         extra={"tenant_id": tenant_id, "error": str(track_err)})
        
        processing_time = time.time() - start_time
        logger.info(f"Generados {len(embeddings)} embeddings en {processing_time:.2f}s con modelo {model_name}")
        
        return EmbeddingResponse(
            embeddings=embeddings,
            model=model_name,
            dimensions=len(embeddings[0]) if embeddings else 0,
            collection_id=collection_id,
            processing_time=processing_time,
            cached_count=embedding_provider.cached_count,
            total_tokens=total_tokens
        )
        
    except Exception as e:
        error_details = {
            "model": model_name,
            "tenant_id": tenant_id,
            "texts_count": len(texts),
            "operation": "generate_embeddings",
            "error_type": type(e).__name__
        }
        logger.error(f"Error generando embeddings: {str(e)}", extra=error_details, exc_info=True)
        raise EmbeddingGenerationError(
            message=f"Error generando embeddings: {str(e)}",
            details=error_details
        )

@router.post("/embeddings/batch", response_model=None, response_model_exclude_none=True)
@with_context(tenant=True, collection=True)  # Simplificado a los contextos realmente necesarios
@handle_errors(error_type="simple", log_traceback=False)
async def batch_generate_embeddings(
    request: BatchEmbeddingRequest,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
) -> BatchEmbeddingResponse:
    """
    Procesa embeddings para lotes de elementos con texto y metadatos asociados.
    
    Este endpoint está optimizado para procesar múltiples textos junto con sus metadatos,
    permitiendo un procesamiento más eficiente y manteniendo la relación entre 
    los textos y sus datos asociados.
    """
    start_time = time.time()
    
    # Obtener tenant_id directamente de tenant_info (validado por verify_tenant)
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    # await check_tenant_quotas(tenant_info)
    
    # Verificar que hay items para procesar
    if not request.items:
        raise ValidationError(
            message="No se proporcionaron items para generar embeddings",
            details={"tenant_id": tenant_id}
        )
    
    # Obtener parámetros de la solicitud
    model_name = request.model or settings.default_embedding_model
    collection_id = request.collection_id
    
    # ID de agente y conversación (opcionales, solo para tracking)
    agent_id = getattr(request, 'agent_id', None)
    conversation_id = getattr(request, 'conversation_id', None)
    
    # Validar modelo usando la función estandarizada
    model_name, metadata = await _validate_and_get_model(tenant_info, model_name)
    
    # Separar textos y metadatos, mantener índices originales
    original_indices = []
    texts = []
    failed_items = []
    
    for i, item in enumerate(request.items):
        if not item.text or not item.text.strip():
            # Registrar item fallido debido a texto vacío
            failed_items.append(FailedEmbeddingItem(
                index=i,
                text=item.text,
                metadata=item.metadata or {},
                error="Texto vacío o solo espacios"
            ))
            continue
        
        # Añadir información de tenant y colección a la metadata
        if not item.metadata:
            item.metadata = {}
            
        # Asegurarse que la metadata tenga campos requeridos
        item.metadata["tenant_id"] = tenant_id
        
        # Agregar collection_id a metadata si está disponible
        if collection_id:
            item.metadata["collection_id"] = collection_id
            
        original_indices.append(i)
        texts.append(item.text)
    
    # Crear proveedor de embeddings con caché
    embedding_provider = CachedEmbeddingProvider(model_name=model_name, tenant_id=tenant_id)
    
    try:
        # Generar embeddings con soporte de caché
        embeddings = await embedding_provider.get_batch_embeddings(texts)
        
        # Calcular total de tokens usando la función centralizada
        total_tokens = 0
        for text in texts:
            total_tokens += await estimate_prompt_tokens(text)
        
        # Determinar si es OpenAI o Ollama para metadatos enriquecidos
        provider = "openai" if "openai" in model_name.lower() else "ollama" if "ollama" in model_name.lower() else "other"
        
        # Generar clave de idempotencia específica para batch embeddings
        # Incluir hash de los primeros 50 caracteres de cada texto para evitar doble conteo
        content_hash = hashlib.md5("".join([text[:30] for text in texts[:10]]).encode()).hexdigest()[:10]
        operation_id = f"batch:{len(texts)}:{content_hash}"
        idempotency_key = f"embed:{tenant_id}:{operation_id}:{int(time.time())}"
        
        # Registrar uso de tokens con el sistema centralizado usando constantes estandarizadas
        try:
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=total_tokens,
                model=model_name,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                token_type=TOKEN_TYPE_EMBEDDING,  # Usar constante estandarizada
                operation=OPERATION_BATCH,  # Constante estandarizada para batch
                idempotency_key=idempotency_key,  # Prevenir doble conteo
                metadata={
                    "provider": provider,
                    "operation_id": operation_id,
                    "batch_size": len(texts),
                    "total_items": len(request.items),
                    "failed_items": len(failed_items),
                    "total_chars": sum(len(text) for text in texts)
                }
            )
        except Exception as track_err:
            logger.warning(f"Error al registrar uso de tokens de batch: {str(track_err)}", 
                         extra={"tenant_id": tenant_id, "error": str(track_err)})
        
        # Construir respuesta asociando embeddings con sus metadatos originales
        result_embeddings = []
        all_embeddings = []
        items_with_metadata = []
        
        for orig_idx, embedding in zip(original_indices, embeddings):
            item = request.items[orig_idx]
            # Añadir el embedding a la lista principal de embeddings
            all_embeddings.append(embedding)
            # Añadir el item con su metadata a la lista de items
            items_with_metadata.append(TextItem(
                text=item.text,
                metadata=item.metadata or {}
            ))
        
        processing_time = time.time() - start_time
        logger.info(f"Generados {len(embeddings)} embeddings en {processing_time:.2f}s con modelo {model_name}")
        
        return BatchEmbeddingResponse(
            embeddings=all_embeddings,
            items=items_with_metadata,
            model=model_name,
            dimensions=len(embeddings[0]) if embeddings else 0,
            processing_time=processing_time,
            cached_count=embedding_provider.cached_count,
            total_tokens=total_tokens,
            collection_id=collection_id
        )
        
    except Exception as e:
        error_details = {
            "model": model_name,
            "tenant_id": tenant_id,
            "texts_count": len(texts),
            "operation": "batch_generate_embeddings",
            "error_type": type(e).__name__
        }
        logger.error(f"Error generando embeddings batch: {str(e)}", extra=error_details, exc_info=True)
        raise EmbeddingGenerationError(
            message=f"Error generando embeddings batch: {str(e)}",
            details=error_details
        )

@router.post("/internal/embed", response_model=InternalEmbeddingResponse, response_model_exclude_none=True, response_model_exclude={"ctx"})
@with_context(tenant=True, validate_tenant=False)  # Endpoint interno que acepta tenant_id como parámetro
@handle_errors(error_type="service", log_traceback=True)
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
        tenant_info = TenantInfo(tenant_id=tenant_id, subscription_tier=subscription_tier)
        
        # Validar modelo usando la función estandarizada
        try:
            model_name, metadata = await _validate_and_get_model(tenant_info, model_name)
        except Exception as validation_err:
            # En caso de error usar modelo predeterminado
            model_name = settings.default_embedding_model
            metadata = {"model_downgraded": True, "validation_error": str(validation_err)}
    
    # Crear proveedor de embeddings
    embedding_provider = CachedEmbeddingProvider(
        model_name=model_name, 
        tenant_id=tenant_id,
        collection_id=collection_id  # Pasar collection_id para especificidad en caché
    )
    
    try:
        # Generar embeddings
        embeddings = await embedding_provider.get_batch_embeddings(
            texts, 
            collection_id=collection_id,
            chunk_id=chunk_id  # Pasar los IDs de chunks para mejor seguimiento y caché
        )
        
        # Calcular total de tokens usando la función centralizada
        total_tokens = 0
        for text in texts:
            total_tokens += await estimate_prompt_tokens(text)
        
        # Registrar uso de tokens con sistema unificado y soporte de idempotencia
        if total_tokens > 0 and hasattr(settings, 'tracking_enabled') and settings.tracking_enabled:
            # Determinar proveedor para metadatos enriquecidos
            provider = "openai" if model and "openai" in model.lower() else "ollama" if model and "ollama" in model.lower() else "other"
            
            # Generar clave de idempotencia específica para el endpoint interno
            # No usar textos completos para evitar claves muy largas
            content_hash = hashlib.md5("".join([text[:20] for text in texts[:5]]).encode()).hexdigest()[:10]
            operation_id = f"internal:{len(texts)}:{content_hash}"
            idempotency_key = f"embed:{tenant_id}:{operation_id}:{int(time.time())}"
            
            try:
                await track_token_usage(
                    tenant_id=tenant_id,
                    tokens=total_tokens,
                    model=model,
                    agent_id=None,  # No hay contexto de agente en endpoint interno
                    conversation_id=None,  # No hay contexto de conversación
                    collection_id=collection_id,
                    token_type=TOKEN_TYPE_EMBEDDING,  # Constante estandarizada
                    operation=OPERATION_INTERNAL,  # Constante estandarizada para uso interno
                    idempotency_key=idempotency_key,  # Prevenir doble conteo
                    metadata={
                        "provider": provider,
                        "operation_id": operation_id,
                        "num_texts": len(texts),
                        "service": "internal",
                        "chunk_ids": True if chunk_id else False,
                        "total_chars": sum(len(text) for text in texts)
                    }
                )
            except Exception as track_err:
                # Solo log, no queremos fallar la operación principal por tracking
                logger.warning(f"Error registrando uso de tokens: {str(track_err)}", 
                             extra={"tenant_id": tenant_id, "error": str(track_err)})
        
        return InternalEmbeddingResponse(
            success=True,
            message="Embeddings generados correctamente",
            data=embeddings,
            metadata={
                "count": len(texts),
                "model_used": model_name,
                "timestamp": time.time()
            }
        )
    except Exception as e:
        logger.exception(f"Error generando embeddings internos: {str(e)}")
        
        # Si es un error genérico, convertirlo a un tipo específico según su naturaleza
        if not isinstance(e, ServiceError):
            if "too large" in str(e).lower() or "demasiado grande" in str(e).lower():
                if len(texts) > 1:
                    specific_error = BatchTooLargeError(
                        message=f"Lote demasiado grande para procesar: {str(e)}",
                        details={"texts_count": len(texts), "tenant_id": tenant_id}
                    )
                else:
                    specific_error = TextTooLargeError(
                        message=f"Texto demasiado grande para generar embedding: {str(e)}",
                        details={"text_length": len(texts[0]) if texts else 0, "tenant_id": tenant_id}
                    )
            elif "embedding" in str(e).lower() or "model" in str(e).lower():
                specific_error = EmbeddingModelError(
                    message=f"Error con el modelo de embedding: {str(e)}",
                    details={"model": model_name, "tenant_id": tenant_id}
                )
            else:
                specific_error = EmbeddingGenerationError(
                    message=f"Error generando embeddings: {str(e)}",
                    details={"model": model_name, "texts_count": len(texts), "tenant_id": tenant_id}
                )
        else:
            specific_error = e
        
        # Usar el modelo estandarizado para el error
        return InternalEmbeddingResponse(
            success=False,
            message=specific_error.message,
            error={
                "message": specific_error.message,
                "details": {
                    "error_type": specific_error.__class__.__name__,
                    "error_code": specific_error.error_code
                },
                "timestamp": time.time()
            },
            metadata={
                "texts_count": len(texts) if texts else 0,
                "model_requested": model,
                "timestamp": time.time()
            }
        )


@router.post("/internal/invalidate", response_model=Dict[str, Any],
            summary="Invalidar caché de documento",
            description="Invalida la caché de un documento actualizado de forma coordinada")
@with_context(tenant=True, validate_tenant=True)
@handle_errors(error_type="service", log_traceback=True)
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
    # Usar el tenant_id del contexto si está disponible
    if ctx and ctx.has_tenant_id():
        tenant_id = ctx.get_tenant_id()
    
    # Registrar la operación
    global _invalidation_count
    _invalidation_count += 1
    
    logger.info(
        f"Invalidando cachés para documento {document_id} del tenant {tenant_id} "
        f"colección {collection_id or 'N/A'}"
    )
    
    # Utilizar la función centralizada para invalidación coordinada
    invalidation_results = await invalidate_document_update(
        tenant_id=tenant_id,
        document_id=document_id,
        collection_id=collection_id
    )
    
    # Registrar información detallada en nivel debug
    logger.debug(f"Resultado de invalidación: {invalidation_results}")
    
    # Devolver resultado estandarizado
    return {
        "success": True,
        "message": f"Caché invalidada para documento {document_id}",
        "data": invalidation_results,
        "metadata": {
            "total_items": sum(invalidation_results.values()) if invalidation_results else 0,
            "timestamp": time.time(),
            "service": "embedding-service"
        }
    }