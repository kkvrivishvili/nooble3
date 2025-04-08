# 4. Actualizando common/cache/init.py para exportar las nuevas funciones

from .redis import (
    get_redis_client, cache_get, cache_set, cache_delete, cache_delete_pattern,
    generate_hash
)

from .contextual import (
    build_cache_key, get_cached_value_multi_level, cache_value_multi_level,
    invalidate_cache_hierarchy, _memory_cache, _memory_expiry
)

from .specialized import (
    EmbeddingCache, QueryResultCache, ConversationCache, AgentCache
)

from .conversation import (
    cache_conversation, get_cached_conversation, cache_message, get_cached_messages
)

from .counters import (
    increment_token_counter, get_token_count, get_agent_usage_stats,
    invalidate_tenant_cache, invalidate_agent_cache, invalidate_conversation_cache,
    invalidate_collection_cache
)

__all__ = [
    # Redis básico
    'get_redis_client', 'cache_get', 'cache_set', 'cache_delete', 'cache_delete_pattern',
    'generate_hash',
    
    # Sistema contextual
    'build_cache_key', 'get_cached_value_multi_level', 'cache_value_multi_level',
    'invalidate_cache_hierarchy',
    
    # Caché especializada
    'EmbeddingCache', 'QueryResultCache', 'ConversationCache', 'AgentCache',
    
    # Sistema de conversaciones
    'cache_conversation', 'get_cached_conversation', 'cache_message', 'get_cached_messages',
    
    # Contadores y estadísticas
    'increment_token_counter', 'get_token_count', 'get_agent_usage_stats',
    'invalidate_tenant_cache', 'invalidate_agent_cache', 'invalidate_conversation_cache',
    'invalidate_collection_cache'
]