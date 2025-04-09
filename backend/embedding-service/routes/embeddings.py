"""
Endpoints para generación de embeddings vectoriales.
"""

import logging
import time
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends

from common.models import TenantInfo
from common.errors import handle_service_error, handle_service_error_simple
from common.auth import verify_tenant
from common.auth.quotas import check_tenant_quotas
from common.context.decorator import with_context
from common.config import get_settings

from services.embedding_provider import CachedEmbeddingProvider
from services.tracking import track_embedding_usage
from models.api import (
    EmbeddingRequest, EmbeddingResponse, 
    BatchEmbeddingRequest, BatchEmbeddingResponse,
    BatchEmbeddingItem, BatchEmbeddingResult
)
from utils.validators import validate_model_access
from errors import EmbeddingGenerationError, InvalidEmbeddingParamsError

router = APIRouter()
logger = logging.getLogger("embedding-service")
settings = get_settings()

@router.post("/embeddings", response_model=EmbeddingResponse)
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True, collection=True)
async def generate_embeddings(
    request: EmbeddingRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> EmbeddingResponse:
    """
    Genera embeddings vectoriales para una lista de textos.
    
    Este endpoint transforma texto en vectores densos que capturan el significado semántico,
    utilizando modelos de embeddings como OpenAI o alternativas locales como Ollama.
    """
    start_time = time.time()
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    await check_tenant_quotas(tenant_info)
    
    # Obtener textos a procesar
    texts = request.texts
    if not texts:
        raise InvalidEmbeddingParamsError(
            message="No se proporcionaron textos para generar embeddings",
            details={"tenant_id": tenant_id}
        )
    
    # Obtener parámetros de la solicitud
    model_name = request.model or settings.default_embedding_model
    collection_id = request.collection_id
    
    # ID de agente y conversación (opcionales, solo para tracking)
    agent_id = request.agent_id if hasattr(request, 'agent_id') else None
    conversation_id = request.conversation_id if hasattr(request, 'conversation_id') else None
    
    # Validar acceso al modelo solicitado - CORREGIDO: Usar el modelo validado
    validated_model = await validate_model_access(tenant_info, model_name, "embedding")
    model_name = validated_model  # Asignar el modelo validado
    
    # Crear proveedor de embeddings con caché
    embedding_provider = CachedEmbeddingProvider(model_name=model_name, tenant_id=tenant_id)
    
    try:
        # Generar embeddings con soporte de caché
        embeddings = await embedding_provider.get_batch_embeddings(texts)
        
        # Registrar uso
        tokens_estimate = sum(len(text.split()) * 1.3 for text in texts)  # Estimación de tokens
        await track_embedding_usage(
            tenant_id=tenant_id,
            texts=texts,
            model=model_name,
            cached_count=0,  # Se podría mejorar para detectar cantidad de caché hits
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        
        processing_time = time.time() - start_time
        logger.info(f"Generados {len(embeddings)} embeddings en {processing_time:.2f}s con modelo {model_name}")
        
        return EmbeddingResponse(
            data=embeddings,
            model=model_name,
            collection_id=collection_id
        )
        
    except Exception as e:
        logger.error(f"Error generando embeddings: {str(e)}", exc_info=True)
        raise EmbeddingGenerationError(
            message=f"Error generando embeddings: {str(e)}",
            details={
                "model": model_name,
                "tenant_id": tenant_id,
                "texts_count": len(texts)
            }
        )

@router.post("/embeddings/batch", response_model=BatchEmbeddingResponse)
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True, collection=True)
async def batch_generate_embeddings(
    request: BatchEmbeddingRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
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
    await check_tenant_quotas(tenant_info)
    
    # Verificar que hay items para procesar
    if not request.items:
        raise InvalidEmbeddingParamsError(
            message="No se proporcionaron items para generar embeddings",
            details={"tenant_id": tenant_id}
        )
    
    # Obtener parámetros de la solicitud
    model_name = request.model or settings.default_embedding_model
    collection_id = request.collection_id
    
    # ID de agente y conversación (opcionales, solo para tracking)
    agent_id = request.agent_id if hasattr(request, 'agent_id') else None
    conversation_id = request.conversation_id if hasattr(request, 'conversation_id') else None
    
    # Validar acceso al modelo solicitado - CORREGIDO: Usar el modelo validado
    validated_model = await validate_model_access(tenant_info, model_name, "embedding")
    model_name = validated_model  # Asignar el modelo validado
    
    # Separar textos y metadatos, mantener índices originales
    original_indices = []
    texts = []
    failed_items = []
    
    for i, item in enumerate(request.items):
        if not item.text or not item.text.strip():
            # Registrar item fallido debido a texto vacío
            failed_items.append(BatchEmbeddingResult(
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
        
        # Registrar uso
        tokens_estimate = sum(len(text.split()) * 1.3 for text in texts)  # Estimación de tokens
        await track_embedding_usage(
            tenant_id=tenant_id,
            texts=texts,
            model=model_name,
            cached_count=0,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        
        # Construir respuesta asociando embeddings con sus metadatos originales
        result_embeddings = []
        for orig_idx, embedding in zip(original_indices, embeddings):
            item = request.items[orig_idx]
            result_embeddings.append(BatchEmbeddingItem(
                embedding=embedding,
                text=item.text,
                metadata=item.metadata or {}
            ))
        
        processing_time = time.time() - start_time
        logger.info(f"Generados {len(embeddings)} embeddings en {processing_time:.2f}s con modelo {model_name}")
        
        return BatchEmbeddingResponse(
            data=result_embeddings,
            failed_items=failed_items,
            model=model_name,
            collection_id=collection_id
        )
        
    except Exception as e:
        logger.error(f"Error generando embeddings batch: {str(e)}", exc_info=True)
        raise EmbeddingGenerationError(
            message=f"Error generando embeddings batch: {str(e)}",
            details={
                "model": model_name,
                "tenant_id": tenant_id,
                "texts_count": len(texts)
            }
        )

# Endpoint simplificado para uso interno por los servicios de query y agent
@router.post("/internal/embed", tags=["Internal"])
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True, collection=True)
async def internal_embed(
    texts: List[str] = Body(..., description="Textos para generar embeddings"),
    model: Optional[str] = Body(None, description="Modelo de embedding"),
    tenant_id: str = Body(..., description="ID del tenant")
) -> Dict[str, Any]:
    """
    Endpoint interno para uso exclusivo de los servicios de query y agent.
    
    Este endpoint está optimizado para alta eficiencia y bajo overhead, generando
    embeddings para textos sin validaciones complejas de permisos de usuario.
    
    Returns:
        Dict con formato estandarizado:
        {
            "success": bool,           # Éxito/fallo de la operación
            "message": str,            # Mensaje descriptivo
            "data": Any,               # Datos principales (embeddings)
            "metadata": Dict[str, Any] # Metadatos adicionales
            "error": Dict[str, Any]    # Presente solo en caso de error
        }
    """
    try:
        # Crear tenant_info mínimo para validación interna
        tenant_info = TenantInfo(tenant_id=tenant_id, subscription_tier="business")
        
        # Validar el modelo solicitado - CORREGIDO: Usar el modelo validado
        model_name = model or settings.default_embedding_model
        validated_model = await validate_model_access(tenant_info, model_name, "embedding")
        model_name = validated_model  # Asignar el modelo validado
        
        # Crear proveedor de embeddings
        embedding_provider = CachedEmbeddingProvider(model_name=model_name, tenant_id=tenant_id)
        
        # Generar embeddings
        embeddings = await embedding_provider.get_batch_embeddings(texts)
        
        # No hacemos tracking en llamadas internas para evitar doble conteo
        # ya que el servicio que llama hará su propio tracking
        
        return {
            "success": True,
            "message": "Embeddings generados correctamente",
            "data": {
                "embeddings": embeddings,
                "model": model_name
            },
            "metadata": {
                "count": len(texts),
                "model_used": model_name,
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.exception(f"Error generando embeddings internos: {str(e)}")
        
        # Si es un error genérico, convertirlo a un tipo específico según su naturaleza
        if not isinstance(e, ServiceError):
            if "too large" in str(e).lower() or "demasiado grande" in str(e).lower():
                if len(texts) > 1:
                    specific_error = BatchTooLargeError(
                        message=f"Lote de textos demasiado grande para procesar: {len(texts)} elementos",
                        details={"texts_count": len(texts)}
                    )
                else:
                    specific_error = TextTooLargeError(
                        message=f"Texto demasiado grande para procesar",
                        details={"text_length": len(texts[0]) if texts and len(texts) > 0 else 0}
                    )
            elif "model" in str(e).lower() or "modelo" in str(e).lower():
                specific_error = EmbeddingModelError(
                    message=f"Error con el modelo de embedding: {str(e)}",
                    details={"model_requested": model}
                )
            else:
                specific_error = EmbeddingGenerationError(
                    message=f"Error al generar embeddings: {str(e)}",
                    details={"texts_count": len(texts) if texts else 0}
                )
        else:
            specific_error = e
        
        # Construir respuesta de error estandarizada según el patrón de comunicación
        error_response = {
            "success": False,
            "message": specific_error.message,
            "data": None,
            "metadata": {
                "texts_count": len(texts) if texts else 0,
                "model_requested": model,
                "timestamp": time.time()
            },
            "error": {
                "message": specific_error.message,
                "details": {
                    "error_type": specific_error.__class__.__name__,
                    "error_code": specific_error.error_code
                },
                "timestamp": time.time()
            }
        }
        
        return error_response