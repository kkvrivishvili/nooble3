"""
Endpoints para generación de embeddings vectoriales.

NOTA IMPORTANTE: Este servicio solo expone endpoints internos para uso por
otros servicios del sistema (Agent Service, Ingestion Service) y no debe
tener endpoints públicos directos.
"""

import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Union
from fastapi import APIRouter, Depends, Body, HTTPException

from models import (InternalEmbeddingResponse, EnhancedEmbeddingRequest,
    EnhancedEmbeddingResponse, EmbeddingTaskConfig, ConversationContext)
from common.auth import validate_model_access
from common.context import with_context, Context
from common.errors import handle_errors, ServiceError, ValidationError
from common.config.tiers import get_available_embedding_models
from common.tracking import track_token_usage, TOKEN_TYPE_EMBEDDING, OPERATION_INTERNAL, OPERATION_BATCH
from common.cache import generate_resource_id_hash, invalidate_document_update
from common.cache.manager import CacheManager

# Importar configuración centralizada
from config.constants import (
    DEFAULT_EMBEDDING_DIMENSION,
    EMBEDDING_TASK_TYPES
)
from config.settings import get_settings

# Servicios locales
from services.embedding_provider import CachedEmbeddingProvider

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

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


@router.post("/internal/enhanced_embed", response_model=EnhancedEmbeddingResponse)
@handle_errors(error_type="json", log_traceback=True)
@with_context
async def enhanced_embed(
    request: EnhancedEmbeddingRequest = Body(..., description="Solicitud mejorada para generar embeddings"),
    ctx: Optional[Context] = None
) -> EnhancedEmbeddingResponse:
    """
    Endpoint mejorado para generación de embeddings con configuración específica de tarea y contexto.
    
    Este endpoint permite una configuración más detallada del proceso de embedding,
    incluyendo parámetros específicos para diferentes tipos de tareas (consulta, documento, re-ranking),
    y enriquecimiento con contexto de conversación para mejorar la calidad de los embeddings.
    
    Características principales:
    - Configuración específica de tarea (tipo, umbral de similitud, normalización)
    - Contexto de conversación para enriquecer embeddings
    - Compatibilidad con LlamaIndex y LangChain
    - Optimización de caché con parámetros de contexto
    - Tracking detallado de tokens y metadatos
    
    Args:
        request: Solicitud completa con textos, configuración de tarea y contexto
        ctx: Contexto de la solicitud (opcional, proporcionado por el decorador @with_context)
        
    Returns:
        EnhancedEmbeddingResponse: Respuesta enriquecida con embeddings y metadatos
    """
    start_time = time.time()
    
    # Verificar entrada
    if not request.texts:
        raise ValidationError(
            message="No se proporcionaron textos para generar embeddings",
            details={"code": "VALIDATION_ERROR"}
        )
    
    # Extraer parámetros principales de la solicitud
    start_time = time.time()
    
    # 1. Aplicar valores predeterminados usando las constantes centralizadas
    model_name = request.model or settings.default_embedding_model
    task_type = None
    metadata = {}
    
    # 2. Aplicar configuración especial si se proporciona un tipo de tarea específico
    if request.task_config and request.task_config.task_type:
        task_type = request.task_config.task_type
        # Si existe un tipo de tarea en nuestras constantes, usar sus valores por defecto
        if task_type in EMBEDDING_TASK_TYPES:
            task_info = EMBEDDING_TASK_TYPES[task_type]
            # En tiers premium, usar el modelo preferido para la tarea
            if request.subscription_tier in ["business", "enterprise"] and not request.model:
                model_name = task_info["preferred_model"]
            
    # 3. Validar acceso al modelo según tier
    if request.subscription_tier:
        model_name, model_metadata = await _validate_and_get_model(
            request.tenant_id, 
            model_name, 
            request.subscription_tier
        )
        metadata.update(model_metadata)
    
    # 4. Complementar contexto desde el decorador @with_context si es necesario
    if ctx and request.conversation_context:
        if not request.conversation_context.agent_id and ctx.get_agent_id():
            request.conversation_context.agent_id = ctx.get_agent_id()
        if not request.conversation_context.conversation_id and ctx.get_conversation_id():
            request.conversation_context.conversation_id = ctx.get_conversation_id()
    
    # Crear proveedor de embeddings
    provider = CachedEmbeddingProvider(
        model_name=model_name,
        tenant_id=request.tenant_id,
        collection_id=str(request.collection_id) if request.collection_id else None,
        tier=request.subscription_tier
    )
    
    try:
        # Generar embeddings directamente con los parámetros de la solicitud
        # Nota: provider.batch_embeddings ya maneja la lógica de caché y tracking
        embeddings, batch_metadata = await provider.batch_embeddings(
            texts=request.texts,
            tenant_id=request.tenant_id,
            collection_id=str(request.collection_id) if request.collection_id else None,
            chunk_ids=request.chunk_ids,
            task_config=request.task_config,
            conversation_context=request.conversation_context,
            metadata=request.metadata,
            ctx=ctx
        )
        
        # Registrar uso de tokens utilizando el sistema centralizado de tracking
        total_tokens = batch_metadata.get("total_tokens", 0)
        if total_tokens > 0:
            # Extraer IDs de contexto
            agent_id = None
            conversation_id = None
            if request.conversation_context:
                agent_id = request.conversation_context.agent_id
                conversation_id = request.conversation_context.conversation_id
            
            # Preparar metadatos básicos (siguiendo estándares del proyecto)
            tracking_metadata = {
                "service": "embedding-service",
                "endpoint": "internal/enhanced_embed",
                "dimensions": batch_metadata.get("dimensions", DEFAULT_EMBEDDING_DIMENSION),
                "latency_ms": int((time.time() - start_time) * 1000)
            }
            
            # Añadir metadatos de tarea específicos para análisis
            if request.task_config:
                tracking_metadata["task_type"] = str(request.task_config.task_type)
                if task_type in EMBEDDING_TASK_TYPES:
                    tracking_metadata["task_description"] = EMBEDDING_TASK_TYPES[task_type]["description"]
            
            # Añadir metadatos de origen para trazabilidad
            if request.source_service:
                tracking_metadata["source_service"] = request.source_service
            if request.target_service:
                tracking_metadata["target_service"] = request.target_service
            
            # Usar la función centralizada track_token_usage para seguir el estándar del proyecto
            await track_token_usage(
                tenant_id=request.tenant_id,
                tokens=total_tokens,
                model=model_name,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=str(request.collection_id) if request.collection_id else None,
                token_type=TOKEN_TYPE_EMBEDDING,
                operation=OPERATION_BATCH,
                metadata=tracking_metadata
            )
        
        # Preparar metadatos para la respuesta que sea fácil de usar desde el servicio de agentes
        compatibility_metadata = {
            "dimensions": batch_metadata.get("dimensions", DEFAULT_EMBEDDING_DIMENSION),
            "model": model_name,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "token_count": total_tokens,
            "cached_percentage": batch_metadata.get("cached_count", 0) / len(request.texts) * 100 if request.texts else 0
        }
        
        # Añadir información de tarea que sea útil para el agente
        if request.task_config:
            task_info = {
                "task_type": str(request.task_config.task_type),
                "normalize": request.task_config.normalize
            }
            
            # Añadir threshold si existe
            if hasattr(request.task_config, 'similarity_threshold') and request.task_config.similarity_threshold is not None:
                task_info["similarity_threshold"] = request.task_config.similarity_threshold
                
            compatibility_metadata["task"] = task_info
        
        # Preparar respuesta con todos los datos relevantes
        return EnhancedEmbeddingResponse(
            success=True,
            message="Embeddings generados correctamente",
            embeddings=embeddings,
            model=model_name,
            dimensions=batch_metadata.get("dimensions", DEFAULT_EMBEDDING_DIMENSION),
            task_config=request.task_config,  # Usar directamente el objeto de configuración original
            processing_time=time.time() - start_time,
            cached_count=batch_metadata.get("cached_count", 0),
            total_tokens=total_tokens,
            collection_id=request.collection_id,
            conversation_context=request.conversation_context,  # Incluir el contexto de conversación en la respuesta
            compatibility_metadata=compatibility_metadata
        )
    
    except ValidationError as e:
        # Reenviar errores de validación explícitos
        raise e
    
    except Exception as e:
        # Capturar y estructurar otros errores
        error_msg = f"Error generando embeddings mejorados: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        raise ServiceError(
            message=error_msg,
            details={
                "code": "ENHANCED_EMBEDDING_ERROR",
                "error_type": e.__class__.__name__
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
        
        # Registrar métrica de invalidación usando el sistema centralizado
        await CacheManager.increment_counter(
            counter_type="cache_invalidation",
            amount=1,
            resource_id="document_update",
            tenant_id=tenant_id,
            metadata={
                "document_id": document_id,
                "collection_id": collection_id,
                "keys_count": sum(keys_invalidated.values())
            }
        )
        
        # Preparar respuesta detallada
        response = {
            "success": True,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "keys_invalidated": keys_invalidated,
            "total_invalidated": sum(keys_invalidated.values()),
            "timestamp": int(time.time()),
            "elapsed_ms": int((time.time() - start_time) * 1000)
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
