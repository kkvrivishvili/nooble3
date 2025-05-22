"""
Cliente Groq simplificado.
"""

import logging
from typing import Optional, AsyncGenerator, List, Dict, Any
from groq import AsyncGroq, Groq

from common.errors import ServiceError
from config.settings import get_settings, GROQ_MODELS

logger = logging.getLogger(__name__)
settings = get_settings()

# Clientes globales
_sync_client: Optional[Groq] = None
_async_client: Optional[AsyncGroq] = None

def get_groq_client(api_key: Optional[str] = None) -> Groq:
    """Cliente sincrónico singleton."""
    global _sync_client
    if not _sync_client:
        key = api_key or settings.groq_api_key
        if not key:
            raise ServiceError("Groq API key no configurada")
        _sync_client = Groq(api_key=key)
    return _sync_client

def get_async_groq_client(api_key: Optional[str] = None) -> AsyncGroq:
    """Cliente asincrónico singleton."""
    global _async_client
    if not _async_client:
        key = api_key or settings.groq_api_key
        if not key:
            raise ServiceError("Groq API key no configurada")
        _async_client = AsyncGroq(api_key=key)
    return _async_client

class GroqLLM:
    """Cliente simplificado para Groq."""
    
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.default_groq_model
        self.client = get_async_groq_client()
        
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """Genera respuesta simple."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens
        )
        
        return response.choices[0].message.content
    
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Genera respuesta en streaming."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
