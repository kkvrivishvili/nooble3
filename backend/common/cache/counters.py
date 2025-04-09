"""
Contadores y estadísticas en caché para tracking de uso.
"""

import logging
import time
from typing import Dict, Any, Optional

from .redis import get_redis_client, cache_delete_pattern
from ..errors.exceptions import ServiceError
from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id, get_current_collection_id
from ..config.settings import get_settings

logger = logging.getLogger(__name__)

async def increment_token_counter(
    tenant_id: Optional[str] = None,
    tokens: int = 0,
    token_type: str = "llm",
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """
    Incrementa un contador de tokens en Redis.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        tokens: Número de tokens a incrementar
        token_type: Tipo de token ('llm' o 'embedding')
        agent_id: ID del agente (opcional, se usa del contexto si no se proporciona)
        conversation_id: ID de la conversación (opcional, se usa del contexto si no se proporciona)
        
    Returns:
        bool: True si se incrementó correctamente
        
    Raises:
        ServiceError: Si hay un problema con la operación
    """
    # Usar tenant_id del contexto si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    
    # Usar agent_id del contexto si no se proporciona
    if agent_id is None:
        agent_id = get_current_agent_id()
    
    # Usar conversation_id del contexto si no se proporciona
    if conversation_id is None:
        conversation_id = get_current_conversation_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede incrementar contador sin tenant_id válido")
        return False
        
    if tokens <= 0:
        logger.debug(f"Ignorando incremento de contador para {tokens} tokens")
        return False
        
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.error("No se pudo obtener cliente Redis para incrementar contador")
            raise ServiceError(
                message="Error de conexión a Redis",
                status_code=500,
                error_code="REDIS_CONNECTION_ERROR",
                context={"tenant_id": tenant_id, "token_type": token_type}
            )
        
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
            
            # Obtener TTL de configuración
            settings = get_settings()
            stats_ttl = getattr(settings, "usage_stats_ttl", 172800)  # 48 horas por defecto
            
            # TTL para estadísticas diarias
            await pipeline.expire(agent_key, stats_ttl)
            
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
                    # TTL para este set
                    await pipeline.expire(conv_set_key, stats_ttl)
        
        await pipeline.execute()
        return True
    except Exception as e:
        error_context = {
            "tenant_id": tenant_id,
            "token_type": token_type,
            "agent_id": agent_id
        }
        logger.error(f"Error incrementando contador de tokens en Redis: {str(e)}", extra=error_context)
        
        # No propagar ServiceError para no interrumpir flujos críticos
        # Esta es una operación no crítica que puede fallar silenciosamente
        return False

async def get_token_count(tenant_id: Optional[str] = None, token_type: str = "llm") -> int:
    """
    Obtiene el contador de tokens de un tenant desde Redis.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        token_type: Tipo de token ('llm' o 'embedding')
        
    Returns:
        int: Número de tokens o 0 si no existe
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar tenant_id del contexto si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede obtener contador sin tenant_id válido")
        return 0
    
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.error("No se pudo obtener cliente Redis para consultar contador")
            raise ServiceError(
                message="Error de conexión a Redis",
                status_code=500,
                error_code="REDIS_CONNECTION_ERROR",
                context={"tenant_id": tenant_id, "token_type": token_type}
            )
        
        # Clave según tipo de token
        if token_type == "embedding":
            counter_key = f"tenant:{tenant_id}:embedding_token_count"
        else:
            counter_key = f"tenant:{tenant_id}:token_count"
        
        # Obtener contador
        count = await redis_client.get(counter_key)
        
        return int(count) if count else 0
    except Exception as e:
        error_context = {
            "tenant_id": tenant_id,
            "token_type": token_type
        }
        logger.error(f"Error obteniendo contador de tokens desde Redis: {str(e)}", extra=error_context)
        
        # No propagar ServiceError para consultas de solo lectura no críticas
        return 0

async def get_agent_usage_stats(agent_id: Optional[str] = None, date: Optional[str] = None) -> Dict[str, int]:
    """
    Obtiene estadísticas de uso de un agente para una fecha.
    
    Args:
        agent_id: ID del agente (opcional, se usa del contexto si no se proporciona)
        date: Fecha en formato YYYY-MM-DD (None = hoy)
        
    Returns:
        Dict[str, int]: Estadísticas de uso
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar agent_id del contexto si no se proporciona
    agent_id = agent_id or get_current_agent_id()
    
    if not agent_id:
        logger.warning("No se pueden obtener estadísticas sin agent_id válido")
        return {}
    
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.error("No se pudo obtener cliente Redis para consultar estadísticas")
            raise ServiceError(
                message="Error de conexión a Redis",
                status_code=500,
                error_code="REDIS_CONNECTION_ERROR",
                context={"agent_id": agent_id}
            )
        
        # Usar fecha especificada o fecha actual
        date_key = date or time.strftime("%Y-%m-%d")
        agent_key = f"agent:{agent_id}:usage:{date_key}"
        
        # Obtener estadísticas
        stats = await redis_client.hgetall(agent_key)
        
        # Convertir valores a enteros
        return {k: int(v) for k, v in stats.items()}
    except Exception as e:
        error_context = {
            "agent_id": agent_id,
            "date": date
        }
        logger.error(f"Error obteniendo estadísticas de uso desde Redis: {str(e)}", extra=error_context)
        
        # No propagar ServiceError para consultas de solo lectura no críticas
        return {}

# Funciones para invalidar caché por niveles

async def invalidate_tenant_cache(tenant_id: Optional[str] = None) -> int:
    """
    Invalida toda la caché para un tenant específico.
    Esta función debe llamarse cuando se actualizan las configuraciones
    del tenant en Supabase.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        
    Returns:
        int: Número de claves eliminadas
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar tenant_id del contexto si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede invalidar caché sin tenant_id válido")
        return 0
    
    logger.info(f"Invalidando toda la caché para tenant {tenant_id}")
    pattern = f"{tenant_id}:*"
    
    try:
        return await cache_delete_pattern(pattern)
    except Exception as e:
        error_context = {"tenant_id": tenant_id}
        logger.error(f"Error invalidando caché del tenant: {str(e)}", extra=error_context)
        raise ServiceError(
            message="Error al invalidar caché del tenant",
            status_code=500,
            error_code="CACHE_INVALIDATION_ERROR",
            context=error_context
        )

async def invalidate_agent_cache(tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> int:
    """
    Invalida toda la caché para un agente específico.
    Esta función debe llamarse cuando se actualizan las configuraciones
    del agente o sus herramientas.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        agent_id: ID del agente (opcional, se usa del contexto si no se proporciona)
        
    Returns:
        int: Número de claves eliminadas
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar tenant_id y agent_id del contexto si no se proporcionan
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede invalidar caché sin tenant_id válido")
        return 0
        
    if not agent_id:
        logger.warning("No se puede invalidar caché sin agent_id válido")
        return 0
    
    logger.info(f"Invalidando caché para agente {agent_id} del tenant {tenant_id}")
    pattern = f"{tenant_id}:*agent:{agent_id}*"
    
    try:
        return await cache_delete_pattern(pattern)
    except Exception as e:
        error_context = {"tenant_id": tenant_id, "agent_id": agent_id}
        logger.error(f"Error invalidando caché del agente: {str(e)}", extra=error_context)
        raise ServiceError(
            message="Error al invalidar caché del agente",
            status_code=500,
            error_code="CACHE_INVALIDATION_ERROR",
            context=error_context
        )

async def invalidate_conversation_cache(tenant_id: Optional[str] = None, agent_id: Optional[str] = None, conversation_id: Optional[str] = None) -> int:
    """
    Invalida la caché para una conversación específica.
    Esta función debe llamarse cuando se borran o modifican mensajes.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        agent_id: ID del agente (opcional, se usa del contexto si no se proporciona)
        conversation_id: ID de la conversación (opcional, se usa del contexto si no se proporciona)
        
    Returns:
        int: Número de claves eliminadas
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar valores del contexto si no se proporcionan
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede invalidar caché sin tenant_id válido")
        return 0
        
    if not conversation_id:
        logger.warning("No se puede invalidar caché sin conversation_id válido")
        return 0
    
    logger.info(f"Invalidando caché para conversación {conversation_id} del agente {agent_id}")
    pattern = f"{tenant_id}:*conv:{conversation_id}*"
    # También eliminar clave directa de la conversación
    direct_key = f"conv:{conversation_id}"
    messages_key = f"conv:{conversation_id}:messages"
    
    try:
        redis_client = await get_redis_client()
        if redis_client is None:
            logger.error("No se pudo obtener cliente Redis para invalidar caché")
            raise ServiceError(
                message="Error de conexión a Redis",
                status_code=500,
                error_code="REDIS_CONNECTION_ERROR",
                context={"tenant_id": tenant_id, "conversation_id": conversation_id}
            )
            
        # Eliminar claves directas
        await redis_client.delete(direct_key)
        await redis_client.delete(messages_key)
        
        # Eliminar por patrón
        deleted = await cache_delete_pattern(pattern)
        
        return deleted + 2  # +2 por las claves directas
    except Exception as e:
        error_context = {"tenant_id": tenant_id, "agent_id": agent_id, "conversation_id": conversation_id}
        logger.error(f"Error invalidando caché de conversación: {str(e)}", extra=error_context)
        raise ServiceError(
            message="Error al invalidar caché de conversación",
            status_code=500,
            error_code="CACHE_INVALIDATION_ERROR",
            context=error_context
        )

async def invalidate_collection_cache(tenant_id: Optional[str] = None, collection_id: Optional[str] = None) -> int:
    """
    Invalida la caché para una colección específica.
    Esta función debe llamarse cuando se actualizan los documentos de una colección.
    
    Args:
        tenant_id: ID del tenant (opcional, se usa del contexto si no se proporciona)
        collection_id: ID de la colección (opcional, se usa del contexto si no se proporciona)
        
    Returns:
        int: Número de claves eliminadas
        
    Raises:
        ServiceError: Si hay un problema crítico con la operación
    """
    # Usar tenant_id del contexto si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    
    # Usar collection_id del contexto si no se proporciona
    if collection_id is None:
        collection_id = get_current_collection_id()
    
    if not tenant_id or tenant_id == "default":
        logger.warning("No se puede invalidar caché sin tenant_id válido")
        return 0
        
    if not collection_id:
        logger.warning("No se puede invalidar caché sin collection_id válido")
        return 0
    
    logger.info(f"Invalidando caché para colección {collection_id} del tenant {tenant_id}")
    pattern = f"{tenant_id}:*coll:{collection_id}*"
    
    try:
        return await cache_delete_pattern(pattern)
    except Exception as e:
        error_context = {"tenant_id": tenant_id, "collection_id": collection_id}
        logger.error(f"Error invalidando caché de colección: {str(e)}", extra=error_context)
        raise ServiceError(
            message="Error al invalidar caché de colección",
            status_code=500,
            error_code="CACHE_INVALIDATION_ERROR",
            context=error_context
        )