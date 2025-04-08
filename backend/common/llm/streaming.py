"""
Funciones para streaming de respuestas LLM.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

logger = logging.getLogger(__name__)

async def stream_openai_response(
    client,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    stream_handler: Optional[callable] = None
) -> AsyncGenerator[str, None]:
    """
    Genera una respuesta de OpenAI en streaming.
    
    Args:
        client: Cliente OpenAI
        messages: Lista de mensajes en formato OpenAI
        model: Nombre del modelo
        temperature: Temperatura de generación
        max_tokens: Límite de tokens
        stream_handler: Función opcional para manejar cada fragmento
        
    Yields:
        str: Fragmentos de texto del streaming
    """
    try:
        # Configurar parámetros de la solicitud
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # Iniciar streaming
        stream = await client.chat.completions.create(**request_params)
        
        # Procesar cada fragmento
        async for chunk in stream:
            if not chunk.choices:
                continue
                
            delta = chunk.choices[0].delta
            
            if delta.content is not None:
                # Llamar al manejador si existe
                if stream_handler:
                    await stream_handler(delta.content)
                
                # Devolver el fragmento
                yield delta.content
    except Exception as e:
        error_msg = f"Error en streaming OpenAI: {str(e)}"
        logger.error(error_msg)
        yield f"Error: {str(e)}"

async def stream_ollama_response(
    base_url: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    stop_sequences: Optional[List[str]] = None,
    stream_handler: Optional[callable] = None
) -> AsyncGenerator[str, None]:
    """
    Genera una respuesta de Ollama en streaming.
    
    Args:
        base_url: URL base de Ollama
        model: Nombre del modelo
        prompt: Prompt principal
        system_prompt: Prompt de sistema opcional
        temperature: Temperatura de generación
        max_tokens: Máximo de tokens a generar
        stop_sequences: Secuencias para detener generación
        stream_handler: Función opcional para manejar cada fragmento
        
    Yields:
        str: Fragmentos de texto del streaming
    """
    import httpx
    
    # Construir solicitud
    request_json = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": temperature
        }
    }
    
    if system_prompt:
        request_json["system"] = system_prompt
    
    if max_tokens:
        request_json["options"]["num_predict"] = max_tokens
    
    if stop_sequences:
        request_json["options"]["stop"] = stop_sequences
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{base_url}/api/generate", 
                                    json=request_json, timeout=60.0) as response:
                response.raise_for_status()
                
                # Procesar la respuesta línea por línea
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    
                    # Buscar líneas completas JSON
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if not line.strip():
                            continue
                            
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                token = data["response"]
                                
                                # Llamar al manejador si existe
                                if stream_handler:
                                    await stream_handler(token)
                                
                                # Devolver el token
                                yield token
                        except json.JSONDecodeError:
                            logger.warning(f"Error al decodificar JSON: {line}")
    except Exception as e:
        error_msg = f"Error en streaming Ollama: {str(e)}"
        logger.error(error_msg)
        yield f"Error: {str(e)}"