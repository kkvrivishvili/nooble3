"""
Módulo para cache-aside y gestión de caché en el sistema RAG.

Proporciona mecanismos de caché multinivel (memoria y Redis) con contexto
siguiendo el patrón Cache-Aside para todos los servicios RAG.
"""

import asyncio
# Importamos constantes del módulo core en lugar de config
# para evitar dependencias circulares
from ..core.constants import (
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT,
    SOURCE_CACHE, SOURCE_SUPABASE, SOURCE_GENERATION,
    METRIC_CACHE_HIT, METRIC_CACHE_MISS, METRIC_LATENCY, METRIC_CACHE_SIZE,
    METRIC_CACHE_INVALIDATION, METRIC_CACHE_INVALIDATION_COORDINATED,
    METRIC_SERIALIZATION_ERROR, METRIC_DESERIALIZATION_ERROR,
    DEFAULT_TTL_MAPPING
)

# Mantenemos la importación de config, pero solo para la función get_settings
# que usaremos con importación tardía donde sea necesario
from ..config import get_settings

# Función para obtener configuraciones de caché del sistema centralizado
async def _get_cache_settings():
    """Obtiene configuraciones de caché desde el sistema centralizado."""
    settings = get_settings()
    return {
        "ttl_extended": settings.cache_ttl_extended,       # 24 horas
        "ttl_standard": settings.cache_ttl_standard,       # 1 hora
        "ttl_short": settings.cache_ttl_short,             # 5 minutos
        "ttl_permanent": settings.cache_ttl_permanent,     # Sin expiración
        "use_memory_cache": settings.use_memory_cache,
        "redis_url": settings.redis_url,
        "redis_max_connections": settings.redis_max_connections
    }

# Inicializar de forma asíncrona los valores de configuración
# Ejecutaremos esto más tarde cuando se importe el módulo en un contexto async
def initialize_cache_settings():
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Si el bucle ya está en ejecución, creamos una tarea futura
        asyncio.create_task(_initialize_cache_settings_async())
    else:
        # Si no hay bucle en ejecución, usamos los valores por defecto
        pass

async def _initialize_cache_settings_async():
    global TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT
    try:
        cache_settings = await _get_cache_settings()
        TTL_SHORT = cache_settings["ttl_short"]
        TTL_STANDARD = cache_settings["ttl_standard"]
        TTL_EXTENDED = cache_settings["ttl_extended"]
        TTL_PERMANENT = cache_settings["ttl_permanent"]
    except Exception as e:
        print(f"Error initializing cache settings: {e}")
        # Mantener los valores por defecto en caso de error

from .manager import CacheManager, get_redis_client
from .helpers import (
    deserialize_chunk_data,
    deserialize_from_cache,
    estimate_object_size,
    generate_resource_id_hash,
    get_default_ttl_for_data_type,
    get_embeddings_batch_with_cache,
    get_with_cache_aside,
    invalidate_chunk_cache,
    invalidate_coordinated,
    invalidate_document_update,
    invalidate_resource_cache,
    serialize_chunk_data,
    serialize_for_cache,
    standardize_llama_metadata,
    track_cache_metrics,
    track_chunk_cache_metrics
)

__all__ = [
    # Clases principales
    "CacheManager",
    
    # Funciones principales del patrón Cache-Aside
    "get_with_cache_aside",
    "get_embeddings_batch_with_cache",
    "serialize_for_cache",
    "deserialize_from_cache",
    "invalidate_resource_cache",
    "invalidate_coordinated",
    "invalidate_document_update",
    "invalidate_chunk_cache",
    
    # Funciones especializadas para chunks
    "serialize_chunk_data",
    "deserialize_chunk_data",
    "track_chunk_cache_metrics",
    "standardize_llama_metadata",
    
    # Funciones de métricas y utilidades
    "track_cache_metrics",
    "generate_resource_id_hash",
    "get_redis_client",
    "estimate_object_size",
    "get_default_ttl_for_data_type",
    
    # Constantes de TTL
    "TTL_SHORT",
    "TTL_STANDARD",
    "TTL_EXTENDED",
    "TTL_PERMANENT",
    "DEFAULT_TTL_MAPPING",
    
    # Constantes de fuentes de datos
    "SOURCE_CACHE",
    "SOURCE_SUPABASE",
    "SOURCE_GENERATION",
    
    # Constantes de métricas
    "METRIC_CACHE_HIT",
    "METRIC_CACHE_MISS",
    "METRIC_LATENCY",
    "METRIC_CACHE_SIZE",
    "METRIC_CACHE_INVALIDATION",
    "METRIC_CACHE_INVALIDATION_COORDINATED",
    "METRIC_SERIALIZATION_ERROR",
    "METRIC_DESERIALIZATION_ERROR",
    
    # Constantes de TTL
    "DEFAULT_TTL_MAPPING"
]