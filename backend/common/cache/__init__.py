"""
Módulo para cache-aside y gestión de caché en el sistema RAG.

Proporciona mecanismos de caché multinivel (memoria y Redis) con contexto
siguiendo el patrón Cache-Aside para todos los servicios RAG.
"""

from common.config import get_settings

# Función para obtener configuraciones de caché del sistema centralizado
def _get_cache_settings():
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

# Constantes para fuentes de datos (para métricas)
SOURCE_CACHE = "cache"
SOURCE_SUPABASE = "supabase"
SOURCE_GENERATION = "generation"

# Constantes para tipos de métricas
METRIC_CACHE_HIT = "cache_hit"
METRIC_CACHE_MISS = "cache_miss"
METRIC_LATENCY = "latency"
METRIC_CACHE_SIZE = "cache_size"
METRIC_CACHE_INVALIDATION = "cache_invalidation"
METRIC_CACHE_INVALIDATION_COORDINATED = "cache_invalidation_coordinated"
METRIC_SERIALIZATION_ERROR = "serialization_error"
METRIC_DESERIALIZATION_ERROR = "deserialization_error"

# Constantes para TTL (tiempos de vida)
# Obtenemos valores iniciales desde configuración centralizada
cache_settings = _get_cache_settings()
TTL_SHORT = cache_settings["ttl_short"]       # 5 minutos por defecto (configuraciones, datos volátiles)
TTL_STANDARD = cache_settings["ttl_standard"] # 1 hora por defecto (resultados de consulta, datos moderadamente estables)
TTL_EXTENDED = cache_settings["ttl_extended"] # 24 horas por defecto (embeddings, datos altamente estables)
TTL_PERMANENT = cache_settings["ttl_permanent"] # Sin expiración (datos persistentes)

# Mapeo de tipos de datos a TTL predeterminados
DEFAULT_TTL_MAPPING = {
    "embedding": TTL_EXTENDED,           # Embeddings (estables)
    "vector_store": TTL_STANDARD,        # Vector stores (moderadamente estables)
    "query_result": TTL_SHORT,           # Resultados de consulta (volátiles)
    "agent_config": TTL_STANDARD,        # Configuraciones de agentes (moderadamente estables)
    "agent_response": TTL_SHORT,         # Respuestas de agentes (volátiles)
    "conversation": TTL_STANDARD,        # Conversaciones (moderadamente estables)
    "conversation_messages": TTL_STANDARD, # Mensajes de conversación
    "document": TTL_STANDARD,            # Documentos (moderadamente estables)
    "document_metadata": TTL_EXTENDED,   # Metadatos de documentos (estables)
    "collection_metadata": TTL_EXTENDED, # Metadatos de colecciones (estables)
    "settings": TTL_SHORT,               # Configuraciones (volátiles)
    "token_usage": TTL_EXTENDED,         # Uso de tokens (estadísticas)
    "counter": TTL_EXTENDED,             # Contadores (estadísticas)
    "retrieval_cache": TTL_SHORT,        # Resultados de recuperación (volátiles)
    "embedding_batch": TTL_EXTENDED,     # Lotes de embeddings (estables)
    "semantic_index": TTL_STANDARD,      # Índices semánticos (moderadamente estables)
    "default": TTL_STANDARD              # Valor predeterminado
}

from .manager import CacheManager
from .helpers import (
    get_with_cache_aside,
    serialize_for_cache,
    deserialize_from_cache,
    track_cache_metrics,
    invalidate_coordinated,
    invalidate_resource_cache,
    invalidate_document_update,
    generate_resource_id_hash,
    get_embeddings_batch_with_cache,
    estimate_object_size,
    get_default_ttl_for_data_type
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
    
    # Funciones de métricas y utilidades
    "track_cache_metrics",
    "generate_resource_id_hash",
    "estimate_object_size",
    "get_default_ttl_for_data_type",
    
    # Constantes de fuentes
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
    "TTL_SHORT",
    "TTL_STANDARD",
    "TTL_EXTENDED",
    "TTL_PERMANENT",
    "DEFAULT_TTL_MAPPING"
]