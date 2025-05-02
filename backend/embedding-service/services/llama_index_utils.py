"""
Utilidades para integración con LlamaIndex.

Este módulo proporciona funciones auxiliares para trabajar con LlamaIndex,
asegurando compatibilidad con el servicio de ingestión y otros servicios.

# ATENCIÓN: PATRÓN CACHE-ASIDE CENTRALIZADO
# Este archivo implementa el patrón Cache-Aside optimizado para embeddings, usando exclusivamente
# get_with_cache_aside (common.cache) para todas las operaciones de caché de embeddings. Está alineado
# con las políticas de caché, jerarquía de claves y serialización estándar de la arquitectura RAG.
# Cualquier modificación debe mantener este estándar y evitar lógica de caché personalizada.
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple

# Importación de configuración centralizada
from config.constants import (
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    TIMEOUTS,
    QUALITY_THRESHOLDS
)
from config.settings import get_settings

# Importaciones comunes
from common.errors import handle_errors, ServiceError, ErrorCode
from common.context import with_context, Context
from common.config.tiers import get_available_embedding_models
from common.auth.models import validate_model_access
from common.tracking import track_token_usage
from common.cache import (
    get_with_cache_aside,
    generate_resource_id_hash,
    get_default_ttl_for_data_type,
    SOURCE_CACHE, 
    SOURCE_SUPABASE, 
    SOURCE_GENERATION
)
from common.db.tables import get_table_name
from common.db.supabase import get_supabase_client

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
    collection_id: str = None,
    chunk_id: List[str] = None,
    ctx: Context = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Genera embeddings para textos usando LlamaIndex.
    
    Implementa el patrón Cache-Aside optimizado utilizando la implementación
    centralizada para asegurar consistencia entre servicios.
    
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
    # Inicializar métricas y resultados
    start_time = time.time()
    metrics = {
        "total_texts": len(texts),
        "cached": 0,
        "db_retrieved": 0,
        "generated": 0
    }
    
    # Validar parámetros
    if not texts:
        return [], {"model": model_name or settings.default_embedding_model, "metrics": metrics}
    
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
    
    # Crear hashes para los textos usando método estandarizado
    text_hashes = [generate_resource_id_hash(text) for text in texts]
    
    # Normalizar chunk_ids si se proporcionan
    if chunk_id and len(chunk_id) > 0:
        # Asegurar que hay un chunk_id para cada texto
        if len(chunk_id) < len(texts):
            # Rellenar con None los faltantes
            chunk_id = chunk_id + [None] * (len(texts) - len(chunk_id))
        elif len(chunk_id) > len(texts):
            # Recortar si hay demasiados
            chunk_id = chunk_id[:len(texts)]
    else:
        chunk_id = [None] * len(texts)
    
    # Procesar cada texto con el patrón Cache-Aside centralizado
    # Obtener resultados de caché
    cache_results = {}
    cache_hits = 0
    
    for i, text in enumerate(texts):
        # Si ya tenemos embedding en caché, guardar el índice
        if i in cache_entries and cache_entries[i] is not None:
            cache_results[i] = cache_entries[i]
            cache_hits += 1
            
            # Registrar métrica específica de chunk si hay chunk_id disponible
            if chunk_id and i < len(chunk_id) and chunk_id[i]:
                try:
                    from common.cache.helpers import track_chunk_cache_metrics
                    from common.core.constants import METRIC_CHUNK_CACHE_HIT
                    await track_chunk_cache_metrics(
                        tenant_id=tenant_id,
                        chunk_id=chunk_id[i],
                        metric_type=METRIC_CHUNK_CACHE_HIT,
                        collection_id=collection_id,
                        model_name=model_name
                    )
                except Exception as e:
                    # No interrumpir el flujo principal si falla el tracking
                    logger.debug(f"Error registrando métrica de chunk cache hit: {str(e)}")
                    
        # Generar identificador consistente para este texto
        # Si tenemos un chunk_id, lo usamos para formar una clave de caché más específica
        if chunk_id and i < len(chunk_id) and chunk_id[i]:
            resource_id = f"{model_name}:{chunk_id[i]}:{text_hashes[i]}"
        else:
            resource_id = f"{model_name}:{text_hashes[i]}"
        
        # Definir función para buscar en base de datos
        async def fetch_embedding_from_db(resource_id, tenant_id, ctx):
            """Busca el embedding en Supabase"""
            try:
                # Extraer el hash del texto del resource_id
                content_hash = resource_id.split(":", 1)[1] if ":" in resource_id else resource_id
                
                # Obtener cliente y tabla
                supabase = get_supabase_client()
                table_name = get_table_name("document_chunks")
                
                # Buscar embedding por hash de contenido
                query_result = (supabase.table(table_name)
                             .select("embedding")
                             .eq("tenant_id", tenant_id)
                             .eq("content_hash", content_hash)
                             .limit(1)
                             .execute())
                             
                if query_result.data and len(query_result.data) > 0:
                    embedding = query_result.data[0].get("embedding")
                    if embedding:
                        return embedding
            except Exception as e:
                logger.warning(f"Error buscando embedding en Supabase: {str(e)}")
            return None
        
        # Definir función para generar embedding si no existe
        async def generate_embedding(resource_id, tenant_id, ctx):
            """Genera un nuevo embedding usando la API"""
            try:
                # Acceder al embedding_endpoint según tenant y configuración
                api_key, endpoint = await _get_embedding_config(tenant_id, model_name)
                
                # Si no hay configuración, usar endpoint por defecto
                if not endpoint or not api_key:
                    if not settings.default_embedding_endpoint:
                        raise ValueError(f"No hay endpoint de embeddings configurado para {tenant_id}")
                    endpoint = settings.default_embedding_endpoint
                    api_key = settings.default_embedding_api_key
                
                # Realizar solicitud a la API
                headers = {"Authorization": f"Bearer {api_key}"}
                data = {"text": text, "model": model_name}
                
                async with aiohttp.ClientSession() as session:
                    start_time = time.time()
                    async with session.post(endpoint, json=data, headers=headers) as response:
                        response.raise_for_status()
                        result = await response.json()
                        latency_ms = (time.time() - start_time) * 1000
                        
                        # Registrar uso de tokens
                        input_tokens = result.get("tokens", {}).get("input", 0)
                        
                        # Registrar métrica específica de chunk si hay chunk_id disponible
                        if chunk_id and i < len(chunk_id) and chunk_id[i]:
                            from common.cache.helpers import track_chunk_cache_metrics
                            from common.core.constants import METRIC_CHUNK_CACHE_MISS, METRIC_CHUNK_EMBEDDING_GENERATION
                            await track_chunk_cache_metrics(
                                tenant_id=tenant_id,
                                chunk_id=chunk_id[i],
                                metric_type=METRIC_CHUNK_CACHE_MISS,
                                collection_id=collection_id,
                                model_name=model_name,
                                extra_metadata={"latency_ms": latency_ms, "tokens": input_tokens}
                            )
                            
                            # También registrar generación de embedding
                            await track_chunk_cache_metrics(
                                tenant_id=tenant_id,
                                chunk_id=chunk_id[i],
                                metric_type=METRIC_CHUNK_EMBEDDING_GENERATION,
                                collection_id=collection_id,
                                model_name=model_name,
                                extra_metadata={"latency_ms": latency_ms, "tokens": input_tokens}
                            )
                        
                        await track_token_usage(
                            tenant_id=tenant_id,
                            tokens=input_tokens,
                            model=model_name,
                            token_type="embedding",
                            operation="generate",
                            metadata={"source": "llama_index_utils", "endpoint": endpoint}
                        )
                        
                        # Devolver el embedding generado
                        return result.get("embedding")
            except Exception as e:
                logger.error(f"Error generando embedding: {str(e)}")
                return None
        
        # Obtener embedding usando el patrón Cache-Aside centralizado
        embedding, text_metrics = await get_with_cache_aside(
            data_type="embedding",
            resource_id=resource_id,
            tenant_id=tenant_id,
            fetch_from_db_func=fetch_embedding_from_db,
            generate_func=generate_embedding,
            agent_id=ctx.get_agent_id() if ctx else None,
            ctx=ctx,
            # TTL se determina automáticamente por tipo de dato
        )
        
        # Guardar resultado y métricas
        if embedding:
            result[i] = embedding
            all_metrics.append(text_metrics)
            
            # Actualizar métricas globales
            if text_metrics.get("source") == SOURCE_CACHE:
                metrics["cached"] += 1
            elif text_metrics.get("source") == SOURCE_SUPABASE:
                metrics["db_retrieved"] += 1
            elif text_metrics.get("source") == SOURCE_GENERATION:
                metrics["generated"] += 1
    
    # Calcular tiempo total de procesamiento
    metrics["total_time_ms"] = (time.time() - start_time) * 1000
    
    return result, {
        "model": model_name,
        "metrics": metrics,
        "detail_metrics": all_metrics if len(all_metrics) <= 5 else f"{len(all_metrics)} texts processed"
    }
