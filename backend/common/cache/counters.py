"""
Contadores y estadísticas en caché para tracking de uso.
"""

import logging
import time
from typing import Dict, Any, Optional

from .redis import get_redis_client, cache_delete_pattern

logger = logging.getLogger(__name__)

async def increment_token_counter(
    tenant_id: str,
    tokens: int,
    token_type: str = "llm",
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """
    Incrementa un contador de tokens en Redis.
    
    Args:
        tenant_id: ID del tenant
        tokens: Número de tokens a incrementar
        token_type: Tipo de token ('llm' o 'embedding')
        agent_id: ID del agente (opcional)
        conversation_id: ID de la conversación (opcional)
        
    Returns:
        bool: True si se incrementó correctamente, False en caso contrario
    """
    if not tenant_id or tokens <= 0:
        return False
        
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            return False
        
        # Clave según tipo de token
        if token_type == "embedding":
            counter_key = f"tenant:{tenant_id}:embedding_token_count"
        else:
            counter_key = f"tenant:{tenant_id}:token_count"
        
        pipeline = redis_client.pipeline()
        
        # Incrementar contador del tenant
        await pipeline.incrby(counter_key, tokens)
        
        # Si tenemos agent_id, actualizar sus estadísticas
        if agent_id:
            date_key = time.strftime("%Y-%m-%d")
            agent_key = f"agent:{agent_id}:usage:{date_key}"
            
            # Campo según tipo de token
            token_field = "embedding_tokens" if token_type == "embedding" else "tokens"
            
            # Incrementar contador de tokens del agente
            await pipeline.hincrby(agent_key, token_field, tokens)
            
            # TTL de 48 horas (2 días) para estadísticas diarias
            await pipeline.expire(agent_key, 172800)
            
            # Si hay conversation_id, también contar conversación y mensaje
            if conversation_id:
                # Incrementar contador de mensajes
                await pipeline.hincrby(agent_key, "messages", 1)
                
                # Verificar si ya contamos esta conversación hoy
                conv_set_key = f"{agent_key}:conversations"
                is_new = await redis_client.sadd(conv_set_key, conversation_id)
                
                if is_new:
                    # Es una conversación nueva para hoy, incrementar contador
                    await pipeline.hincrby(agent_key, "conversations", 1)
                    # TTL de 48 horas para este set
                    await pipeline.expire(conv_set_key, 172800)
        
        await pipeline.execute()
        return True
    except Exception as e:
        logger.error(f"Error incrementing token counter in Redis: {str(e)}")
        return False

async def get_token_count(tenant_id: str, token_type: str = "llm") -> int:
    """
    Obtiene el contador de tokens de un tenant desde Redis.
    
    Args:
        tenant_id: ID del tenant
        token_type: Tipo de token ('llm' o 'embedding')
        
    Returns:
        int: Número de tokens o 0 si no existe
    """
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            return 0
        
        # Clave según tipo de token
        if token_type == "embedding":
            counter_key = f"tenant:{tenant_id}:embedding_token_count"
        else:
            counter_key = f"tenant:{tenant_id}:token_count"
        
        # Obtener contador
        count = await redis_client.get(counter_key)
        
        return int(count) if count else 0
    except Exception as e:
        logger.error(f"Error getting token count from Redis: {str(e)}")
        return 0

async def get_agent_usage_stats(agent_id: str, date: Optional[str] = None) -> Dict[str, int]:
    """
    Obtiene estadísticas de uso de un agente para una fecha.
    
    Args:
        agent_id: ID del agente
        date: Fecha en formato YYYY-MM-DD (None = hoy)
        
    Returns:
        Dict[str, int]: Estadísticas de uso
    """
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            return {}
        
        # Usar fecha especificada o fecha actual
        date_key = date or time.strftime("%Y-%m-%d")
        agent_key = f"agent:{agent_id}:usage:{date_key}"
        
        # Obtener estadísticas
        stats = await redis_client.hgetall(agent_key)
        
        # Convertir valores a enteros
        return {k: int(v) for k, v in stats.items()}
    except Exception as e:
        logger.error(f"Error getting agent usage stats from Redis: {str(e)}")
        return {}

# Funciones para invalidar caché por niveles

async def invalidate_tenant_cache(tenant_id: str) -> int:
    """
    Invalida toda la caché para un tenant específico.
    Esta función debe llamarse cuando se actualizan las configuraciones
    del tenant en Supabase.
    
    Args:
        tenant_id: ID del tenant
        
    Returns:
        int: Número de claves eliminadas
    """
    logger.info(f"Invalidando toda la caché para tenant {tenant_id}")
    pattern = f"{tenant_id}:*"
    return await cache_delete_pattern(pattern)

async def invalidate_agent_cache(tenant_id: str, agent_id: str) -> int:
    """
    Invalida toda la caché para un agente específico.
    Esta función debe llamarse cuando se actualizan las configuraciones
    del agente o sus herramientas.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        
    Returns:
        int: Número de claves eliminadas
    """
    logger.info(f"Invalidando caché para agente {agent_id} del tenant {tenant_id}")
    pattern = f"{tenant_id}:*agent:{agent_id}*"
    return await cache_delete_pattern(pattern)

async def invalidate_conversation_cache(tenant_id: str, agent_id: str, conversation_id: str) -> int:
    """
    Invalida la caché para una conversación específica.
    Esta función debe llamarse cuando se borran o modifican mensajes.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        conversation_id: ID de la conversación
        
    Returns:
        int: Número de claves eliminadas
    """
    logger.info(f"Invalidando caché para conversación {conversation_id} del agente {agent_id}")
    pattern = f"{tenant_id}:*conv:{conversation_id}*"
    # También eliminar clave directa de la conversación
    direct_key = f"conv:{conversation_id}"
    messages_key = f"conv:{conversation_id}:messages"
    
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.delete(direct_key, messages_key)
    
    return await cache_delete_pattern(pattern)

async def invalidate_collection_cache(tenant_id: str, collection_id: str) -> int:
    """
    Invalida la caché para una colección específica.
    Esta función debe llamarse cuando se actualizan los documentos de una colección.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        
    Returns:
        int: Número de claves eliminadas
    """
    logger.info(f"Invalidando caché para colección {collection_id} del tenant {tenant_id}")
    pattern = f"{tenant_id}:*coll:{collection_id}*"
    return await cache_delete_pattern(pattern)