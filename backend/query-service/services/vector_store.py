# Actualización de query-service/services/vector_store.py

import logging
import time
import sys
import json
from typing import Optional, Any

from common.db.tables import get_table_name
from common.db.supabase import get_supabase_client, get_tenant_vector_store
from common.cache import CacheManager
from common.context import with_context, Context
from common.errors import handle_errors, CollectionNotFoundError

logger = logging.getLogger(__name__)

@with_context(tenant=True, collection=True)
@handle_errors(error_type="simple", log_traceback=False)
async def get_vector_store_for_collection(tenant_id: str, collection_id: str, ctx: Context = None) -> Optional[Any]:
    """
    Obtiene un vector store para una colección específica siguiendo el patrón Cache-Aside optimizado.
    
    1. Verificar caché primero
    2. Si no está en caché, obtener de Supabase
    3. Almacenar en caché para futuras consultas
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        Vector store para la colección o None si no se encuentra
    """
    # Métricas para seguimiento de rendimiento
    start_time = time.time()
    metrics = {
        "source": None,
        "collection_id": collection_id
    }
    
    # 1. VERIFICAR CACHÉ - Paso 1 del patrón Cache-Aside
    cache_check_start = time.time()
    
    # Buscar en caché unificada
    vector_store = await CacheManager.get(
        data_type="vector_store",
        resource_id=collection_id,
        tenant_id=tenant_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        search_hierarchy=True
    )
    
    cache_check_time = time.time() - cache_check_start
    
    if vector_store:
        logger.debug(f"Vector store para colección {collection_id} obtenido de caché")
        
        # Registrar acierto y latencia de caché
        await track_cache_hit("vector_store", tenant_id, True)
        await track_cache_metric(
            data_type="vector_store",
            tenant_id=tenant_id,
            source="cache",
            latency_ms=cache_check_time * 1000
        )
        
        metrics["source"] = "cache"
        metrics["latency_ms"] = cache_check_time * 1000
        return vector_store
    
    # Registrar fallo de caché
    await track_cache_hit("vector_store", tenant_id, False)
    
    # 2. OBTENER DE SUPABASE - Paso 2 del patrón Cache-Aside
    db_start_time = time.time()
    
    try:
        # Obtener cliente y tabla
        supabase = get_supabase_client()
        
        # Obtener vector store de Supabase
        vector_store = await get_tenant_vector_store(
            tenant_id=tenant_id,
            collection_id=collection_id,
            ctx=ctx
        )
        
        db_time = time.time() - db_start_time
        
        # Registrar latencia de Supabase
        await track_cache_metric(
            data_type="vector_store",
            tenant_id=tenant_id,
            source="supabase",
            latency_ms=db_time * 1000
        )
        
        if vector_store:
            # 3. ALMACENAR EN CACHÉ - Paso 3 del patrón Cache-Aside
            try:
                # Estimar tamaño para métricas (aproximado)
                try:
                    size_estimate = sys.getsizeof(json.dumps(str(vector_store)))
                except:
                    size_estimate = 5000  # Valor estimado por defecto
                
                # Cachear para futuras solicitudes usando TTL estandarizado
                await CacheManager.set(
                    data_type="vector_store",
                    resource_id=collection_id,
                    value=vector_store,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    ttl=CacheManager.ttl_standard  # 1 hora
                )
                
                # Registrar tamaño en caché
                await track_cache_size("vector_store", tenant_id, size_estimate)
                
                logger.debug(f"Vector store para colección {collection_id} almacenado en caché")
            except Exception as cache_err:
                logger.warning(f"Error al almacenar vector store en caché: {str(cache_err)}")
            
            metrics["source"] = "supabase"
            metrics["latency_ms"] = db_time * 1000
            return vector_store
        else:
            logger.warning(f"No se encontró vector store para colección {collection_id}")
            metrics["source"] = "not_found"
            return None
            
    except Exception as e:
        logger.error(f"Error obteniendo vector store: {str(e)}")
        metrics["source"] = "error"
        metrics["error"] = str(e)
        return None
    finally:
        # Registrar tiempo total
        metrics["total_time_ms"] = (time.time() - start_time) * 1000
        logger.debug(f"Métricas de vector_store: {json.dumps(metrics)}")

@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def invalidate_vector_store_cache(tenant_id: str, collection_id: str, ctx: Context = None) -> bool:
    """
    Invalida la caché del vector store para una colección.
    
    Esta función debe llamarse cuando se modifican documentos en una colección.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        bool: True si se invalidó correctamente
    """
    try:
        # Invalidar caché relacionada con esta colección usando CacheManager
        # Incluye invalidación coordinada de vector store y cualquier consulta relacionada
        invalidated_keys = 0
        
        # 1. Invalidar vector store
        deleted = await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="vector_store",
            resource_id=collection_id
        )
        invalidated_keys += deleted
        
        # 2. Invalidar consultas relacionadas a esta colección
        deleted_queries = await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="query_result",
            collection_id=collection_id
        )
        invalidated_keys += deleted_queries
        
        logger.info(f"Caché invalidada para colección {collection_id}: {invalidated_keys} claves eliminadas")
        return True
    except Exception as e:
        logger.error(f"Error al invalidar caché para colección {collection_id}: {str(e)}")
        return False

# Funciones auxiliares para métricas - Consistentes con el patrón de métricas

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