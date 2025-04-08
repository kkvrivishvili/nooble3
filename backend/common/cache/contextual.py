# 2. Mejora de common/cache/contextual.py - SISTEMA DE CACHÉ EN CASCADA

import time
import logging
from typing import Dict, Any, List, Optional, Union

from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id
from .redis import cache_get, cache_set, cache_delete_pattern, generate_hash

logger = logging.getLogger(__name__)

# Caché en memoria para datos de uso frecuente
_memory_cache: Dict[str, Any] = {}
_memory_expiry: Dict[str, float] = {}

def build_cache_key(
    key_type: str,
    resource_id: str,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> str:
    """Genera una clave de caché con todos los niveles de contexto relevantes."""
    
    # Usar el contexto actual si no se proporciona explícitamente
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
    if agent_id is None:
        agent_id = get_current_agent_id()
    if conversation_id is None:
        conversation_id = get_current_conversation_id()
    
    # Construir clave de forma jerárquica
    key_parts = [tenant_id, key_type]
    
    # Añadir niveles de contexto disponibles
    if user_id:
        key_parts.append(f"user:{user_id}")
    if agent_id:
        key_parts.append(f"agent:{agent_id}")
    if conversation_id:
        key_parts.append(f"conv:{conversation_id}")
    if collection_id:
        key_parts.append(f"coll:{collection_id}")
    
    # Añadir identificador específico
    key_parts.append(resource_id)
    
    return ":".join(key_parts)

async def get_cached_value_multi_level(
    key_type: str,
    resource_id: str,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    use_memory_cache: bool = True
) -> Optional[Any]:
    """
    Busca un valor en caché usando una estrategia de cascada multinivel.
    
    Búsqueda en orden:
    1. Caché en memoria (si use_memory_cache=True)
    2. Nivel más específico (todos los niveles de contexto)
    3. Niveles intermedios (eliminando progresivamente elementos de contexto)
    4. Nivel más general (solo tenant y tipo)
    """
    
    # Usar el contexto actual si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    
    # Clave completa para caché en memoria
    memory_key = f"{tenant_id}:{key_type}:{resource_id}"
    if agent_id: memory_key += f":{agent_id}"
    if conversation_id: memory_key += f":{conversation_id}"
    if collection_id: memory_key += f":{collection_id}"
    
    # 1. Verificar en memoria primero (más rápido)
    if use_memory_cache and memory_key in _memory_cache:
        if time.time() < _memory_expiry.get(memory_key, 0):
            return _memory_cache[memory_key]
        # Limpiar si expiró
        del _memory_cache[memory_key]
        del _memory_expiry[memory_key]
    
    # 2. Generar niveles de claves para búsqueda en cascada
    key_levels = []
    
    # Nivel más específico (todos los parámetros disponibles)
    if conversation_id and agent_id and collection_id:
        key_levels.append(build_cache_key(
            key_type, resource_id, tenant_id, agent_id, conversation_id, collection_id
        ))
    
    # Nivel de conversación y agente
    if conversation_id and agent_id:
        key_levels.append(build_cache_key(
            key_type, resource_id, tenant_id, agent_id, conversation_id
        ))
    
    # Nivel de agente y colección
    if agent_id and collection_id:
        key_levels.append(build_cache_key(
            key_type, resource_id, tenant_id, agent_id, collection_id=collection_id
        ))
    
    # Nivel de agente
    if agent_id:
        key_levels.append(build_cache_key(
            key_type, resource_id, tenant_id, agent_id
        ))
    
    # Nivel de colección
    if collection_id:
        key_levels.append(build_cache_key(
            key_type, resource_id, tenant_id, collection_id=collection_id
        ))
    
    # Nivel base (solo tenant)
    key_levels.append(build_cache_key(
        key_type, resource_id, tenant_id
    ))
    
    # 3. Buscar en cada nivel
    for key in key_levels:
        value = await cache_get(key)
        if value is not None:
            # Guardar en memoria para acceso futuro
            if use_memory_cache:
                _memory_cache[memory_key] = value
                _memory_expiry[memory_key] = time.time() + 300  # 5 minutos
            return value
    
    # No encontrado en ningún nivel
    return None

async def cache_value_multi_level(
    key_type: str,
    resource_id: str,
    value: Any,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    ttl: int = 3600,
    use_memory_cache: bool = True
) -> bool:
    """
    Guarda un valor en caché con múltiples niveles de contexto.
    
    Args:
        key_type: Tipo de recurso (embed, query, agent, etc)
        resource_id: ID específico del recurso
        value: Valor a guardar
        tenant_id, agent_id, etc: Información de contexto
        ttl: Tiempo de vida en segundos
        use_memory_cache: Si debe guardar también en memoria
    """
    
    # Usar el contexto actual si no se proporciona
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    
    # Generar clave con todos los niveles disponibles
    key = build_cache_key(
        key_type, resource_id, tenant_id, agent_id, conversation_id, collection_id
    )
    
    # Guardar en Redis
    result = await cache_set(key, value, ttl)
    
    # Guardar también en memoria para acceso rápido
    if use_memory_cache:
        memory_key = f"{tenant_id}:{key_type}:{resource_id}"
        if agent_id: memory_key += f":{agent_id}"
        if conversation_id: memory_key += f":{conversation_id}"
        if collection_id: memory_key += f":{collection_id}"
        
        _memory_cache[memory_key] = value
        _memory_expiry[memory_key] = time.time() + min(300, ttl)  # 5 min o menos
    
    return result

async def invalidate_cache_hierarchy(
    tenant_id: str,
    key_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None
) -> int:
    """
    Invalida la caché en todos los niveles jerárquicos relevantes.
    
    Args:
        tenant_id: ID del tenant (obligatorio)
        key_type: Tipo de clave a invalidar o None para todos
        agent_id, etc: Niveles de contexto específicos
    
    Returns:
        int: Número de claves invalidadas
    """
    
    # 1. Limpiar memoria
    keys_to_delete = []
    for key in list(_memory_cache.keys()):
        parts = key.split(':')
        if parts[0] != tenant_id:
            continue
            
        if key_type is not None and parts[1] != key_type:
            continue
            
        if agent_id is not None and agent_id not in key:
            continue
            
        if conversation_id is not None and conversation_id not in key:
            continue
            
        if collection_id is not None and collection_id not in key:
            continue
            
        keys_to_delete.append(key)
    
    for key in keys_to_delete:
        if key in _memory_cache:
            del _memory_cache[key]
            del _memory_expiry[key]
    
    # 2. Generar patrón para Redis
    pattern_parts = [tenant_id]
    
    if key_type:
        pattern_parts.append(key_type)
    
    if agent_id:
        pattern_parts.append(f"*agent:{agent_id}*")
    
    if conversation_id:
        pattern_parts.append(f"*conv:{conversation_id}*")
    
    if collection_id:
        pattern_parts.append(f"*coll:{collection_id}*")
    
    pattern = ":".join(pattern_parts) + "*"
    
    # 3. Invalidar en Redis
    return await cache_delete_pattern(pattern)