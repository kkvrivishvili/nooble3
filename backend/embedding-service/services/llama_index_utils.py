"""
Utilidades para integración con LlamaIndex.

Este módulo proporciona funciones auxiliares para trabajar con LlamaIndex,
asegurando compatibilidad con el servicio de ingestión y otros servicios.
"""

import logging
import hashlib
import time
import sys
import json
from typing import List, Dict, Any, Optional, Tuple

from common.config import get_settings
from common.errors import handle_errors, ServiceError, ErrorCode
from common.context import with_context, Context
from common.config.tiers import get_available_embedding_models
from common.auth.models import validate_model_access
from common.tracking import track_token_usage
from common.cache.manager import CacheManager
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
    ctx: Context = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Genera embeddings para textos usando LlamaIndex.
    
    Implementación siguiendo el patrón Cache-Aside optimizado:
    1. Verificar caché primero
    2. Si no está en caché, verificar en Supabase
    3. Si no está en Supabase, generar nuevo embedding
    4. Almacenar en caché para futuras consultas
    
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
        # Métricas para seguimiento de rendimiento
        start_time = time.time()
        metrics = {
            "cache_hits": 0,
            "supabase_hits": 0,
            "generated": 0,
            "total_texts": len(texts)
        }
        
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
        
        # Crear hashes para los textos - usando método consistente
        text_hashes = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
        
        # Generar claves de caché
        cache_keys = []
        embeddings_from_cache = {}
        
        # 1. VERIFICAR CACHÉ - Paso 1 del patrón Cache-Aside
        cache_check_start = time.time()
        for i, text in enumerate(texts):
            # Crear clave de caché usando formato estandarizado
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
                    metrics["cache_hits"] += 1
                    
                    # Registrar latencia de caché
                    await track_cache_metric(
                        data_type="embedding",
                        tenant_id=tenant_id,
                        source="cache",
                        latency_ms=(time.time() - start_time) * 1000
                    )
            except Exception as cache_err:
                # Solo log en debug para errores de caché
                logger.debug(f"Error al obtener embedding de caché: {str(cache_err)}")
                
        # Registrar métrica de verificación de caché
        cache_check_time = (time.time() - cache_check_start) * 1000
        logger.debug(f"Verificación de caché completada en {cache_check_time:.2f}ms")
                
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
            
            # Registrar métrica de caché completa
            metrics["total_time_ms"] = (time.time() - start_time) * 1000
            await track_cache_hit("embedding", tenant_id, True)
            
            return embeddings, {"model": model_name, "cached": True, "metrics": metrics}
            
        # Identificar textos que necesitan búsqueda en DB o procesamiento
        texts_to_check_db = []
        indices_to_check_db = []
        
        for i, text in enumerate(texts):
            if i not in embeddings_from_cache:
                texts_to_check_db.append(text)
                indices_to_check_db.append(i)
        
        # 2. VERIFICAR EN SUPABASE - Paso 2 del patrón Cache-Aside
        embeddings_from_db = {}
        if texts_to_check_db:
            db_check_start = time.time()
            
            # Obtener cliente Supabase y nombre de tabla
            supabase = get_supabase_client()
            table_name = get_table_name("document_chunks")
            
            # Verificar en lotes para optimizar consultas
            for i, idx in enumerate(indices_to_check_db):
                text = texts_to_check_db[i]
                text_hash = text_hashes[idx]
                
                try:
                    # Buscar si existe embedding previamente calculado
                    result = (supabase.table(table_name)
                             .select("embedding")
                             .eq("tenant_id", tenant_id)
                             .eq("content_hash", text_hash)
                             .limit(1)
                             .execute())
                             
                    if result.data and len(result.data) > 0:
                        embedding = result.data[0].get("embedding")
                        if embedding:
                            embeddings_from_db[idx] = embedding
                            metrics["supabase_hits"] += 1
                            
                            # Guardar en caché para futuras consultas
                            resource_id = cache_keys[idx]
                            await CacheManager.set(
                                data_type="embedding",
                                resource_id=resource_id,
                                value=embedding,
                                tenant_id=tenant_id,
                                agent_id=ctx.get_agent_id() if ctx else None,
                                ttl=CacheManager.ttl_extended  # 24 horas
                            )
                            
                            # Registrar latencia de DB
                            await track_cache_metric(
                                data_type="embedding",
                                tenant_id=tenant_id,
                                source="supabase",
                                latency_ms=(time.time() - db_check_start) * 1000
                            )
                except Exception as db_err:
                    logger.warning(f"Error al buscar embedding en Supabase: {str(db_err)}")
            
            # Registrar métrica de verificación en DB
            db_check_time = (time.time() - db_check_start) * 1000
            logger.debug(f"Verificación en Supabase completada en {db_check_time:.2f}ms")
        
        # Si todos los embeddings están en caché o DB, devolverlos directamente
        if len(embeddings_from_cache) + len(embeddings_from_db) == len(texts):
            logger.info(f"Embeddings obtenidos de caché ({len(embeddings_from_cache)}) y DB ({len(embeddings_from_db)})")
            
            # Preparar resultado combinando caché y DB
            result = [None] * len(texts)
            
            # Primero los de caché
            for i, embedding in embeddings_from_cache.items():
                result[i] = embedding
                
            # Luego los de DB
            for i, embedding in embeddings_from_db.items():
                result[i] = embedding
            
            # Registrar métrica de caché + DB completa
            metrics["total_time_ms"] = (time.time() - start_time) * 1000
            
            return result, {"model": model_name, "cached": True, "db_retrieved": True, "metrics": metrics}
        
        # 3. GENERAR NUEVOS EMBEDDINGS - Paso 3 del patrón Cache-Aside
        # Identificar textos que necesitan procesamiento
        texts_to_process = []
        indices_to_process = []
        
        for i, idx in enumerate(indices_to_check_db):
            if idx not in embeddings_from_db:
                texts_to_process.append(texts_to_check_db[i])
                indices_to_process.append(idx)
        
        metrics["generated"] = len(texts_to_process)
        
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
        generation_start = time.time()
        
        # Método por lotes
        new_embeddings = embed_model.get_text_embedding_batch(texts_to_process)
        
        generation_time = time.time() - generation_start
        
        # Registrar uso de tokens
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            token_type="embedding",
            operation="generate",
            metadata={
                "texts_count": len(texts_to_process),
                "processing_time": generation_time
            }
        )
        
        # Registrar latencia de generación
        await track_cache_metric(
            data_type="embedding",
            tenant_id=tenant_id,
            source="generation",
            latency_ms=generation_time * 1000
        )
        
        # Registrar métrica de caché miss
        for _ in range(len(texts_to_process)):
            await track_cache_hit("embedding", tenant_id, False)
        
        # 4. PREPARAR RESULTADO FINAL - Combinando todas las fuentes
        result = [None] * len(texts)
        
        # Primero los de caché
        for i, embedding in embeddings_from_cache.items():
            result[i] = embedding
            
        # Luego los de DB
        for i, embedding in embeddings_from_db.items():
            result[i] = embedding
            
        # Finalmente los nuevos
        for idx, (i, embedding) in enumerate(zip(indices_to_process, new_embeddings)):
            # Asegurar que el embedding sea una lista Python estándar
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
                
            result[i] = embedding
            
            # Almacenar nuevos embeddings en caché - Paso 4 del patrón Cache-Aside
            resource_id = cache_keys[i]
            
            try:
                # Calcular tamaño aproximado para métricas
                embedding_size = sys.getsizeof(json.dumps(embedding))
                
                await CacheManager.set(
                    data_type="embedding",
                    resource_id=resource_id,
                    value=embedding,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    ttl=CacheManager.ttl_extended  # 24 horas
                )
                
                # Registrar tamaño en caché
                await track_cache_size("embedding", tenant_id, embedding_size)
                
            except Exception as cache_set_err:
                logger.debug(f"Error al guardar embedding en caché: {str(cache_set_err)}")
        
        # Registrar tiempo total
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        
        return result, {
            "model": model_name, 
            "metrics": metrics
        }
        
    except Exception as e:
        # Capturar y reenviar cualquier excepción
        logger.error(f"Error generando embeddings con LlamaIndex: {str(e)}", exc_info=True)
        raise

# Funciones auxiliares para métricas

async def track_cache_hit(data_type: str, tenant_id: str, hit: bool):
    """Registra un acierto o fallo de caché."""
    metric_type = "cache_hit" if hit else "cache_miss"
    try:
        await CacheManager.increment_counter(
            counter_type=metric_type,
            amount=1,
            resource_id=data_type,
            tenant_id=tenant_id
        )
    except Exception as e:
        logger.debug(f"Error al registrar métrica de caché: {str(e)}")

async def track_cache_metric(data_type: str, tenant_id: str, source: str, latency_ms: float):
    """Registra la latencia de recuperación de datos."""
    try:
        await CacheManager.increment_counter(
            counter_type="latency",
            amount=int(latency_ms),  # Convertir a entero para contador
            resource_id=f"{data_type}_{source}",  # cache, supabase, generation
            tenant_id=tenant_id,
            metadata={"latency_ms": latency_ms}
        )
    except Exception as e:
        logger.debug(f"Error al registrar métrica de latencia: {str(e)}")

async def track_cache_size(data_type: str, tenant_id: str, size_bytes: int):
    """Registra el tamaño de los datos almacenados en caché."""
    try:
        await CacheManager.increment_counter(
            counter_type="cache_size",
            amount=size_bytes,
            resource_id=data_type,
            tenant_id=tenant_id
        )
    except Exception as e:
        logger.debug(f"Error al registrar métrica de tamaño: {str(e)}")
