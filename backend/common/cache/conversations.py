"""
Funciones específicas para cacheo de conversaciones y mensajes.
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from .redis import get_redis_client, cache_get, cache_set

logger = logging.getLogger(__name__)

async def cache_conversation(
    conversation_id: str,
    agent_id: str,
    owner_tenant_id: str,
    title: str = "Nueva conversación",
    is_public: bool = False,
    session_id: Optional[str] = None,
    ttl: int = 86400  # 24 horas por defecto
) -> bool:
    """
    Cachea una conversación en Redis.
    
    Args:
        conversation_id: ID de la conversación
        agent_id: ID del agente
        owner_tenant_id: ID del tenant propietario
        title: Título de la conversación
        is_public: Si es una conversación pública
        session_id: ID de sesión (para conversaciones públicas)
        ttl: Tiempo de vida en segundos
        
    Returns:
        bool: True si se cacheó correctamente, False en caso contrario
    """
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.warning("Failed to cache conversation: Redis client not available")
            return False
        
        # Datos a cachear
        conversation_data = {
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "owner_tenant_id": owner_tenant_id,
            "title": title,
            "is_public": is_public,
            "created_at": time.time()
        }
        
        if session_id:
            conversation_data["session_id"] = session_id
        
        # Cachear la conversación
        key = f"conv:{conversation_id}"
        await cache_set(key, conversation_data, ttl)
        
        # Si hay session_id, añadir a la lista de conversaciones de la sesión
        if session_id:
            session_key = f"session:{session_id}:conversations"
            pipeline = redis_client.pipeline()
            await pipeline.sadd(session_key, conversation_id)
            await pipeline.expire(session_key, ttl)
            await pipeline.execute()
            
        logger.debug(f"Conversation {conversation_id} cached successfully")
        return True
    except Exception as e:
        logger.error(f"Error caching conversation in Redis: {str(e)}")
        return False

async def get_cached_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene una conversación cacheada en Redis.
    
    Args:
        conversation_id: ID de la conversación
        
    Returns:
        Optional[Dict[str, Any]]: Datos de la conversación o None si no existe
    """
    key = f"conv:{conversation_id}"
    return await cache_get(key)

async def cache_message(
    conversation_id: str,
    message_id: str,
    role: str,
    content: str,
    token_count: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
    ttl: int = 86400  # 24 horas por defecto
) -> bool:
    """
    Cachea un mensaje en Redis.
    
    Args:
        conversation_id: ID de la conversación
        message_id: ID del mensaje
        role: Rol ('user', 'assistant', 'system')
        content: Contenido del mensaje
        token_count: Contador de tokens (para mensajes del asistente)
        metadata: Metadatos adicionales
        ttl: Tiempo de vida en segundos
        
    Returns:
        bool: True si se cacheó correctamente, False en caso contrario
    """
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.warning("Failed to cache message: Redis client not available")
            return False
        
        # Datos a cachear
        message_data = {
            "message_id": message_id,
            "role": role,
            "content": content,
            "timestamp": time.time()
        }
        
        if token_count > 0:
            message_data["token_count"] = token_count
        
        if metadata:
            message_data["metadata"] = metadata
        
        # Convertir a JSON
        message_json = json.dumps(message_data)
        
        # Añadir a la lista de mensajes
        messages_key = f"conv:{conversation_id}:messages"
        
        pipeline = redis_client.pipeline()
        await pipeline.rpush(messages_key, message_json)
        await pipeline.expire(messages_key, ttl)
        
        # Incrementar contador de mensajes en la conversación
        conversation_key = f"conv:{conversation_id}"
        await pipeline.hincrby(conversation_key, "message_count", 1)
        
        await pipeline.execute()
        
        logger.debug(f"Message {message_id} cached successfully for conversation {conversation_id}")
        return True
    except Exception as e:
        logger.error(f"Error caching message in Redis: {str(e)}")
        return False

async def get_cached_messages(
    conversation_id: str,
    start: int = 0,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Obtiene mensajes cacheados en Redis para una conversación.
    
    Args:
        conversation_id: ID de la conversación
        start: Índice inicial (0 = más antiguo)
        limit: Máximo número de mensajes a obtener
        
    Returns:
        List[Dict[str, Any]]: Lista de mensajes
    """
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            return []
        
        messages_key = f"conv:{conversation_id}:messages"
        end = start + limit - 1
        
        # Obtener mensajes de la lista
        cached_messages = await redis_client.lrange(messages_key, start, end)
        
        if not cached_messages:
            return []
        
        # Convertir de JSON a objetos
        messages = []
        for msg_json in cached_messages:
            try:
                messages.append(json.loads(msg_json))
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in cached message: {msg_json}")
        
        return messages
    except Exception as e:
        logger.error(f"Error getting cached messages from Redis: {str(e)}")
        return []