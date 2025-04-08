# common/cache/init.py

from .redis import get_redis_client, generate_hash
from .manager import CacheManager

# Para seguimiento de uso y estadísticas
from .counters import (
    increment_token_counter, get_token_count, get_agent_usage_stats,
    invalidate_tenant_cache, invalidate_agent_cache, invalidate_conversation_cache,
    invalidate_collection_cache
)

__all__ = [
    # Sistema unificado de caché
    'CacheManager',
    
    # Utilidades de Redis
    'get_redis_client', 'generate_hash',
    
    # Contadores y estadísticas (mantenemos estos por separado)
    'increment_token_counter', 'get_token_count', 'get_agent_usage_stats',
    'invalidate_tenant_cache', 'invalidate_agent_cache', 'invalidate_conversation_cache',
    'invalidate_collection_cache'
]