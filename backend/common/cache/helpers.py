"""
Funciones auxiliares para implementar el patrón Cache-Aside.

Este módulo proporciona una implementación centralizada y estandarizada 
del patrón Cache-Aside para todos los servicios del sistema RAG.
"""

import logging
import time
import sys
import json
import hashlib
from typing import Dict, List, Any, Optional, Callable, Tuple, Union, TypeVar

# Eliminamos la importación circular
# from common.cache.manager import CacheManager
from common.context import Context
# Eliminamos la importación circular
# from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

# Importar constantes desde el módulo principal
from common.cache import (
    SOURCE_CACHE, SOURCE_SUPABASE, SOURCE_GENERATION,
    METRIC_CACHE_HIT, METRIC_CACHE_MISS, METRIC_LATENCY, METRIC_CACHE_SIZE,
    METRIC_CACHE_INVALIDATION, METRIC_CACHE_INVALIDATION_COORDINATED,
    METRIC_SERIALIZATION_ERROR, METRIC_DESERIALIZATION_ERROR,
    DEFAULT_TTL_MAPPING, TTL_STANDARD
)

logger = logging.getLogger(__name__)

# Tipo genérico para resultados de caché
T = TypeVar('T')

async def get_with_cache_aside(
    data_type: str,
    resource_id: str,
    tenant_id: str,
    fetch_from_db_func: Callable,
    generate_func: Optional[Callable] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    ctx: Optional[Context] = None,
    ttl: Optional[int] = None,
    serializer: Optional[Callable] = None,
    deserializer: Optional[Callable] = None
) -> Tuple[Optional[T], Dict[str, Any]]:
    """
    Implementación centralizada del patrón Cache-Aside para el sistema RAG.
    
    Sigue el flujo estándar:
    1. Verificar caché primero
    2. Si no está en caché, buscar en Supabase mediante fetch_from_db_func
    3. Si no está en BD, generar dato (si se proporciona generate_func)
    4. Almacenar en caché con TTL adecuado según el tipo de dato
    5. Retornar dato con métricas unificadas del proceso
    
    Este método garantiza consistencia en la implementación del patrón en
    todos los servicios (ingestion, embedding, query, agent).
    
    Args:
        data_type: Tipo de datos ("embedding", "vector_store", "agent_config", etc.)
        resource_id: ID único del recurso
        tenant_id: ID del tenant
        fetch_from_db_func: Función async que busca el dato en Supabase
                          (recibe params: resource_id, tenant_id, ctx)
        generate_func: Función async opcional para generar el dato si no existe
                     (recibe params: resource_id, tenant_id, ctx, **kwargs)
        agent_id, conversation_id, collection_id: Contexto adicional opcional
        ctx: Contexto de la operación
        ttl: Tiempo de vida en segundos (si None, usa valor predeterminado por tipo)
        serializer: Función para serializar el objeto antes de almacenar en caché
        deserializer: Función para deserializar el objeto al recuperar de caché
        
    Returns:
        Tuple[Optional[Any], Dict[str, Any]]: 
            - El dato recuperado o generado (o None si no existe)
            - Diccionario con métricas y metadatos del proceso
    """
    # Métricas para seguimiento de rendimiento
    start_time = time.time()
    metrics = {
        "source": None,
        "data_type": data_type,
        "resource_id": resource_id,
    }
    
    # Si no se proporcionan funciones de serialización, usar las predeterminadas
    if serializer is None:
        serializer = lambda x: serialize_for_cache(x, data_type)
    if deserializer is None:
        deserializer = lambda x: deserialize_from_cache(x, data_type)
    
    # Validar parámetros obligatorios
    if not tenant_id:
        logger.warning(f"Tenant ID es obligatorio para Cache-Aside en {data_type}")
        metrics["source"] = "error"
        metrics["error"] = "missing_tenant_id"
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        return None, metrics
    
    if not resource_id:
        logger.warning(f"Resource ID es obligatorio para Cache-Aside en {data_type}")
        metrics["source"] = "error"
        metrics["error"] = "missing_resource_id"
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        return None, metrics
    
    # 1. VERIFICAR CACHÉ - Paso 1 del patrón Cache-Aside
    cache_check_start = time.time()
    
    try:
        from common.cache.manager import CacheManager
        cached_value = await CacheManager.get(
            data_type=data_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            search_hierarchy=True,
            use_memory=True
        )
        
        cache_check_time = time.time() - cache_check_start
        
        if cached_value:
            # Deserializar valor de caché si es necesario
            deserialize_success = True
            if deserializer:
                try:
                    cached_value = deserializer(cached_value)
                except Exception as deserialize_err:
                    deserialize_success = False
                    logger.warning(f"Error deserializando valor de caché: {str(deserialize_err)}")
                    # Registrar error de deserialización en métricas y considerar como caché miss
                    await track_cache_metrics(
                        data_type=data_type,
                        tenant_id=tenant_id,
                        metric_type=METRIC_DESERIALIZATION_ERROR,
                        value=1,
                        metadata={"source": SOURCE_CACHE, "error": str(deserialize_err)}
                    )
            
            # Continuar solo si la deserialización fue exitosa
            if deserialize_success:
                # Registrar acierto y latencia de caché
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_CACHE_HIT,
                    value=True,
                    metadata={"source": SOURCE_CACHE, "latency_ms": cache_check_time * 1000}
                )
                
                metrics["source"] = SOURCE_CACHE
                metrics["latency_ms"] = cache_check_time * 1000
                metrics["total_time_ms"] = (time.time() - start_time) * 1000
                
                logger.debug(f"Dato de tipo {data_type} (id: {resource_id}) obtenido de caché")
                return cached_value, metrics
    except Exception as cache_err:
        logger.debug(f"Error accediendo a caché para {data_type}: {str(cache_err)}")
    
    # Registrar fallo de caché
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type=METRIC_CACHE_MISS,
        value=True,
        metadata={"source": "miss"}  # Añadir metadato para la fuente
    )
    
    # 2. OBTENER DE SUPABASE - Paso 2 del patrón Cache-Aside
    db_start_time = time.time()
    
    try:
        db_value = await fetch_from_db_func(resource_id, tenant_id, ctx)
        
        db_time = time.time() - db_start_time
        
        # Registrar latencia de BD
        await track_cache_metrics(
            data_type=data_type,
            tenant_id=tenant_id,
            metric_type=METRIC_LATENCY,
            value=db_time * 1000,
            metadata={"source": SOURCE_SUPABASE}
        )
        
        if db_value:
            # Serializar valor antes de guardarlo en caché
            try:
                cache_value = serializer(db_value) if serializer else db_value
            except Exception as serialize_err:
                logger.warning(f"Error serializando valor de BD para {data_type}: {str(serialize_err)}")
                # Registrar métrica de error de serialización
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_SERIALIZATION_ERROR,
                    value=1,
                    metadata={"source": SOURCE_SUPABASE, "error": str(serialize_err)}
                )
                # En caso de error de serialización, aún podemos retornar el valor original
                metrics["source"] = SOURCE_SUPABASE
                metrics["latency_ms"] = db_time * 1000
                metrics["total_time_ms"] = (time.time() - start_time) * 1000
                metrics["serialization_error"] = True
                return db_value, metrics
            
            # Determinar TTL adecuado para el tipo de dato
            if ttl is None:
                ttl = get_default_ttl_for_data_type(data_type)
            
            # Guardar en caché para futuras consultas
            try:
                from common.cache.manager import CacheManager
                # Estimar tamaño para métricas
                size_estimate = estimate_object_size(cache_value)
                
                # Guardar en caché con el valor serializado
                await CacheManager.set(
                    data_type=data_type,
                    resource_id=resource_id,
                    value=cache_value,  # Valor ya serializado
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    collection_id=collection_id,
                    ttl=ttl
                )
                
                # Registrar tamaño en caché
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_CACHE_SIZE,
                    value=size_estimate
                )
                logger.debug(f"Dato de tipo {data_type} (id: {resource_id}) almacenado en caché")
            except Exception as cache_set_err:
                logger.warning(f"Error almacenando en caché {data_type}: {str(cache_set_err)}")
            
            metrics["source"] = SOURCE_SUPABASE
            metrics["latency_ms"] = db_time * 1000
            metrics["total_time_ms"] = (time.time() - start_time) * 1000
            
            return db_value, metrics
    except Exception as db_err:
        logger.warning(f"Error obteniendo {data_type} de base de datos: {str(db_err)}")
    
    # 3. GENERAR DATO - Paso 3 del patrón Cache-Aside (opcional)
    if generate_func is None:
        # Si no se proporciona función para generar, retornar None
        metrics["source"] = "not_found"
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        logger.debug(f"Dato de tipo {data_type} (id: {resource_id}) no encontrado")
        return None, metrics
    
    # Intentar generar el dato
    generation_start = time.time()
    
    try:
        generated_value = await generate_func(resource_id, tenant_id, ctx)
        generation_time = time.time() - generation_start
        
        # Registrar latencia de generación
        await track_cache_metrics(
            data_type=data_type,
            tenant_id=tenant_id,
            metric_type=METRIC_LATENCY,
            value=generation_time * 1000,
            metadata={"source": SOURCE_GENERATION}
        )
        
        if generated_value:
            # Serializar valor antes de guardarlo en caché
            try:
                cache_value = serializer(generated_value) if serializer else generated_value
            except Exception as serialize_err:
                logger.warning(f"Error serializando valor generado para {data_type}: {str(serialize_err)}")
                # Registrar métrica de error de serialización
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_SERIALIZATION_ERROR,
                    value=1,
                    metadata={"source": SOURCE_GENERATION, "error": str(serialize_err)}
                )
                # En caso de error de serialización, aún podemos retornar el valor original
                metrics["source"] = SOURCE_GENERATION
                metrics["latency_ms"] = generation_time * 1000
                metrics["total_time_ms"] = (time.time() - start_time) * 1000
                metrics["serialization_error"] = True
                return generated_value, metrics
            
            # Determinar TTL adecuado para el tipo de dato
            if ttl is None:
                ttl = get_default_ttl_for_data_type(data_type)
                
            # Guardar en caché
            try:
                from common.cache.manager import CacheManager
                # Estimar tamaño para métricas
                size_estimate = estimate_object_size(cache_value)
                
                # Guardar en caché con el valor serializado
                await CacheManager.set(
                    data_type=data_type,
                    resource_id=resource_id,
                    value=cache_value,  # Valor ya serializado
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    collection_id=collection_id,
                    ttl=ttl
                )
                
                # Registrar tamaño en caché
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_CACHE_SIZE,
                    value=size_estimate
                )
                logger.debug(f"Dato generado de tipo {data_type} (id: {resource_id}) almacenado en caché")
            except Exception as cache_set_err:
                logger.warning(f"Error almacenando en caché dato generado {data_type}: {str(cache_set_err)}")
            
            metrics["source"] = SOURCE_GENERATION
            metrics["latency_ms"] = generation_time * 1000
            metrics["total_time_ms"] = (time.time() - start_time) * 1000
            
            return generated_value, metrics
    except Exception as gen_err:
        logger.error(f"Error generando {data_type}: {str(gen_err)}")
    
    # Si llegamos aquí, no se pudo obtener ni generar el dato
    metrics["source"] = "error"
    metrics["total_time_ms"] = (time.time() - start_time) * 1000
    
    return None, metrics

async def invalidate_coordinated(
    tenant_id: str,
    primary_data_type: str,
    primary_resource_id: str,
    related_invalidations: List[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None
) -> Dict[str, int]:
    """
    Realiza invalidación coordinada de caché para múltiples recursos relacionados.
    
    Args:
        tenant_id: ID del tenant
        primary_data_type: Tipo de datos principal a invalidar
        primary_resource_id: ID del recurso principal
        related_invalidations: Lista de diccionarios con invalidaciones relacionadas
                               [{"data_type": str, "resource_id": str, ...}]
        agent_id, conversation_id, collection_id: Contexto adicional opcional
        
    Returns:
        Dict[str, int]: Diccionario con conteo de claves invalidadas por tipo
    """
    # Validar parámetros obligatorios
    if not tenant_id:
        logger.warning("Tenant ID es obligatorio para invalidación coordinada")
        return {primary_data_type: 0}
    
    if not primary_data_type or not primary_resource_id:
        logger.warning("Data type y resource ID son obligatorios para invalidación coordinada")
        return {primary_data_type: 0}
    
    invalidation_counts = {primary_data_type: 0}
    
    # 1. Invalidar recurso principal
    try:
        from common.cache.manager import CacheManager
        # Registrar métrica de invalidación coordinada
        await track_cache_metrics(
            data_type=primary_data_type,
            tenant_id=tenant_id,
            metric_type=METRIC_CACHE_INVALIDATION_COORDINATED,
            value=1,
            agent_id=agent_id,
            metadata={
                "resource_id": primary_resource_id,
                "related_count": len(related_invalidations) if related_invalidations else 0
            }
        )
        
        deleted = await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type=primary_data_type,
            resource_id=primary_resource_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id
        )
        invalidation_counts[primary_data_type] = deleted
        logger.debug(f"Invalidadas {deleted} claves para {primary_data_type} (id: {primary_resource_id})")
    except Exception as e:
        logger.warning(f"Error invalidando {primary_data_type}: {str(e)}")
    
    # 2. Invalidar recursos relacionados
    if related_invalidations:
        for related in related_invalidations:
            rel_type = related.get("data_type")
            rel_id = related.get("resource_id")
            rel_agent_id = related.get("agent_id", agent_id)
            rel_conv_id = related.get("conversation_id", conversation_id)
            rel_coll_id = related.get("collection_id", collection_id)
            
            if rel_type not in invalidation_counts:
                invalidation_counts[rel_type] = 0
                
            try:
                from common.cache.manager import CacheManager
                deleted = await CacheManager.invalidate(
                    tenant_id=tenant_id,
                    data_type=rel_type,
                    resource_id=rel_id,
                    agent_id=rel_agent_id,
                    conversation_id=rel_conv_id,
                    collection_id=rel_coll_id
                )
                invalidation_counts[rel_type] += deleted
                logger.debug(f"Invalidadas {deleted} claves relacionadas para {rel_type}")
            except Exception as e:
                logger.warning(f"Error invalidando {rel_type} relacionado: {str(e)}")
    
    return invalidation_counts

async def invalidate_resource_cache(
    data_type: str,
    resource_id: str,
    tenant_id: str,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None
) -> bool:
    """
    Invalida la caché para un recurso específico.
    
    Esta función proporciona una interfaz simple para invalidar recursos en caché
    siguiendo el mismo patrón de nombrado usado por get_with_cache_aside.
    
    Args:
        data_type: Tipo de datos ("embedding", "vector_store", "agent_config", etc.)
        resource_id: ID único del recurso
        tenant_id: ID del tenant
        agent_id, conversation_id, collection_id: Contexto adicional opcional
        
    Returns:
        bool: True si la invalidación fue exitosa
    """
    # Validar parámetros obligatorios
    if not tenant_id:
        logger.warning(f"Tenant ID es obligatorio para invalidar caché de {data_type}")
        return False
    
    if not resource_id:
        logger.warning(f"Resource ID es obligatorio para invalidar caché de {data_type}")
        return False
    
    # Registrar métrica de invalidación antes de intentar la operación
    try:
        from common.cache.manager import CacheManager
        # Registrar métrica de invalidación
        await track_cache_metrics(
            data_type=data_type,
            tenant_id=tenant_id,
            metric_type=METRIC_CACHE_INVALIDATION,
            value=1,
            agent_id=agent_id,
            metadata={"resource_id": resource_id}
        )
        
        deleted = await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type=data_type,
            resource_id=resource_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id
        )
        
        logger.debug(f"Invalidadas {deleted} claves para {data_type}:{resource_id}")
        return deleted > 0
    except Exception as e:
        logger.warning(f"Error invalidando caché para {data_type}:{resource_id}: {str(e)}")
        return False

async def invalidate_document_update(
    tenant_id: str,
    document_id: str,
    collection_id: Optional[str] = None
) -> Dict[str, int]:
    """
    Invalidación especializada para actualizaciones de documentos en el sistema RAG.
    
    Cuando se actualiza un documento, esta función invalida automáticamente:
    1. La caché del documento mismo
    2. Los embeddings relacionados con el documento
    3. El vector store de la colección
    4. Las consultas que pudieron haber usado ese documento
    
    Esta invalidación coordinada mantiene la consistencia del sistema
    después de actualizaciones, asegurando que no se usen datos obsoletos.
    
    Args:
        tenant_id: ID del tenant
        document_id: ID del documento actualizado
        collection_id: ID de la colección a la que pertenece el documento (opcional)
        
    Returns:
        Dict[str, int]: Diccionario con conteo de claves invalidadas por tipo
    """
    # Preparar invalidaciones relacionadas
    invalidations = [
        {"data_type": "embedding", "resource_id": f"doc:{document_id}"},
        {"data_type": "retrieval_cache", "resource_id": "*"}
    ]
    
    # Añadir invalidación del vector store si tenemos collection_id
    if collection_id:
        invalidations.append({"data_type": "vector_store", "resource_id": collection_id})
        invalidations.append({"data_type": "semantic_index", "resource_id": collection_id})
    
    # Usar la función de invalidación coordinada existente
    return await invalidate_coordinated(
        tenant_id=tenant_id,
        primary_data_type="document",
        primary_resource_id=document_id,
        related_invalidations=invalidations,
        collection_id=collection_id
    )

async def invalidate_chunk_cache(
    tenant_id: str,
    chunk_id: str,
    collection_id: Optional[str] = None,
    document_id: Optional[str] = None,
    model_name: Optional[str] = None,
    ctx: Optional[Context] = None
) -> Dict[str, int]:
    """
    Invalida selectivamente la caché relacionada con un chunk específico.
    
    Esta función permite invalidar la caché de embeddings y resultados de consultas 
    relacionados con un chunk específico, sin afectar al resto de chunks del mismo documento.
    
    Args:
        tenant_id: ID del tenant
        chunk_id: ID del chunk específico a invalidar
        collection_id: ID de la colección (opcional)
        document_id: ID del documento al que pertenece el chunk (opcional)
        model_name: Nombre del modelo de embedding (opcional, se usará para invalidación más precisa)
        ctx: Contexto de la solicitud
        
    Returns:
        Dict con contador de claves invalidadas por tipo
    """
    logger = logging.getLogger("common.cache")
    
    # Usar contenido de context si está disponible
    if ctx:
        if not tenant_id and hasattr(ctx, 'tenant_id'):
            tenant_id = ctx.tenant_id
        if not collection_id and hasattr(ctx, 'collection_id'):
            collection_id = ctx.collection_id
    
    # Generar patrones de claves para invalidación precisa
    # Si se proporciona el modelo, invalidar solo ese modelo específico para el chunk
    if model_name:
        embedding_pattern = f"{model_name}:{chunk_id}:*"
    else:
        embedding_pattern = f"*:{chunk_id}:*"  # Todos los modelos para ese chunk
    
    # Configurar tipos de datos a invalidar
    invalidations = [
        {
            "data_type": "embeddings",
            "resource_id": embedding_pattern,
            "collection_id": collection_id
        }
    ]
    
    # Si conocemos el document_id, invalidar también los resultados de consulta que podrían contener este chunk
    if document_id:
        invalidations.append({
            "data_type": "query_result",
            "resource_id": f"*{document_id}*{chunk_id}*",  # Invalidar consultas que podrían haber recuperado este chunk
            "collection_id": collection_id
        })
    
    # Registrar métricas de invalidación específicas por chunk
    try:
        from common.tracking import track_operation
        await track_operation(
            tenant_id=tenant_id,
            operation="chunk_cache_invalidation",
            metadata={
                "chunk_id": chunk_id,
                "document_id": document_id,
                "collection_id": collection_id,
                "model_name": model_name
            }
        )
    except Exception as e:
        logger.warning(f"Error al registrar métricas de invalidación de chunk: {str(e)}")
    
    # Ejecutar invalidación coordinada
    return await invalidate_coordinated(
        tenant_id=tenant_id,
        primary_data_type="chunk",
        primary_resource_id=chunk_id,
        collection_id=collection_id,
        related_invalidations=invalidations,
        ctx=ctx
    )

async def get_embeddings_batch_with_cache(
    texts: List[str],
    tenant_id: str,
    model_name: str,
    embedding_provider: Callable,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    ctx: Optional[Context] = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Implementación especializada del patrón Cache-Aside para lotes de embeddings.
    
    Esta función centraliza el procesamiento por lotes de embeddings, manteniendo
    la consistencia con el patrón Cache-Aside y asegurando métricas precisas
    para toda la operación batch.
    
    Args:
        texts: Lista de textos para generar embeddings
        tenant_id: ID del tenant
        model_name: Modelo de embedding a utilizar
        embedding_provider: Función que genera embeddings para los textos no encontrados en caché
                          (recibe una lista de textos y devuelve una lista de embeddings)
        agent_id: ID opcional del agente
        conversation_id: ID opcional de la conversación
        collection_id: ID opcional de la colección
        ctx: Contexto opcional de la operación
        
    Returns:
        Tuple[List[List[float]], Dict[str, Any]]:
            - Lista de embeddings (en el mismo orden que los textos)
            - Diccionario de métricas
    """
    start_time = time.time()
    
    # Métricas para seguimiento
    metrics = {
        "source": "mixed",  # Puede ser "cache", "generation" o "mixed"
        "data_type": "embedding_batch",
        "texts_count": len(texts),
        "cache_hits": 0,
        "cache_misses": 0
    }
    
    # Generar hashes para los textos
    import hashlib
    text_hashes = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
    cache_keys = [f"{model_name}:{text_hash}" for text_hash in text_hashes]
    
    # Intentar recuperar todos los embeddings de la caché
    embeddings_from_cache = {}
    
    for i, cache_key in enumerate(cache_keys):
        try:
            from common.cache.manager import CacheManager
            val = await CacheManager.get(
                data_type="embedding",
                resource_id=cache_key,
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                search_hierarchy=True
            )
            
            if val:
                embeddings_from_cache[i] = val
                metrics["cache_hits"] += 1
                
                # Registrar métrica de acierto
                await track_cache_metrics(
                    data_type="embedding",
                    tenant_id=tenant_id,
                    metric_type=METRIC_CACHE_HIT,
                    value=True,
                    agent_id=agent_id,
                    metadata={"model": model_name}
                )
        except Exception as e:
            logger.debug(f"Error al buscar embedding en caché: {str(e)}")
    
    # Todos los embeddings están en caché?
    if len(embeddings_from_cache) == len(texts):
        logger.info(f"Todos los embeddings ({len(texts)}) recuperados de caché")
        metrics["source"] = SOURCE_CACHE
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        
        # Ordenar embeddings según el orden original de textos
        result = [embeddings_from_cache[i] for i in range(len(texts))]
        return result, metrics
    
    # Identificar textos que necesitan procesamiento
    texts_to_process = []
    indices_to_process = []
    
    for i, text in enumerate(texts):
        if i not in embeddings_from_cache:
            texts_to_process.append(text)
            indices_to_process.append(i)
            metrics["cache_misses"] += 1
            
            # Registrar métrica de fallo
            await track_cache_metrics(
                data_type="embedding",
                tenant_id=tenant_id,
                metric_type=METRIC_CACHE_MISS,
                value=False,
                agent_id=agent_id,
                metadata={"model": model_name}
            )
    
    # Generar nuevos embeddings para los textos no encontrados en caché
    generation_start = time.time()
    
    try:
        # Llamar al proveedor de embeddings con los textos que faltan
        new_embeddings = await embedding_provider(texts_to_process)
        
        if len(new_embeddings) != len(texts_to_process):
            raise ValueError(f"Discrepancia en embeddings generados: {len(new_embeddings)} vs {len(texts_to_process)} esperados")
            
        # Almacenar nuevos embeddings en caché con el TTL adecuado
        for idx, (i, embedding) in enumerate(zip(indices_to_process, new_embeddings)):
            # Serializar embedding si es necesario
            serialized_embedding = serialize_for_cache(embedding, "embedding")
            
            # Guardar en caché
            cache_key = cache_keys[i]
            from common.cache.manager import CacheManager
            await CacheManager.set(
                data_type="embedding",
                resource_id=cache_key,
                value=serialized_embedding,
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                ttl=get_default_ttl_for_data_type("embedding")  # Usar TTL estándar para embeddings
            )
            
            # Registrar métricas de tamaño
            emb_size = estimate_object_size(serialized_embedding)
            await track_cache_metrics(
                data_type="embedding",
                tenant_id=tenant_id,
                metric_type=METRIC_CACHE_SIZE,
                value=emb_size,
                agent_id=agent_id,
                metadata={"model": model_name}
            )
            
        # Métricas de generación
        generation_time = time.time() - generation_start
        metrics["generation_time_ms"] = generation_time * 1000
        
    except Exception as e:
        logger.error(f"Error generando embeddings en lote: {str(e)}")
        # Si hay error, devolver los embeddings que sí tenemos de caché
        if not embeddings_from_cache:
            # Si no hay ninguno en caché, propagar el error
            raise
        
        # Marcar el error en métricas
        metrics["error"] = str(e)
        metrics["partial_results"] = True
        
        # Para los que no se pudieron generar, usar None
        new_embeddings = [None] * len(texts_to_process)
    
    # Combinar embeddings de caché y nuevos
    final_embeddings = [None] * len(texts)
    
    # Primero colocar los de caché
    for i, emb in embeddings_from_cache.items():
        final_embeddings[i] = deserialize_from_cache(emb, "embedding")
        
    # Luego colocar los nuevos
    for idx, i in enumerate(indices_to_process):
        if new_embeddings[idx] is not None:
            final_embeddings[i] = new_embeddings[idx]
    
    # Métricas finales
    metrics["total_time_ms"] = (time.time() - start_time) * 1000
    
    if metrics["cache_hits"] > 0 and metrics["cache_misses"] > 0:
        metrics["source"] = "mixed"
    elif metrics["cache_hits"] > 0:
        metrics["source"] = SOURCE_CACHE
    else:
        metrics["source"] = SOURCE_GENERATION
    
    logger.info(
        f"Batch de embeddings procesado: {len(texts)} textos, "
        f"{metrics['cache_hits']} de caché, {metrics['cache_misses']} generados, "
        f"tiempo total: {metrics['total_time_ms']:.2f}ms"
    )
    
    return final_embeddings, metrics

# Funciones auxiliares para métricas

async def track_chunk_cache_metrics(
    tenant_id: str,
    chunk_id: str,
    metric_type: str,
    collection_id: Optional[str] = None,
    document_id: Optional[str] = None,
    model_name: Optional[str] = None,
    value: Union[bool, float, int] = True,
    extra_metadata: Optional[Dict[str, Any]] = None
):
    """
    Función especializada para registrar métricas relacionadas con caché de chunks.
    
    Permite un seguimiento detallado del uso de caché a nivel de chunk individual,
    facilitando análisis de rendimiento y optimización de estrategias de caché.
    
    Args:
        tenant_id: ID del tenant
        chunk_id: ID del chunk específico
        metric_type: Tipo de métrica (METRIC_CHUNK_CACHE_HIT, METRIC_CHUNK_CACHE_MISS, etc.)
        collection_id: ID de la colección (opcional)
        document_id: ID del documento al que pertenece el chunk (opcional)
        model_name: Nombre del modelo de embedding utilizado (opcional)
        value: Valor de la métrica (booleano para hit/miss, número para latencia/tamaño)
        extra_metadata: Metadatos adicionales específicos de la operación
    """
    try:
        # Preparar metadatos básicos del chunk
        metadata = {
            "chunk_id": chunk_id,
            "collection_id": collection_id,
            "document_id": document_id,
            "model_name": model_name
        }
        
        # Añadir metadatos adicionales si se proporcionan
        if extra_metadata:
            metadata.update(extra_metadata)
        
        # Usar la función centralizada para registrar la métrica
        await track_cache_metrics(
            data_type="chunk",
            tenant_id=tenant_id,
            metric_type=metric_type,
            value=value,
            metadata=metadata
        )
    except Exception as e:
        logger = logging.getLogger("common.cache")
        logger.warning(f"Error al registrar métrica de caché de chunk: {str(e)}")

async def track_cache_metrics(
    data_type: str,
    tenant_id: str,
    metric_type: str,
    value: Union[bool, float, int],
    agent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Función centralizada para registrar todas las métricas relacionadas con caché.
    
    Unifica la lógica de seguimiento de métricas como hits, misses, latencia, tamaño,
    etc., en una sola función que maneja diferentes tipos de métricas.
    
    Args:
        data_type: Tipo de dato ("embedding", "vector_store", etc.)
        tenant_id: ID del tenant
        metric_type: Tipo de métrica (METRIC_CACHE_HIT, METRIC_LATENCY, etc.)
        value: Valor de la métrica (booleano para hit/miss, número para latencia/tamaño)
        agent_id: ID del agente opcional
        metadata: Metadatos adicionales
    """
    try:
        # Conversión de valor según tipo de métrica
        if metric_type in [METRIC_CACHE_HIT, METRIC_CACHE_MISS]:
            # Para hit/miss, el valor es un booleano, incrementar contador en 1
            amount = 1
            counter_type = METRIC_CACHE_HIT if value else METRIC_CACHE_MISS
        elif metric_type == METRIC_LATENCY:
            # Para latencia, el valor es un float (milisegundos)
            amount = int(value)  # Convertir a entero para contador
            counter_type = METRIC_LATENCY
            if not metadata:
                metadata = {}
            metadata["latency_ms"] = value
        elif metric_type == METRIC_CACHE_SIZE:
            # Para tamaño, el valor es un entero (bytes)
            amount = int(value)
            counter_type = METRIC_CACHE_SIZE
        else:
            # Para otros tipos de métricas
            amount = 1 if isinstance(value, bool) else int(value)
            counter_type = metric_type
        
        # Usar la función centralizada de incremento de contador
        from common.cache.manager import CacheManager
        await CacheManager.increment_counter(
            scope=counter_type,
            amount=amount,
            resource_id=data_type,
            tenant_id=tenant_id,
            agent_id=agent_id,
            metadata=metadata
        )
    except Exception as e:
        logger.debug(f"Error al registrar métrica de caché {metric_type}: {str(e)}")

# Mantener funciones antiguas para compatibilidad pero delegando a la función centralizada

async def track_cache_hit(data_type: str, tenant_id: str, hit: bool):
    """Registra un acierto o fallo de caché."""
    from common.cache.manager import CacheManager
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type="cache_hit" if hit else "cache_miss",
        value=hit
    )
    
async def track_cache_metric(data_type: str, tenant_id: str, source: str, latency_ms: float):
    """Registra la latencia de recuperación de datos."""
    from common.cache.manager import CacheManager
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type=f"latency_{source}",
        value=latency_ms
    )
    
async def track_cache_size(data_type: str, tenant_id: str, size_bytes: int):
    """Registra el tamaño de los datos almacenados en caché."""
    from common.cache.manager import CacheManager
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type="cache_size",
        value=size_bytes
    )

# Funciones de serialización/deserialización

def serialize_chunk_data(chunk_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializa los metadatos de un chunk para uso en API y caché.
    
    Esta función especializada garantiza que los atributos críticos de un chunk
    (como chunk_id, collection_id, document_id y modelo de embedding) sean
    serializados de manera consistente para todas las API y almacenamiento en caché.
    
    Args:
        chunk_data: Diccionario con datos del chunk
        
    Returns:
        Diccionario serializado con metadatos normalizados
    """
    # Crear copia para no modificar el original
    serialized = {}
    
    # Lista de campos críticos que siempre deben estar presentes
    critical_fields = ["chunk_id", "tenant_id", "collection_id", "document_id", "embedding_model"]
    
    # Procesar primero los campos críticos
    for field in critical_fields:
        if field in chunk_data:
            serialized[field] = chunk_data[field]
        elif field == "embedding_model" and "model" in chunk_data:
            # Compatibilidad con diferentes nombres de campo para modelo
            serialized[field] = chunk_data["model"]
        elif field == "chunk_id" and "id" in chunk_data:
            # Compatibilidad con diferentes nombres de campo para chunk_id
            serialized[field] = chunk_data["id"]
        else:
            # Campos críticos ausentes se establecen como None
            serialized[field] = None
    
    # Añadir timestamp si no existe
    if "embedding_timestamp" not in chunk_data:
        serialized["embedding_timestamp"] = int(time.time())
    else:
        serialized["embedding_timestamp"] = chunk_data["embedding_timestamp"]
    
    # Procesar el resto de campos
    for key, value in chunk_data.items():
        if key not in serialized:
            serialized[key] = serialize_for_cache(value, "chunk")
    
    return serialized

def deserialize_chunk_data(serialized_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deserializa los metadatos de un chunk desde API o caché.
    
    Función complementaria a serialize_chunk_data que garantiza que los
    datos de un chunk se deserialicen de manera consistente, manejando
    posibles cambios en la estructura o nombres de campos.
    
    Args:
        serialized_data: Diccionario serializado con datos del chunk
        
    Returns:
        Diccionario deserializado con metadatos normalizados
    """
    # Crear copia para no modificar el original
    deserialized = serialized_data.copy()
    
    # Asegurar consistencia en nombres de campos críticos
    if "id" not in deserialized and "chunk_id" in deserialized:
        deserialized["id"] = deserialized["chunk_id"]
    
    if "model" not in deserialized and "embedding_model" in deserialized:
        deserialized["model"] = deserialized["embedding_model"]
    
    # Deserializar campos complejos si es necesario
    if "embedding" in deserialized and isinstance(deserialized["embedding"], str):
        try:
            deserialized["embedding"] = json.loads(deserialized["embedding"])
        except:
            pass  # Mantener como está si no se puede deserializar
    
    return deserialized

def serialize_for_cache(value: Any, data_type: str) -> Any:
    """
    Serializa un valor para almacenar en caché según el tipo de datos.
    
    Implementa reglas específicas de serialización para cada tipo de dato
    del sistema RAG, garantizando que todos los servicios sigan el mismo
    patrón de serialización.
    
    Especialmente importante para:
    - Embeddings: Convierte cualquier formato (numpy, tensor) a listas Python
    - Vector stores: Maneja objetos complejos específicos del servicio
    - Resultados de consulta: Asegura serialización compatible con JSON
    - Chunks: Utiliza serialize_chunk_data para consistencia en metadatos
    
    Args:
        value: Valor a serializar
        data_type: Tipo de datos ("embedding", "vector_store", "chunk", etc.)
        
    Returns:
        Any: Valor serializado listo para almacenar en caché
    """
    if value is None:
        return None
        
    # Para chunks, usar la función especializada
    if data_type == "chunk" and isinstance(value, dict):
        return serialize_chunk_data(value)
    
    # Detectar arrays numpy o tensores y convertirlos a listas planas
    if data_type == "embedding":
        # Para numpy arrays
        if 'numpy' in str(type(value)) and hasattr(value, 'tolist'):
            return value.tolist()
        
        # Para tensores PyTorch o TensorFlow
        if 'torch' in str(type(value)) and hasattr(value, 'detach') and hasattr(value, 'cpu') and hasattr(value, 'numpy'):
            return value.detach().cpu().numpy().tolist()
        
        # Para tensores TensorFlow
        if 'tensorflow' in str(type(value)) and hasattr(value, 'numpy'):
            return value.numpy().tolist()
            
        # Para cualquier otro tipo array-like con método tolist
        if hasattr(value, 'tolist'):
            return value.tolist()
        
        # Si ya es una lista, asegurarse de que los valores son nativos de Python
        if isinstance(value, list):
            # Verificar si hay floats32 o tipos similares de numpy
            if value and hasattr(value[0], 'item') and callable(value[0].item):
                return [float(v.item()) if hasattr(v, 'item') else float(v) for v in value]
            return value
    
    # Para vector_store, se necesita manejar la serialización de objetos específicos
    elif data_type == "vector_store":
        # Muchos vector_stores no son serializables directamente
        # Se recomienda que los servicios específicos definan sus propios serializadores
        return value
    
    # Para resultados de consulta
    elif data_type == "query_result":
        # Asegurar que solo se guarden tipos serializables a JSON
        try:
            # Intentar serializar a JSON para verificar
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            # Intentar convertir a dict serializable
            if hasattr(value, "__dict__"):
                return value.__dict__
            # Para casos complejos, convertir a string
            return str(value)
    
    # Para otros tipos de datos, intentar serializar directamente
    try:
        # Probar si es serializable a JSON como está
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # Si falla, intentar conversiones comunes
        if hasattr(value, "to_dict"):
            return value.to_dict()
        elif hasattr(value, "__dict__"):
            return value.__dict__
        else:
            # Último recurso: convertir a string
            return str(value)
    

def deserialize_from_cache(value: Any, data_type: str) -> Any:
    """
    Deserializa un valor recuperado de caché según el tipo de datos.
    
    Implementa reglas específicas de deserialización para cada tipo de dato,
    complementando serialize_for_cache y garantizando compatibilidad entre servicios.
    
    Args:
        value: Valor serializado a deserializar
        data_type: Tipo de datos ("embedding", "vector_store", "chunk", etc.)
        
    Returns:
        Any: Valor deserializado listo para usar
    """
    if value is None:
        return None
    
    # La mayoría de los valores se pueden usar directamente
    if data_type == "chunk":
        return deserialize_chunk_data(value)
    
    elif data_type == "embedding":
        # Los embeddings siempre se almacenan como listas planas
        # Aquí dejamos que el servicio decida si necesita convertirlos a otro formato
        return value
    
    elif data_type == "vector_store":
        # Para vector_stores, verificar si necesita procesamiento específico
        # Por ahora, devolver tal cual, pero los servicios pueden proporcionar 
        # sus propios deserializadores si es necesario
        return value
    
    elif data_type == "query_result":
        # Para resultados de consulta, asegurarse de que las estructuras estén correctas
        # Si es un diccionario serializado desde un objeto, mantenerlo como dict
        return value
    
    # Para otros tipos, retornar tal cual
    return value

# Funciones utilitarias

def estimate_object_size(obj: Any) -> int:
    """
    Estima el tamaño en bytes de un objeto para métricas.
    
    Args:
        obj: Objeto a medir
        
    Returns:
        int: Tamaño estimado en bytes
    """
    # Constantes para tamaños predeterminados
    DEFAULT_SIZE = 1000  # Tamaño predeterminado para objetos complejos
    MIN_SIZE = 500       # Tamaño mínimo si hay error
    
    # Si el objeto es None, retornar tamaño mínimo
    if obj is None:
        return 0
    
    try:
        # Para objetos simples
        if isinstance(obj, (int, float, bool, str)):
            return sys.getsizeof(obj)
        
        # Para objetos con método de tamaño propio
        if hasattr(obj, '__sizeof__'):
            return obj.__sizeof__()
        
        # Para objetos tipo numpy array o tensor
        if 'numpy' in str(type(obj)) and hasattr(obj, 'nbytes'):
            return getattr(obj, 'nbytes')
            
        # Para objetos serializables a JSON
        try:
            json_str = json.dumps(obj)
            return sys.getsizeof(json_str)
        except (TypeError, ValueError, OverflowError):
            # Objeto no es JSON serializable
            pass
            
        # Para objetos con __dict__
        if hasattr(obj, '__dict__'):
            # Estimamos basado en el tamaño del diccionario de atributos
            return estimate_object_size(obj.__dict__)
        
        # Si llegamos aquí, usar valor predeterminado
        logger.debug(f"Usando tamaño predeterminado para objeto tipo {type(obj)}")
        return DEFAULT_SIZE
        
    except Exception as e:
        logger.warning(f"Error estimando tamaño de objeto tipo {type(obj)}: {str(e)}")
        return MIN_SIZE

def get_default_ttl_for_data_type(data_type: str) -> int:
    """
    Obtiene el TTL predeterminado para un tipo de datos específico.
    
    Centraliza la lógica de asignación de TTL para evitar inconsistencias
    entre diferentes partes del sistema RAG.
    
    Args:
        data_type: Tipo de datos para el que se desea obtener el TTL
        
    Returns:
        int: Valor TTL en segundos para el tipo de datos especificado
    """
    from common.cache import DEFAULT_TTL_MAPPING, TTL_STANDARD
    
    # Si el tipo existe en el mapeo, usar ese valor
    if data_type in DEFAULT_TTL_MAPPING:
        return DEFAULT_TTL_MAPPING[data_type]
    
    # Caso contrario, usar el valor estándar por defecto
    return TTL_STANDARD

def generate_resource_id_hash(data: Any) -> str:
    """
    Genera un hash consistente para usar como resource_id.
    
    Esta función puede aceptar cualquier tipo de dato, no solo strings.
    Para datos que no son strings, los convierte a su representación
    JSON antes de generar el hash.
    
    Args:
        data: Dato a hashear (string, dict, list, etc.)
        
    Returns:
        str: Hash SHA-256 hexadecimal
    """
    if isinstance(data, str):
        text = data
    else:
        try:
            # Intentar convertir a JSON para objetos no string
            text = json.dumps(data, sort_keys=True)
        except (TypeError, ValueError):
            # Si no es serializable a JSON, usar repr
            text = repr(data)
    
    return hashlib.sha256(text.encode()).hexdigest()
