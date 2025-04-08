"""
Endpoints para generación de embeddings.
"""

import time
import logging
from typing import List, Dict, Any, Optional, Union

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel

from common.models import (
    TenantInfo, EmbeddingRequest, EmbeddingResponse, 
    BatchEmbeddingRequest, BatchEmbeddingResponse, BatchEmbeddingData, BatchEmbeddingError
)
from common.errors import ServiceError, handle_service_error_simple
from common.context import with_context
from common.auth import verify_tenant, check_tenant_quotas, validate_model_access
from common.tracking import track_embedding_usage
from common.config import get_settings

from services.embedding_provider import CachedEmbeddingProvider

router = APIRouter()
logger = logging.getLogger(__name__)
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
        raise ServiceError(
            message="No se proporcionaron textos para generar embeddings",
            status_code=400,
            error_code="missing_texts"
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
            success=True,
            message="Embeddings generados exitosamente",
            embeddings=embeddings,
            model=model_name,
            collection_id=collection_id,
            processing_time=processing_time,
            total_tokens=int(tokens_estimate)
        )
        
    except Exception as e:
        logger.error(f"Error generando embeddings: {str(e)}", exc_info=True)
        raise ServiceError(
            message=f"Error generando embeddings: {str(e)}",
            status_code=500,
            error_code="embedding_generation_error"
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
        raise ServiceError(
            message="No se proporcionaron items para generar embeddings",
            status_code=400,
            error_code="missing_items"
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
            failed_items.append(BatchEmbeddingError(
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
            result_embeddings.append(BatchEmbeddingData(
                embedding=embedding,
                text=item.text,
                metadata=item.metadata or {}
            ))
        
        processing_time = time.time() - start_time
        logger.info(f"Generados {len(embeddings)} embeddings en {processing_time:.2f}s con modelo {model_name}")
        
        return BatchEmbeddingResponse(
            success=True,
            message="Embeddings batch generados exitosamente",
            embeddings=result_embeddings,
            failed_items=failed_items,
            model=model_name,
            collection_id=collection_id,
            processing_time=processing_time,
            total_tokens=int(tokens_estimate)
        )
        
    except Exception as e:
        logger.error(f"Error generando embeddings batch: {str(e)}", exc_info=True)
        raise ServiceError(
            message=f"Error generando embeddings batch: {str(e)}",
            status_code=500,
            error_code="embedding_batch_generation_error"
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
    """
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
        "embeddings": embeddings,
        "model": model_name
    }