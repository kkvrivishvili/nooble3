"""
Integración con la API de Groq para LLMs.
"""

import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
import asyncio
import os

# Importaciones para tipos cuando se instala groq
try:
    from groq import AsyncGroq, Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

from .base import BaseLLM, BaseEmbeddingModel
from .token_counters import count_tokens

logger = logging.getLogger(__name__)

# Modelos disponibles en Groq
GROQ_MODELS = {
    "llama3-8b-8192": {
        "context_window": 8192,
        "description": "Llama 3 8B (GroqCloud)",
        "default_max_tokens": 4096
    },
    "llama3-70b-8192": {
        "context_window": 8192,
        "description": "Llama 3 70B (GroqCloud)",
        "default_max_tokens": 4096
    },
    "llama3-1-8b-8192": {
        "context_window": 8192,
        "description": "Llama 3.1 8B (GroqCloud)",
        "default_max_tokens": 4096
    },
    "llama3-1-70b-8192": {
        "context_window": 8192,
        "description": "Llama 3.1 70B (GroqCloud)",
        "default_max_tokens": 4096
    },
    "mixtral-8x7b-32768": {
        "context_window": 32768,
        "description": "Mixtral 8x7B (GroqCloud)",
        "default_max_tokens": 8192
    },
    "gemma-7b-it": {
        "context_window": 8192,
        "description": "Gemma 7B (GroqCloud)",
        "default_max_tokens": 4096
    }
}

def is_groq_model(model_name: str) -> bool:
    """
    Determina si un nombre de modelo corresponde a un modelo de Groq.
    
    Args:
        model_name: Nombre del modelo a verificar
        
    Returns:
        bool: True si es un modelo de Groq, False en caso contrario
    """
    # Verificar si el modelo está en la lista de modelos Groq
    if model_name in GROQ_MODELS:
        return True
    
    # También verificar por prefijos de Groq
    groq_prefixes = ["llama3-", "mixtral-", "gemma-"]
    return any(model_name.startswith(prefix) for prefix in groq_prefixes)

def get_groq_client(api_key: Optional[str] = None) -> Union['Groq', None]:
    """
    Obtiene un cliente de Groq.
    
    Args:
        api_key: API key de Groq (opcional, usa la variable de entorno GROQ_API_KEY por defecto)
        
    Returns:
        Groq: Cliente de Groq o None si no está disponible
    """
    if not GROQ_AVAILABLE:
        logger.warning("La biblioteca de Groq no está instalada. Ejecuta 'pip install groq' para instalar.")
        return None
    
    # Usar la API key proporcionada o la de entorno
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    
    if not api_key:
        logger.warning("No se encontró GROQ_API_KEY en las variables de entorno")
        return None
    
    return Groq(api_key=api_key)

def get_async_groq_client(api_key: Optional[str] = None) -> Union['AsyncGroq', None]:
    """
    Obtiene un cliente asíncrono de Groq.
    
    Args:
        api_key: API key de Groq (opcional, usa la variable de entorno GROQ_API_KEY por defecto)
        
    Returns:
        AsyncGroq: Cliente asíncrono de Groq o None si no está disponible
    """
    if not GROQ_AVAILABLE:
        logger.warning("La biblioteca de Groq no está instalada. Ejecuta 'pip install groq' para instalar.")
        return None
    
    # Usar la API key proporcionada o la de entorno
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    
    if not api_key:
        logger.warning("No se encontró GROQ_API_KEY en las variables de entorno")
        return None
    
    return AsyncGroq(api_key=api_key)

class GroqLLM(BaseLLM):
    """Implementación de BaseLLM para Groq."""
    
    def __init__(
        self, 
        model: str = "llama3-8b-8192", 
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Inicializa el modelo LLM de Groq.
        
        Args:
            model: Nombre del modelo a utilizar
            api_key: API key de Groq (opcional)
            temperature: Temperatura para la generación (0.0-1.0)
            max_tokens: Número máximo de tokens a generar
            **kwargs: Argumentos adicionales para la API de Groq
        """
        super().__init__()
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        
        # Establecer max_tokens basado en el modelo o el valor por defecto
        model_info = GROQ_MODELS.get(model, {})
        self.max_tokens = max_tokens or model_info.get("default_max_tokens", 4096)
        
        # Otros parámetros por defecto para la API
        self.default_params = {
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            **kwargs
        }
        
        # Inicializar clientes
        self._sync_client = None
        self._async_client = None
    
    @property
    def sync_client(self):
        """Obtiene el cliente sincrónico, inicializándolo si es necesario."""
        if not self._sync_client:
            self._sync_client = get_groq_client(self.api_key)
        return self._sync_client
    
    @property
    def async_client(self):
        """Obtiene el cliente asincrónico, inicializándolo si es necesario."""
        if not self._async_client:
            self._async_client = get_async_groq_client(self.api_key)
        return self._async_client
    
    async def predict(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """
        Genera una respuesta para un prompt.
        
        Args:
            prompt: Texto del prompt
            system_prompt: Instrucción de sistema opcional
            **kwargs: Parámetros adicionales específicos del modelo
            
        Returns:
            str: Texto generado
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise ValueError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
        # Preparar mensajes
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Combinar parámetros por defecto con los proporcionados
        params = {**self.default_params, **kwargs}
        
        # Realizar la llamada a la API
        try:
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                **params
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error al llamar a la API de Groq: {str(e)}")
            raise
    
    async def stream_generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> AsyncGenerator[str, None]:
        """
        Genera una respuesta en streaming.
        
        Args:
            prompt: Texto del prompt
            system_prompt: Instrucción de sistema opcional
            **kwargs: Parámetros adicionales específicos del modelo
            
        Yields:
            str: Fragmentos de texto generados
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise ValueError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
        # Preparar mensajes
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Combinar parámetros por defecto con los proporcionados y activar streaming
        params = {**self.default_params, **kwargs, "stream": True}
        
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                **params
            )
            
            async for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        except Exception as e:
            logger.error(f"Error en streaming de Groq: {str(e)}")
            raise
    
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Genera una respuesta basada en mensajes de chat.
        
        Args:
            messages: Lista de mensajes en formato {role, content}
            **kwargs: Parámetros adicionales específicos del modelo
            
        Returns:
            Dict[str, Any]: Respuesta generada con metadatos
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise ValueError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
        # Combinar parámetros por defecto con los proporcionados
        params = {**self.default_params, **kwargs}
        
        try:
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                **params
            )
            
            # Construir respuesta estructurada
            response_content = completion.choices[0].message.content
            
            # Calcular tokens si es posible
            input_tokens = completion.usage.prompt_tokens if hasattr(completion, 'usage') else None
            output_tokens = completion.usage.completion_tokens if hasattr(completion, 'usage') else None
            
            return {
                "content": response_content,
                "metadata": {
                    "model": self.model,
                    "provider": "groq",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "finish_reason": completion.choices[0].finish_reason if hasattr(completion.choices[0], 'finish_reason') else None
                }
            }
        except Exception as e:
            logger.error(f"Error en chat de Groq: {str(e)}")
            raise

# Funciones auxiliares para integración con el sistema
def get_groq_llm_model(model_name: str = "llama3-8b-8192", **kwargs) -> GroqLLM:
    """
    Obtiene un modelo LLM de Groq configurado.
    
    Args:
        model_name: Nombre del modelo a utilizar
        **kwargs: Parámetros adicionales para el modelo
        
    Returns:
        GroqLLM: Instancia configurada del modelo
    """
    return GroqLLM(model=model_name, **kwargs)

async def stream_groq_response(
    messages: List[Dict[str, str]],
    model: str = "llama3-8b-8192",
    api_key: Optional[str] = None,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Genera una respuesta en streaming desde Groq.
    
    Args:
        messages: Lista de mensajes en formato {role, content}
        model: Nombre del modelo a utilizar
        api_key: API key de Groq (opcional)
        **kwargs: Parámetros adicionales para la API
        
    Yields:
        str: Fragmentos de texto generados
    """
    # Inicializar cliente
    client = get_async_groq_client(api_key)
    if not client:
        raise ValueError("No se pudo inicializar el cliente de Groq")
    
    # Parámetros por defecto
    params = {
        "temperature": kwargs.pop("temperature", 0.7),
        "max_tokens": kwargs.pop("max_tokens", 4096),
        "stream": True,
        **kwargs
    }
    
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            **params
        )
        
        async for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        logger.error(f"Error en streaming de Groq: {str(e)}")
        raise
