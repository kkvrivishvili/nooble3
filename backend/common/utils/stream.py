"""
Utilidades para streaming de respuestas LLM manteniendo contexto.
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator

from ..cache.contextual import AgentMemory, build_cache_key, cache_get, cache_set
from ..cache.redis import generate_hash
from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id

logger = logging.getLogger(__name__)

async def stream_llm_response(
    prompt: str,
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    model_name: str,
    system_prompt: Optional[str] = None,
    collection_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    use_cache: bool = True
) -> AsyncGenerator[str, None]:
    """
    Genera una respuesta del LLM en modo streaming manteniendo el contexto.
    
    Args:
        prompt: Consulta del usuario
        tenant_id: ID del tenant
        agent_id: ID del agente
        conversation_id: ID de la conversación
        model_name: Modelo LLM a utilizar
        system_prompt: Prompt de sistema
        collection_ids: IDs de colecciones a consultar
        user_id: ID del usuario (opcional)
        session_id: ID de sesión (opcional)
        tools: Herramientas disponibles (opcional)
        use_cache: Si debe usar caché (True por defecto)
        
    Yields:
        str: Tokens generados uno por uno
    """
    from ..llm.ollama import OllamaLLM
    from ..llm.openai import get_openai_client
    from ..config.settings import get_settings
    
    settings = get_settings()
    
    # Crear memoria del agente
    memory = AgentMemory(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id
    )
    
    # Registrar colecciones
    if collection_ids:
        for coll_id in collection_ids:
            await memory.register_collection(coll_id)
    
    # 1. Verificar en caché si hay una respuesta previa para esta consulta exacta
    if use_cache:
        cache_key = build_cache_key(
            key_type="query",
            resource_id=generate_hash(prompt),
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            collection_ids=collection_ids,
            conversation_id=conversation_id
        )
        
        cached_response = await cache_get(cache_key)
        if cached_response and not tools:  # No reutilizar caché si hay herramientas
            # Simular streaming para respuesta cacheada
            for chunk in cached_response.split():
                yield chunk + " "
                await asyncio.sleep(0.05)  # Simular latencia
            return
    
    # 2. Consultar RAG si hay colecciones
    context_chunks = []
    if collection_ids:
        # Este es un poco simplificado - debería llamar al servicio de query real
        # Aquí solo se muestra el concepto
        try:
            from ..utils.http import call_service
            from ..config.settings import get_settings
            
            settings = get_settings()
            
            for collection_id in collection_ids:
                # Llamar al servicio de Query para obtener datos relevantes
                response = await call_service(
                    url=f"{settings.query_service_url}/search",
                    data={
                        "tenant_id": tenant_id,
                        "query": prompt,
                        "collection_id": collection_id,
                        "limit": 5
                    },
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    collection_id=collection_id,
                    operation_type="rag_query"
                )
                
                # Verificar éxito y extraer datos según el formato estandarizado
                if response.get("success", False) and response.get("data", {}) is not None:
                    # Extraer resultados del campo data de la respuesta estandarizada
                    response_data = response.get("data", {})
                    if "results" in response_data:
                        context_chunks.extend(response_data["results"])
        except Exception as e:
            logger.error(f"Error consultando RAG: {str(e)}")
            # Continuar sin contexto si falla
    
    # 3. Obtener historial de conversación
    conversation_history = await memory.get_conversation_history()
    
    # 4. Construir prompt completo
    full_prompt = []
    
    # Añadir historial si existe
    if conversation_history:
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            full_prompt.append(f"{role}: {content}")
    
    # Añadir contexto RAG si existe
    if context_chunks:
        full_prompt.append("Contexto relevante:")
        for chunk in context_chunks:
            full_prompt.append(f"- {chunk['text']}")
    
    # Añadir prompt actual
    full_prompt.append(f"User: {prompt}")
    
    # Unir todo
    final_prompt = "\n\n".join(full_prompt)
    
    # 5. Streaming de la respuesta
    full_response = ""
    use_ollama = settings.use_ollama
    
    try:
        if use_ollama:
            # Usar Ollama con streaming
            ollama = OllamaLLM(
                model_name=model_name,
                temperature=0.7
            )
            
            async for chunk in ollama._stream_response({
                "model": model_name,
                "prompt": final_prompt,
                "system": system_prompt or "Eres un asistente de IA útil",
                "stream": True
            }):
                full_response += chunk
                yield chunk
        else:
            # Usar OpenAI con streaming
            openai_client = get_openai_client()
            
            # Preparar mensajes en formato OpenAI
            messages = []
            
            # Añadir system prompt
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Añadir historial
            for msg in conversation_history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
            
            # Añadir contexto RAG
            if context_chunks:
                rag_content = "Contexto relevante:\n"
                for chunk in context_chunks:
                    rag_content += f"- {chunk['text']}\n"
                messages.append({"role": "system", "content": rag_content})
            
            # Añadir prompt actual
            messages.append({"role": "user", "content": prompt})
            
            # Llamar a OpenAI con streaming
            stream = await openai_client.chat.completions.create(
                model=model_name,
                messages=messages,
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
        cache_key = build_cache_key(
            key_type="query",
            resource_id=generate_hash(prompt),
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            collection_ids=collection_ids,
            conversation_id=conversation_id
        )
        await cache_set(cache_key, full_response, ttl=3600)
    
    # 7. Registrar mensaje en la memoria del agente
    await memory.add_message({
        "role": "assistant",
        "content": full_response,
        "timestamp": time.time(),
        "model": model_name,
        "tokens": len(full_response.split()),  # Estimación básica
        "message_id": str(uuid.uuid4())
    })
    
    # 8. Registrar uso de tokens
    from ..tracking.tokens import track_token_usage
    
    # Estimación básica de tokens
    input_tokens = len(final_prompt.split())
    output_tokens = len(full_response.split())
    
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=input_tokens + output_tokens,
        model=model_name,
        agent_id=agent_id,
        conversation_id=conversation_id
    )