"""
Utilidades para integración con LlamaIndex.

Este módulo proporciona funciones auxiliares para trabajar con LlamaIndex,
asegurando compatibilidad con el servicio de ingestión y otros servicios.
"""

import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple

from common.config import get_settings
from common.errors import handle_errors, ServiceError, ErrorCode
from common.context import with_context, Context
from common.config.tiers import get_available_embedding_models
from common.auth.models import validate_model_access
from common.tracking import track_token_usage
from common.cache.manager import CacheManager

# Importaciones de LlamaIndex
from llama_index.embeddings.openai import OpenAIEmbedding

logger = logging.getLogger(__name__)
settings = get_settings()

def configure_llama_index():
    """
    Configura LlamaIndex con parámetros globales.
    
    Esta función garantiza que las configuraciones sean consistentes con
    las utilizadas en el servicio de ingestión.
    """
    from llama_index.core import Settings
    
    # Configurar parámetros globales para LlamaIndex
    Settings.llm = None  # No configuramos LLM por defecto en este servicio
    Settings.embed_model = None  # Configuraremos por llamada individual
    
    logger.info("LlamaIndex configurado globalmente")

# Inicialización
configure_llama_index()

@handle_errors(error_type="service", log_traceback=True)
@with_context(tenant=True, validate_tenant=True)
async def generate_embeddings_with_llama_index(
    texts: List[str],
    tenant_id: str,
    model_name: str = None,
    ctx: Context = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Genera embeddings para textos usando LlamaIndex.
    
    Implementación idéntica a la del servicio de ingestión para asegurar
    compatibilidad completa entre servicios.
    
    Args:
        texts: Lista de textos para generar embeddings
        tenant_id: ID del tenant
        model_name: Nombre del modelo de embedding
        ctx: Contexto de la operación
        
    Returns:
        Tuple[List[List[float]], Dict[str, Any]]: 
            - Lista de embeddings generados
            - Diccionario con metadatos del proceso
    """
    try:
        # Verificar tier para uso del modelo
        tier = "free"  # Valor por defecto
        if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
            tier = ctx.tenant_info.tier
        
        # Usar modelo solicitado o modelo por defecto
        model_name = model_name or settings.default_embedding_model
        
        # Validar acceso al modelo según el tier
        available_models = get_available_embedding_models(tier, tenant_id)
        
        # Validar acceso al modelo
        if not validate_model_access(model_name, available_models):
            allowed_models = ", ".join(available_models)
            raise ServiceError(
                message=f"El modelo '{model_name}' no está disponible para el tier {tier}.",
                error_code=ErrorCode.PERMISSION_DENIED,
                details={
                    "requested_model": model_name,
                    "available_models": available_models,
                    "tier": tier
                }
            )
        
        # Crear hashes para los textos - usando método consistente con embedding-service
        text_hashes = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
        
        # Generar claves de caché compatibles con embedding-service
        cache_keys = []
        embeddings_from_cache = {}
        
        # Verificar caché para cada texto individualmente
        for i, text in enumerate(texts):
            # Crear clave de caché usando el mismo formato que embedding-service
            resource_id = f"{model_name}:{text_hashes[i]}"
            
            cache_keys.append(resource_id)
            
            # Intentar obtener embedding de caché
            try:
                val = await CacheManager.get(
                    data_type="embedding",
                    resource_id=resource_id,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    search_hierarchy=True,
                    use_memory=True
                )
                if val:
                    embeddings_from_cache[i] = val
            except Exception as cache_err:
                # Solo log en debug para errores de caché
                logger.debug(f"Error al obtener embedding de caché: {str(cache_err)}")
                
        # Si todos los embeddings están en caché, devolverlos directamente
        if len(embeddings_from_cache) == len(texts):
            logger.info(f"Embeddings obtenidos de caché para {len(texts)} textos")
            embeddings = [embeddings_from_cache[i] for i in range(len(texts))]
            
            # Registrar uso desde caché (menor costo)
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=0,  # Sin costo adicional por usar caché
                model=model_name,
                token_type="embedding",
                operation="cache_hit",
                metadata={"texts_count": len(texts)}
            )
            
            return embeddings, {"model": model_name, "cached": True}
            
        # Identificar textos que necesitan procesamiento
        texts_to_process = []
        indices_to_process = []
        
        for i, text in enumerate(texts):
            if i not in embeddings_from_cache:
                texts_to_process.append(text)
                indices_to_process.append(i)
        
        # Configurar modelo de embeddings
        embed_model = OpenAIEmbedding(
            model=model_name,
            embed_batch_size=min(len(texts_to_process), 100),  # Tamaño de batch óptimo
            api_key=settings.openai_api_key
        )
        
        # Estimar tokens para la operación
        import tiktoken
        encoder = tiktoken.encoding_for_model(model_name)
        total_tokens = sum(len(encoder.encode(text)) for text in texts_to_process)
        
        # Generar los embeddings solo para textos no cacheados
        start_time = __import__('time').time()
        
        # Método por lotes
        new_embeddings = embed_model.get_text_embedding_batch(texts_to_process)
        
        processing_time = __import__('time').time() - start_time
        
        # Registrar uso de tokens
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            token_type="embedding",
            operation="generate",
            metadata={
                "texts_count": len(texts_to_process),
                "processing_time": processing_time
            }
        )
        
        # Preparar resultado combinando caché y nuevos embeddings
        result = [None] * len(texts)
        
        # Primero los de caché
        for i, embedding in embeddings_from_cache.items():
            result[i] = embedding
            
        # Luego los nuevos
        for idx, (i, embedding) in enumerate(zip(indices_to_process, new_embeddings)):
            result[i] = embedding
            
            # Almacenar nuevos embeddings en caché
            resource_id = cache_keys[i]
            
            try:
                await CacheManager.set(
                    data_type="embedding",
                    resource_id=resource_id,
                    value=embedding,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    ttl=86400  # 24 horas
                )
            except Exception as cache_set_err:
                # Solo log en debug para errores de caché
                logger.debug(f"Error al guardar embedding en caché: {str(cache_set_err)}")
        
        return result, {"model": model_name, "cached": len(embeddings_from_cache) > 0, "generated": len(texts_to_process)}
        
    except Exception as e:
        # Capturar y reenviar cualquier excepción
        logger.error(f"Error generando embeddings con LlamaIndex: {str(e)}", exc_info=True)
        raise
