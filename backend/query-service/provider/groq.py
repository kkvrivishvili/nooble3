"""
Integración con la API de Groq para LLMs.

Este módulo proporciona una implementación completa de la integración con Groq,
optimizada específicamente para el servicio de consultas.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
import asyncio

# Importaciones para tipos cuando se instala groq
try:
    from groq import AsyncGroq, Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Importación para contadores de tokens (mismo que usa el resto del servicio)
from common.llm.token_counters import count_tokens

logger = logging.getLogger(__name__)

# Modelos disponibles en Groq (actualizados según documentación oficial)
GROQ_MODELS = {
    # Modelos de producción actuales
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
    "llama-3.3-70b-versatile": {
        "context_window": 8192,
        "description": "Llama 3.3 70B Versatile (GroqCloud)",
        "default_max_tokens": 4096
    },
    "llama-3.1-8b-instant": {
        "context_window": 8192, 
        "description": "Llama 3.1 8B Instant (GroqCloud)",
        "default_max_tokens": 4096
    },
    "gemma-2-9b-it": {
        "context_window": 8192,
        "description": "Gemma 2 9B Instruction Tuned (GroqCloud)",
        "default_max_tokens": 4096
    }
}

# Importaciones para tipos de error estándar
from common.errors import ServiceError, ErrorCode

# Errores específicos para Groq que siguen el estándar del proyecto
class GroqError(ServiceError):
    """Error base para operaciones con Groq."""
    def __init__(self, message: str, code: str = ErrorCode.EXTERNAL_SERVICE_ERROR):
        super().__init__(message=message, code=code)

class GroqAuthenticationError(GroqError):
    """Error de autenticación con la API de Groq."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.AUTHORIZATION_ERROR)

class GroqRateLimitError(GroqError):
    """Error de límite de tasa con la API de Groq."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.RATE_LIMIT_EXCEEDED)

class GroqModelNotFoundError(GroqError):
    """Error cuando el modelo solicitado no está disponible."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.MODEL_NOT_FOUND_ERROR)

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
    
    # También verificar por prefijos de Groq (actualizados para nuevos formatos)
    groq_prefixes = ["llama3-", "llama-3", "mixtral-", "gemma-"]
    return any(model_name.startswith(prefix) for prefix in groq_prefixes)

def estimate_groq_tokens(text: str, model_name: str) -> int:
    """
    Estima el número de tokens en un texto para modelos de Groq.
    
    Args:
        text: Texto para estimar tokens
        model_name: Nombre del modelo para la estimación
        
    Returns:
        int: Número estimado de tokens
    """
    # Usar estimadores específicos según el modelo
    if "llama" in model_name.lower():
        return count_tokens(text, model="llama")
    elif "gemma" in model_name.lower():
        return count_tokens(text, model="gemma")
    else:
        # Fallback general
        return count_tokens(text)

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

class GroqLLM:
    """Implementación completa del cliente LLM para Groq."""
    
    def __init__(
        self, 
        model: str = "llama3-70b-8192", 
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
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        
        # Establecer max_tokens basado en el modelo o el valor por defecto
        model_info = GROQ_MODELS.get(model, {})
        self.max_tokens = max_tokens or model_info.get("default_max_tokens", 4096)
        
        # Otros parámetros por defecto para la API (con parámetros adicionales importantes)
        self.default_params = {
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "top_p": kwargs.get("top_p", 0.95),  # Control de diversidad
            "frequency_penalty": kwargs.get("frequency_penalty", 0),  # Penalización de repetición
            "presence_penalty": kwargs.get("presence_penalty", 0),  # Penalización de presencia
            **kwargs
        }
        
        # Inicializar clientes
        self._sync_client = None
        self._async_client = None
        
        # Nombre del modelo para propiedades
        self.model_name = model
    
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
            
        Raises:
            GroqAuthenticationError: Si hay problemas con la API key
            GroqRateLimitError: Si se excede el límite de tasa
            GroqModelNotFoundError: Si el modelo solicitado no existe
            GroqError: Para otros errores de Groq
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise GroqAuthenticationError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
        # Preparar mensajes
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Combinar parámetros por defecto con los proporcionados
        params = {**self.default_params, **kwargs}
        
        # Realizar la llamada a la API con manejo específico de errores
        try:
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                **params
            )
            return completion.choices[0].message.content
        except Exception as e:
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg:
                logger.error(f"Error de autenticación con Groq: {str(e)}")
                raise GroqAuthenticationError(f"Error de autenticación con Groq: {str(e)}")
            elif "rate limit" in error_msg:
                logger.error(f"Error de límite de tasa en Groq: {str(e)}")
                raise GroqRateLimitError(f"Se ha excedido el límite de tasa de Groq: {str(e)}")
            elif "model not found" in error_msg or "does not exist" in error_msg:
                logger.error(f"Modelo de Groq no encontrado: {self.model}")
                raise GroqModelNotFoundError(f"El modelo '{self.model}' no está disponible en Groq")
            else:
                logger.error(f"Error al llamar a la API de Groq: {str(e)}")
                raise GroqError(f"Error en la API de Groq: {str(e)}")
    
    async def stream_generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> AsyncGenerator[str, None]:
        """
        Genera una respuesta en streaming.
        
        Args:
            prompt: Texto del prompt
            system_prompt: Instrucción de sistema opcional
            **kwargs: Parámetros adicionales específicos del modelo
            
        Yields:
            str: Fragmentos de texto generados
            
        Raises:
            GroqAuthenticationError: Si hay problemas con la API key
            GroqRateLimitError: Si se excede el límite de tasa
            GroqModelNotFoundError: Si el modelo solicitado no existe
            GroqError: Para otros errores de Groq
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise GroqAuthenticationError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
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
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg:
                logger.error(f"Error de autenticación con Groq: {str(e)}")
                raise GroqAuthenticationError(f"Error de autenticación con Groq: {str(e)}")
            elif "rate limit" in error_msg:
                logger.error(f"Error de límite de tasa en Groq: {str(e)}")
                raise GroqRateLimitError(f"Se ha excedido el límite de tasa de Groq: {str(e)}")
            elif "model not found" in error_msg or "does not exist" in error_msg:
                logger.error(f"Modelo de Groq no encontrado: {self.model}")
                raise GroqModelNotFoundError(f"El modelo '{self.model}' no está disponible en Groq")
            else:
                logger.error(f"Error en streaming de Groq: {str(e)}")
                raise GroqError(f"Error en streaming de Groq: {str(e)}")
    
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Genera una respuesta basada en mensajes de chat.
        
        Args:
            messages: Lista de mensajes en formato {role, content}
            **kwargs: Parámetros adicionales específicos del modelo
            
        Returns:
            Dict[str, Any]: Respuesta generada con metadatos
            
        Raises:
            GroqAuthenticationError: Si hay problemas con la API key
            GroqRateLimitError: Si se excede el límite de tasa
            GroqModelNotFoundError: Si el modelo solicitado no existe
            GroqError: Para otros errores de Groq
        """
        # Verificar disponibilidad del cliente
        if not self.async_client:
            raise GroqAuthenticationError("No se pudo inicializar el cliente de Groq. Verifica tu API key.")
        
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
                    "total_tokens": input_tokens + output_tokens if input_tokens and output_tokens else None,
                    "finish_reason": completion.choices[0].finish_reason if hasattr(completion.choices[0], 'finish_reason') else None
                }
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg:
                logger.error(f"Error de autenticación con Groq: {str(e)}")
                raise GroqAuthenticationError(f"Error de autenticación con Groq: {str(e)}")
            elif "rate limit" in error_msg:
                logger.error(f"Error de límite de tasa en Groq: {str(e)}")
                raise GroqRateLimitError(f"Se ha excedido el límite de tasa de Groq: {str(e)}")
            elif "model not found" in error_msg or "does not exist" in error_msg:
                logger.error(f"Modelo de Groq no encontrado: {self.model}")
                raise GroqModelNotFoundError(f"El modelo '{self.model}' no está disponible en Groq")
            else:
                logger.error(f"Error en chat de Groq: {str(e)}")
                raise GroqError(f"Error en chat de Groq: {str(e)}")

# Funciones auxiliares para integración con el sistema
def get_groq_llm_model(model_name: str = "llama3-70b-8192", **kwargs) -> GroqLLM:
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
    model: str = "llama3-70b-8192",
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
        raise GroqAuthenticationError("No se pudo inicializar el cliente de Groq")
    
    # Parámetros por defecto
    params = {
        "temperature": kwargs.pop("temperature", 0.7),
        "max_tokens": kwargs.pop("max_tokens", 4096),
        "top_p": kwargs.pop("top_p", 0.95),
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
        error_msg = str(e).lower()
        if "api key" in error_msg or "authentication" in error_msg:
            logger.error(f"Error de autenticación con Groq: {str(e)}")
            raise GroqAuthenticationError(f"Error de autenticación con Groq: {str(e)}")
        elif "rate limit" in error_msg:
            logger.error(f"Error de límite de tasa en Groq: {str(e)}")
            raise GroqRateLimitError(f"Se ha excedido el límite de tasa de Groq: {str(e)}")
        elif "model not found" in error_msg or "does not exist" in error_msg:
            logger.error(f"Modelo de Groq no encontrado: {model}")
            raise GroqModelNotFoundError(f"El modelo '{model}' no está disponible en Groq")
        else:
            logger.error(f"Error en streaming de Groq: {str(e)}")
            raise GroqError(f"Error en streaming de Groq: {str(e)}")
