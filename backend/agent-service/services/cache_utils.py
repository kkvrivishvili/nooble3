"""
Utilidades para estandarización de caché en el Agent Service.

Este módulo implementa las tres mejoras principales del sistema de caché:
1. Estandarización de claves de caché
2. Uso de TTLs centralizados 
3. Invalidación en cascada para recursos relacionados
"""

import logging
import sys
import json
from typing import Dict, Any, Optional, List, Union, Tuple

from common.cache import CacheManager, get_with_cache_aside
from common.cache.helpers import standardize_llama_metadata, serialize_for_cache
from common.core.constants import (
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT,
    DEFAULT_TTL_MAPPING
)
from common.tracking import track_cache_metrics
from common.context import Context
from common.db import get_supabase_client
from common.db.tables import get_table_name

# Importamos las constantes locales del Agent Service
from config.constants import (
    CACHE_TYPE_AGENT, CACHE_TYPE_AGENT_CONFIG, CACHE_TYPE_AGENT_TOOLS,
    CACHE_TYPE_CONVERSATION, CACHE_TYPE_CONVERSATION_MEMORY,
    CACHE_TYPE_CONVERSATION_MESSAGE, CACHE_TYPE_CONVERSATION_MESSAGES_LIST,
    CACHE_TYPE_AGENT_EXECUTION_STATE, CACHE_TYPE_COLLECTION_METADATA,
    AGENT_SERVICE_TTL_MAPPING, get_ttl_for_data_type
)

logger = logging.getLogger(__name__)

async def get_agent_with_cache(
    agent_id: str,
    tenant_id: str,
    fetch_function,
    agent_service=None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Obtiene un agente usando el patrón Cache-Aside estandarizado.
    
    Args:
        agent_id: ID del agente
        tenant_id: ID del tenant
        fetch_function: Función para obtener el agente de la base de datos
        agent_service: Referencia opcional al servicio de agentes
        
    Returns:
        Tuple con (agent_data, cache_metrics)
    """
    return await get_with_cache_aside(
        data_type=CACHE_TYPE_AGENT,  # Usar constante en lugar de string literal
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_function,
        generate_func=None,
        ttl=get_ttl_for_data_type(CACHE_TYPE_AGENT)  # Usar TTL según el tipo de datos
    )

async def get_agent_config_with_cache(
    agent_id: str, 
    tenant_id: str,
    fetch_function
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Obtiene la configuración de un agente usando el patrón Cache-Aside estandarizado.
    
    Args:
        agent_id: ID del agente
        tenant_id: ID del tenant
        fetch_function: Función para obtener la configuración de la base de datos
        
    Returns:
        Tuple con (config_data, cache_metrics)
    """
    return await get_with_cache_aside(
        data_type=CACHE_TYPE_AGENT_CONFIG,
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_function,
        generate_func=None,
        ttl=get_ttl_for_data_type(CACHE_TYPE_AGENT_CONFIG)
    )

async def get_conversation_memory_with_cache(
    conversation_id: str,
    tenant_id: str,
    agent_id: Optional[str],
    fetch_function,
    generate_function
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Obtiene la memoria de conversación usando el patrón Cache-Aside estandarizado.
    
    Args:
        conversation_id: ID de la conversación
        tenant_id: ID del tenant
        agent_id: ID opcional del agente
        fetch_function: Función para obtener la memoria de la base de datos
        generate_function: Función para generar una memoria vacía si no existe
        
    Returns:
        Tuple con (memory_data, cache_metrics)
    """
    return await get_with_cache_aside(
        data_type=CACHE_TYPE_CONVERSATION_MEMORY,
        resource_id=conversation_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_function,
        generate_func=generate_function,
        agent_id=agent_id,
        conversation_id=conversation_id,
        ttl=get_ttl_for_data_type(CACHE_TYPE_CONVERSATION_MEMORY)
    )

async def _track_cache_size(data_type: str, tenant_id: str, object_size: int) -> None:
    """
    Registra el tamaño de un objeto en caché para monitoreo.
    
    Args:
        data_type: Tipo de datos
        tenant_id: ID del tenant
        object_size: Tamaño estimado del objeto en bytes
    """
    try:
        # Solo registrar si el objeto supera cierto tamaño (ej: 1KB)
        if object_size > 1024:
            await track_cache_metrics(
                data_type=data_type,
                tenant_id=tenant_id,
                operation="size",
                cache_size=object_size
            )
            
            # Emitir advertencia si el objeto es muy grande
            if object_size > 100 * 1024:  # > 100KB
                logger.warning(
                    f"Objeto grande en caché: {data_type}, tenant: {tenant_id}, "
                    f"tamaño: {object_size/1024:.2f}KB"
                )
    except Exception as e:
        logger.warning(f"Error al registrar tamaño de caché: {str(e)}")

async def invalidate_agent_cache_cascade(
    tenant_id: str,
    agent_id: str,
    invalidate_conversations: bool = False,
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """
    Invalida en cascada todas las cachés relacionadas con un agente.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        invalidate_conversations: Si es True, también invalida la caché de conversaciones
        ctx: Contexto opcional
        
    Returns:
        Diccionario con resultados de invalidación (número de claves invalidadas por tipo)
    """
    invalidation_results = {
        "agent": 0,
        "agent_config": 0,
        "agent_tools": 0,
        "conversations": 0,
        "messages": 0
    }
    
    # 1. Invalidar configuración del agente
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT, 
        resource_id=agent_id
    )
    invalidation_results["agent"] += 1
    
    # 2. Invalidar configuración de herramientas
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT_CONFIG, 
        resource_id=agent_id
    )
    invalidation_results["agent_config"] += 1
    
    # 3. Invalidar herramientas del agente
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT_TOOLS, 
        resource_id=agent_id
    )
    invalidation_results["agent_tools"] += 1
    
    # 4. Invalidar estado de ejecución del agente
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT_EXECUTION_STATE, 
        resource_id=agent_id
    )
    
    # 5. Si se solicita, invalidar conversaciones relacionadas
    if invalidate_conversations:
        # Obtener todos los IDs de conversación relacionados con este agente
        try:
            supabase = get_supabase_client()
            result = await supabase.table(get_table_name("conversations")) \
                .select("id") \
                .eq("agent_id", agent_id) \
                .eq("tenant_id", tenant_id) \
                .execute()
            
            if result.data:
                for conv in result.data:
                    conv_id = conv.get("id")
                    if conv_id:
                        # Invalidar memoria de la conversación
                        await CacheManager.invalidate(
                            tenant_id=tenant_id,
                            data_type=CACHE_TYPE_CONVERSATION_MEMORY,
                            resource_id=conv_id,
                            agent_id=agent_id
                        )
                        
                        # Intentar invalidar la lista de mensajes
                        try:
                            await CacheManager.get_instance().delete(
                                f"{tenant_id}:{CACHE_TYPE_CONVERSATION_MESSAGES_LIST}:conv:{conv_id}"
                            )
                            invalidation_results["messages"] += 1
                        except Exception as e:
                            logger.warning(f"Error al invalidar lista de mensajes: {str(e)}")
                        
                        invalidation_results["conversations"] += 1
        except Exception as e:
            logger.warning(f"Error al invalidar conversaciones: {str(e)}")
    
    # Registrar métricas de invalidación
    await track_cache_metrics(
        data_type="agent_cascade", 
        tenant_id=tenant_id, 
        operation="invalidate", 
        hit=True,
        latency_ms=0
    )
    
    return invalidation_results

async def invalidate_conversation_cache_cascade(
    tenant_id: str,
    conversation_id: str,
    agent_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Invalida en cascada todas las cachés relacionadas con una conversación.
    
    Args:
        tenant_id: ID del tenant
        conversation_id: ID de la conversación
        agent_id: ID opcional del agente
        
    Returns:
        Diccionario con resultados de invalidación
    """
    invalidation_results = {
        "memory": 0,
        "messages": 0,
        "messages_list": 0
    }
    
    # 1. Invalidar memoria de conversación
    await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type=CACHE_TYPE_CONVERSATION_MEMORY,
        resource_id=conversation_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    invalidation_results["memory"] += 1
    
    # 2. Intentar invalidar la lista de mensajes
    try:
        key = f"{tenant_id}:{CACHE_TYPE_CONVERSATION_MESSAGES_LIST}"
        if agent_id:
            key += f":agent:{agent_id}"
        key += f":conv:{conversation_id}"
        
        await CacheManager.get_instance().delete(key)
        invalidation_results["messages_list"] += 1
    except Exception as e:
        logger.warning(f"Error al invalidar lista de mensajes: {str(e)}")
    
    # 3. Registrar métricas de invalidación
    await track_cache_metrics(
        data_type="conversation_cascade", 
        tenant_id=tenant_id, 
        operation="invalidate", 
        hit=True,
        latency_ms=0
    )
    
    return invalidation_results
