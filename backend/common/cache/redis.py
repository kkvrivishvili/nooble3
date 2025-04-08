# 1. Mejora de common/cache/redis.py - BASE DEL SISTEMA

import logging
import time
import json
import hashlib
from typing import Any, Optional, Dict, List

logger = logging.getLogger(__name__)

# Variable global para cliente Redis
_redis_client = None

async def get_redis_client():
    """Obtiene un cliente Redis compartido"""
    global _redis_client
    
    if _redis_client is None:
        from ..config.settings import get_settings
        import redis.asyncio as redis
        
        settings = get_settings()
        try:
            pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections if hasattr(settings, 'redis_max_connections') else 10,
                decode_responses=True
            )
            client = redis.Redis(connection_pool=pool)
            await client.ping()
            logger.info("Redis connected successfully")
            _redis_client = client
        except Exception as e:
            logger.warning(f"Redis connection failed: {str(e)}. Running without cache.")
            return None
    
    return _redis_client

async def cache_get(key: str) -> Optional[Any]:
    """Obtiene un valor de la caché"""
    redis_client = await get_redis_client()
    if not redis_client:
        return None
    
    try:
        cached_value = await redis_client.get(key)
        if cached_value:
            try:
                return json.loads(cached_value)
            except json.JSONDecodeError:
                return cached_value
        return None
    except Exception as e:
        logger.warning(f"Error getting value from cache: {str(e)}")
        return None

async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Almacena un valor en la caché"""
    redis_client = await get_redis_client()
    if not redis_client:
        return False
    
    try:
        # Serializar a JSON si es necesario
        if not isinstance(value, str):
            serialized = json.dumps(value)
        else:
            serialized = value
            
        if ttl is not None and ttl > 0:
            await redis_client.setex(key, ttl, serialized)
        else:
            await redis_client.set(key, serialized)
        return True
    except Exception as e:
        logger.warning(f"Error setting value in cache: {str(e)}")
        return False

async def cache_delete(key: str) -> bool:
    """Elimina un valor de la caché"""
    redis_client = await get_redis_client()
    if not redis_client:
        return False
    
    try:
        return await redis_client.delete(key) > 0
    except Exception as e:
        logger.warning(f"Error deleting value from cache: {str(e)}")
        return False

async def cache_delete_pattern(pattern: str) -> int:
    """Elimina valores que coinciden con un patrón"""
    redis_client = await get_redis_client()
    if not redis_client:
        return 0
    
    try:
        cursor = b"0"
        deleted_count = 0
        
        while cursor:
            cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            
            if keys:
                deleted_count += await redis_client.delete(*keys)
                
            if cursor == b"0":
                break
                
        return deleted_count
    except Exception as e:
        logger.warning(f"Error deleting pattern from cache: {str(e)}")
        return 0

def generate_hash(data: Any) -> str:
    """Genera un hash para cualquier tipo de datos"""
    if isinstance(data, str):
        return hashlib.md5(data.encode()).hexdigest()
    else:
        return hashlib.md5(json.dumps(data).encode()).hexdigest()