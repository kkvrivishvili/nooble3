# common/cache/init.py

from .manager import (
    CacheManager, 
    generate_hash, 
    get_redis_client, 
    TTL_SHORT, 
    TTL_MEDIUM, 
    TTL_LONG, 
    TTL_PERMANENT
)

__all__ = [
    'CacheManager',
    'generate_hash',
    'get_redis_client',
    'TTL_SHORT',
    'TTL_MEDIUM',
    'TTL_LONG',
    'TTL_PERMANENT',
]