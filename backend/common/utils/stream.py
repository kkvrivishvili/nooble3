"""
Utilidades para streaming de respuestas LLM manteniendo contexto.
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator

from ..cache.manager import CacheManager
from ..cache.helpers import generate_resource_id_hash, get_with_cache_aside, serialize_for_cache
from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id

logger = logging.getLogger(__name__)

async def stream_llm_response(
    prompt: str,
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    model_name: str,
    use_cache: bool = True,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    collection_ids: Optional[List[str]] = None,
    system_message: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    stop_sequences: Optional[List[str]] = None,
    allow_fallback: bool = True,
    streaming_callback: Optional[Any] = None,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Procesa una solicitud a un LLM con capacidad de streaming.
    
    Gestiona automáticamente:
    - Caché de respuestas
    - Memoria de agente (historial de mensajes)
    - Registro de colecciones accedidas
    - Fallback a modelos alternativos
    - Streaming de respuestas por tokens
    
    Args:
        prompt: Texto de la consulta
        tenant_id: ID del tenant
        agent_id: ID del agente
        conversation_id: ID de la conversación
        model_name: Nombre del modelo LLM
        use_cache: Si se debe usar caché
        user_id: ID opcional del usuario
        session_id: ID opcional de la sesión
        collection_ids: Lista de IDs de colecciones usadas
        system_message: Mensaje de sistema personalizado
        temperature: Temperatura para generación
        max_tokens: Límite de tokens de salida
        stop_sequences: Secuencias para detener generación
        allow_fallback: Permitir fallback a modelo alternativo
        streaming_callback: Función de callback para streaming
        
    Returns:
        AsyncGenerator que produce tokens de respuesta
    """
    # Inicializar configuraciones y contexto
    from ..config.settings import get_settings
    
    settings = get_settings()
    
    # Registrar colecciones utilizadas en esta consulta
    if collection_ids:
        for coll_id in collection_ids:
            collection_resource_id = f"collection:{coll_id}"
            await CacheManager.set(
                data_type="agent_collection",
                resource_id=collection_resource_id,
                value={"collection_id": coll_id, "last_accessed": time.time()},
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id
            )
    
    # 1. Verificar en caché si hay una respuesta previa para esta consulta exacta
    if use_cache:
        resource_id = generate_resource_id_hash(prompt)
        cached_response = await CacheManager.get(
            data_type="query",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        
        if cached_response:
            logger.info(f"Respuesta recuperada de caché para {agent_id}")
            
            # Registrar mensaje en la memoria del agente (incluso para respuestas de caché)
            message_id = str(uuid.uuid4())
            await CacheManager.set(
                data_type="agent_message",
                resource_id=message_id,
                value={
                    "role": "assistant",
                    "content": cached_response,
                    "model": model_name,
                    "timestamp": time.time()
                },
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id
            )
            
            # Añadir mensaje a la lista de mensajes de la conversación
            await _add_message_to_conversation(tenant_id, agent_id, conversation_id, message_id)
            
            # Retornar respuesta cacheada como único bloque
            yield cached_response
            return
    
    # 2. Registrar mensaje del usuario en la memoria del agente
    user_message_id = str(uuid.uuid4())
    await CacheManager.set(
        data_type="agent_message",
        resource_id=user_message_id,
        value={
            "role": "user",
            "content": prompt,
            "timestamp": time.time()
        },
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Añadir mensaje a la lista de mensajes de la conversación
    await _add_message_to_conversation(tenant_id, agent_id, conversation_id, user_message_id)
    
    # 3. Construir el contexto para el LLM
    messages = await _get_conversation_messages(tenant_id, agent_id, conversation_id)
    
    # Añadir mensaje de sistema si se proporciona
    if system_message:
        messages.insert(0, {"role": "system", "content": system_message})
    elif settings.default_system_message:
        messages.insert(0, {"role": "system", "content": settings.default_system_message})
    
    # 4. Preparar cliente LLM
    try:
        from ..llm.client import get_llm_client
        llm_client = await get_llm_client(model_name)
    except Exception as e:
        error_message = f"Error al inicializar cliente LLM: {str(e)}"
        logger.error(error_message)
        yield error_message
        return
    
    # 5. Generar la respuesta con streaming
    full_response = ""
    try:
        # Streaming desde el LLM
        if streaming_callback:
            streaming_callback({"status": "started"})
            
        stream = await llm_client.create_chat_completion(
            messages=messages,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop_sequences,
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield token
    except Exception as e:
        error_message = f"Error: {str(e)}"
        logger.error(f"Error en streaming LLM: {error_message}")
        yield error_message
        return
    
    # 6. Guardar respuesta completa en caché
    if use_cache:
        resource_id = generate_resource_id_hash(prompt)
        await CacheManager.set(
            data_type="query",
            resource_id=resource_id,
            value=full_response,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=3600
        )
    
    # 7. Registrar mensaje en la memoria del agente
    assistant_message_id = str(uuid.uuid4())
    await CacheManager.set(
        data_type="agent_message",
        resource_id=assistant_message_id,
        value={
            "role": "assistant",
            "content": full_response,
            "model": model_name,
            "timestamp": time.time()
        },
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Añadir mensaje a la lista de mensajes de la conversación
    await _add_message_to_conversation(tenant_id, agent_id, conversation_id, assistant_message_id)
    
    if streaming_callback:
        streaming_callback({"status": "completed"})

async def _add_message_to_conversation(tenant_id: str, agent_id: str, conversation_id: str, message_id: str) -> None:
    """
    Añade un ID de mensaje a la lista de mensajes de una conversación.
    """
    conv_resource_id = f"conversation:{conversation_id}"
    messages_list = await CacheManager.get(
        data_type="conversation_messages",
        resource_id=conv_resource_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    ) or []
    
    # Añadir el nuevo mensaje a la lista
    messages_list.append(message_id)
    
    # Guardar la lista actualizada
    await CacheManager.set(
        data_type="conversation_messages",
        resource_id=conv_resource_id,
        value=messages_list,
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )

async def _get_conversation_messages(tenant_id: str, agent_id: str, conversation_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene todos los mensajes de una conversación.
    """
    conv_resource_id = f"conversation:{conversation_id}"
    message_ids = await CacheManager.get(
        data_type="conversation_messages",
        resource_id=conv_resource_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    ) or []
    
    messages = []
    for msg_id in message_ids:
        message = await CacheManager.get(
            data_type="agent_message",
            resource_id=msg_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        if message:
            # Solo incluir los campos relevantes para el LLM
            messages.append({
                "role": message.get("role", "user"),
                "content": message.get("content", "")
            })
    
    return messages