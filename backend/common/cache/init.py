# common/cache/init.py

from .redis import get_redis_client, generate_hash
from .manager import CacheManager

__all__ = [
    'CacheManager',
    'get_redis_client',
    'generate_hash',
]