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
import aiohttp
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
    SOURCE_GENERATION,
    standardize_llama_metadata,
    track_chunk_cache_metrics,
    track_cache_metrics,
    METRIC_LATENCY,
    serialize_for_cache
)
from common.db.tables import get_table_name
from common.db.supabase import get_supabase_client
from common.core.constants import (
    METRIC_CHUNK_CACHE_HIT,
    METRIC_CHUNK_CACHE_MISS,
    METRIC_CHUNK_EMBEDDING_GENERATION
)

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
    
    # Usar la función de estandarización de metadatos ya importada al inicio del archivo
    # (No es necesario importarla aquí ya que la importamos a nivel de módulo)
    
    # Nota: Ya no necesitamos crear lista completa de hashes por adelantado
    # Los hashes se generarán de forma individual durante el procesamiento
    
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
    
    # CRÍTICO: Estandarizar metadatos base para todo el lote
    # La estandarización garantiza compatibilidad total con el sistema de caché centralizado
    # y mantiene consistencia con los otros servicios (ingestion, query) para facilitar
    # la trazabilidad de chunks/documentos y optimizar cache hits
    try:
        base_metadata = standardize_llama_metadata(
            metadata={},
            tenant_id=tenant_id,  # Campo obligatorio para multitenancy
            collection_id=collection_id,  # Para búsqueda jerárquica en caché
            ctx=ctx  # Contexto para valores por defecto
        )
    except ValueError as e:
        # Errores específicos de validación de metadatos
        logger.error(f"Error en estandarización de metadatos base: {str(e)}",
                  extra={"tenant_id": tenant_id, "collection_id": collection_id})
        # Crear metadatos mínimos para no fallar completamente
        base_metadata = {
            "tenant_id": tenant_id,
            "created_at": int(time.time())
        }
        if collection_id:
            base_metadata["collection_id"] = collection_id
    except Exception as e:
        # Errores inesperados
        logger.error(f"Error inesperado en estandarización: {str(e)}")
        raise ServiceError(
            message=f"Error preparando metadatos: {str(e)}",
            error_code=ErrorCode.PROCESSING_ERROR,
            details={"tenant_id": tenant_id, "collection_id": collection_id}
        )
    
    # Inicializar colecciones para resultados y métricas
    result = [None] * len(texts)  # Lista para guardar embeddings resultantes
    all_metrics = []  # Lista para almacenar métricas de cada texto
    
    # Procesar cada texto utilizando el patrón Cache-Aside centralizado
    for i, text in enumerate(texts):
        # Generar identificador consistente para este texto
        # Evitamos crear la lista completa de hashes por adelantado y los generamos a demanda
        text_hash = generate_resource_id_hash(text)
        
        # Crear resource_id basado en el context (con o sin chunk_id)
        current_chunk_id = chunk_id[i] if i < len(chunk_id) and chunk_id[i] else None
        
        # Construir resource_id optimizado para la búsqueda jerárquica
        if collection_id and current_chunk_id:
            # Formato: collection:chunk:hash - Mayor especificidad para caché
            resource_id = f"{collection_id}:{current_chunk_id}:{text_hash}"
        elif collection_id:
            # Formato: collection:hash - Para búsquedas por colección
            resource_id = f"{collection_id}:{text_hash}"
        elif current_chunk_id:
            # Formato: chunk:hash - Para búsquedas por chunk
            resource_id = f"{current_chunk_id}:{text_hash}"
        else:
            # Solo hash para textos sin contexto adicional
            resource_id = text_hash
        
        # Crear metadatos específicos para este texto/chunk
        chunk_specific_metadata = dict(base_metadata)
        if current_chunk_id:
            chunk_specific_metadata["chunk_id"] = current_chunk_id
        
        # Definir función para buscar en base de datos
        async def fetch_embedding_from_db(resource_id, tenant_id, ctx):
            """Busca el embedding en Supabase si existe"""
            try:
                # Si no hay collection_id, no podemos buscar en la base de datos
                if not collection_id:
                    return None
                
                # Extraer el hash del texto del resource_id (último componente)
                content_hash = resource_id.split(":")[-1] if ":" in resource_id else resource_id
                
                # Obtener cliente Supabase con timeout optimizado
                supabase = await get_supabase_client(tenant_id)
                if not supabase:
                    logger.warning(f"No se pudo obtener cliente Supabase para tenant {tenant_id}")
                    return None
                
                # Buscar embedding en la tabla correspondiente con timeout optimizado
                table_name = get_table_name("embeddings", tenant_id)
                timeout_seconds = TIMEOUTS.get("supabase_query", 10)
                
                # Consulta optimizada con filtros específicos
                result = await supabase.table(table_name).select("embedding") \
                    .filter("text_hash", "eq", content_hash) \
                    .filter("collection_id", "eq", collection_id) \
                    .limit(1) \
                    .execute(timeout=timeout_seconds)
                
                # Verificar si hay resultados válidos
                if result.data and len(result.data) > 0 and result.data[0].get("embedding"):
                    embedding = result.data[0].get("embedding")
                    metrics["db_retrieved"] += 1
                    return embedding
            except Exception as e:
                logger.warning(f"Error buscando embedding en Supabase: {str(e)}", 
                            extra={"tenant_id": tenant_id, "resource_id": resource_id})
            return None
        
        # Definir función para generar embedding si no existe
        async def generate_embedding(resource_id, tenant_id, ctx):
            """Genera un nuevo embedding usando la API y lo serializa correctamente"""
            try:
                # Obtener configuración de la API
                api_key, endpoint = await _get_embedding_config(tenant_id, model_name)
                
                # Usar valores por defecto si no hay configuración específica
                if not endpoint or not api_key:
                    if not settings.default_embedding_endpoint:
                        raise ValueError(f"No hay endpoint de embeddings configurado para {tenant_id}")
                    endpoint = settings.default_embedding_endpoint
                    api_key = settings.default_embedding_api_key
                
                # Preparar request
                headers = {"Authorization": f"Bearer {api_key}"}
                data = {"text": text, "model": model_name}
                request_timeout = TIMEOUTS.get("embedding_api", 30)  # Timeout optimizado
                
                # Realizar solicitud a la API con timeout y manejo de errores mejorado
                async with aiohttp.ClientSession() as session:
                    start_time = time.time()
                    try:
                        async with session.post(
                            endpoint, 
                            json=data, 
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=request_timeout)
                        ) as response:
                            response.raise_for_status()
                            result = await response.json()
                            latency_ms = (time.time() - start_time) * 1000
                            
                            # Obtener el embedding del resultado
                            raw_embedding = result.get("embedding")
                            if not raw_embedding:
                                raise ValueError("La API no devolvió un embedding válido")
                            
                            # Serializar para caché si es necesario
                            try:
                                embedding = serialize_for_cache(raw_embedding, "embedding")
                            except Exception as e:
                                logger.warning(f"Error serializando embedding: {str(e)}")
                                # Usar el embedding tal cual si falla la serialización
                                embedding = raw_embedding
                            
                            # Registrar uso de tokens y métricas
                            input_tokens = result.get("tokens", {}).get("input", 0)
                            
                            # Crear metadatos para métricas
                            embedding_metadata = {
                                "source": SOURCE_GENERATION,
                                "model": model_name,
                                "latency_ms": latency_ms,
                                "tokens": input_tokens,
                                "dimensions": len(embedding) if isinstance(embedding, list) else "unknown"
                            }
                            
                            # Registrar métricas de chunk si corresponde
                            current_chunk_id = chunk_id[i] if i < len(chunk_id) and chunk_id[i] else None
                            if current_chunk_id:
                                # Registrar métricas específicas de chunk
                                await track_chunk_cache_metrics(
                                    tenant_id=tenant_id,
                                    chunk_id=current_chunk_id,
                                    metric_type=METRIC_CHUNK_CACHE_MISS,
                                    collection_id=collection_id,
                                    model_name=model_name,
                                    extra_metadata={**chunk_specific_metadata, **embedding_metadata}
                                )
                                
                                await track_chunk_cache_metrics(
                                    tenant_id=tenant_id,
                                    chunk_id=current_chunk_id,
                                    metric_type=METRIC_CHUNK_EMBEDDING_GENERATION,
                                    collection_id=collection_id,
                                    model_name=model_name,
                                    extra_metadata={**chunk_specific_metadata, **embedding_metadata}
                                )
                            
                            # Registrar uso de tokens con el sistema centralizado
                            await track_token_usage(
                                tenant_id=tenant_id,
                                tokens=input_tokens,
                                model=model_name,
                                token_type="embedding",
                                operation="generate",
                                metadata=embedding_metadata
                            )
                            
                            # Actualizar métricas globales
                            metrics["generated"] += 1
                            
                            return embedding
                    except aiohttp.ClientError as e:
                        # Manejo específico para errores de red
                        logger.error(f"Error de red al generar embedding: {str(e)}")
                        raise ServiceError(
                            message=f"Error de conexión con el servicio de embeddings: {str(e)}",
                            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR
                        )
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
            conversation_id=ctx.get_conversation_id() if ctx else None,
            collection_id=collection_id,
            ctx=ctx
            # TTL se determina automáticamente por tipo de dato
        )
        
        # Guardar resultado y métricas
        if embedding:
            result[i] = embedding
            all_metrics.append(text_metrics)
            
            # Actualizar métricas globales
            if text_metrics.get("source") == SOURCE_CACHE:
                metrics["cached"] += 1
                
                # Registrar métrica de hit para chunks cuando sea apropiado
                current_chunk_id = chunk_id[i] if i < len(chunk_id) and chunk_id[i] else None
                if current_chunk_id:
                    try:
                        await track_chunk_cache_metrics(
                            tenant_id=tenant_id,
                            chunk_id=current_chunk_id,
                            metric_type=METRIC_CHUNK_CACHE_HIT,
                            collection_id=collection_id,
                            model_name=model_name,
                            extra_metadata=chunk_specific_metadata
                        )
                    except Exception as e:
                        # Solo log, no interrumpe flujo principal
                        logger.debug(f"Error registrando métrica de chunk cache hit: {str(e)}")
    
    # Calcular tiempo total de procesamiento
    total_time_ms = (time.time() - start_time) * 1000
    metrics["total_time_ms"] = total_time_ms
    
    # Registrar latencia total para monitoreo
    try:
        await track_cache_metrics(
            data_type="embedding_batch",
            tenant_id=tenant_id,
            metric_type=METRIC_LATENCY,
            value=total_time_ms,
            collection_id=collection_id,
            metadata={
                "model": model_name,
                "batch_size": len(texts),
                "cached_ratio": metrics["cached"] / len(texts) if texts else 0,
                "generated_ratio": metrics["generated"] / len(texts) if texts else 0
            }
        )
    except Exception as e:
        # No interrumpir el flujo principal por errores de métricas
        logger.debug(f"Error registrando métricas de latencia: {str(e)}")
    
    # Devolver resultados con metadatos optimizados
    return result, {
        "model": model_name,
        "metrics": metrics,
        # Limitar detalle de métricas para evitar sobrecarga de memoria
        "detail_metrics": all_metrics[:10] if len(all_metrics) <= 10 else f"{len(all_metrics)} texts processed"
    }
