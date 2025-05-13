"""
Utilidades para el conteo preciso de tokens LLM.
Proporciona funciones para estimar tokens según diferentes modelos.
"""
import re
import traceback
from typing import List, Dict, Any, Optional, Union
import logging

from ..context.vars import get_full_context
from ..errors.exceptions import ServiceError, ErrorCode
from ..config.settings import get_settings

# Configurar logger
logger = logging.getLogger(__name__)

# Intentar importar tiktoken para conteo preciso
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken no está disponible, se usarán estimaciones aproximadas para el conteo de tokens")

# Cargar factores de conversión desde configuración centralizada
try:
    settings = get_settings()
    TOKEN_ESTIMATION_FACTORS = getattr(settings, "token_estimation_factors", {})
    # No definimos MODEL_TOKEN_LIMITS aquí, usamos la función helper para obtenerlo
    # Si no hay configuración disponible, usar valores predeterminados
    if not TOKEN_ESTIMATION_FACTORS:
        TOKEN_ESTIMATION_FACTORS = {
            # OpenAI
            "gpt-3.5-turbo": 1.33,
            "gpt-4": 1.33,
            "gpt-4-turbo": 1.33,
            # Embeddings
            "text-embedding-ada-002": 0.75,  # OBSOLETO: Modelo legacy de OpenAI
            "text-embedding-3-small": 0.75,
            "text-embedding-3-large": 0.75,
            # Anthropic
            "claude-instant": 1.45,
            "claude-2": 1.45,
            # Llama
            "llama2": 1.4,
            "llama3": 1.4,
            # Mistral
            "mistral": 1.4,
            # Qwen
            "qwen3:1.7b": 1.4,
            # Default para modelos desconocidos
            "default": 1.3
        }
except Exception as e:
    # Si no podemos cargar desde configuración, usar valores predeterminados
    logger.warning(f"No se pudieron cargar factores de token desde configuración: {str(e)}")
    # OpenAI y otros modelos populares
    TOKEN_ESTIMATION_FACTORS = {
        "gpt-3.5-turbo": 1.33,
        "gpt-4": 1.33,
        "gpt-4-turbo": 1.33,
        "text-embedding-ada-002": 0.75,  # OBSOLETO: Modelo legacy de OpenAI
        "text-embedding-3-small": 0.75,
        "text-embedding-3-large": 0.75,
        "claude-instant": 1.45,
        "claude-2": 1.45,
        "llama2": 1.4,
        "llama3": 1.4,
        "mistral": 1.4,
        "qwen3:1.7b": 1.4,
        "default": 1.3
    }

def estimate_max_tokens_for_model(model_name: str) -> int:
    """
    Estima el máximo de tokens para un modelo específico.
    
    Args:
        model_name: Nombre del modelo
        
    Returns:
        int: Número máximo de tokens que puede manejar el modelo
        
    Raises:
        ServiceError: Si hay un error al determinar el límite del modelo
    """
    error_context = {
        "function": "estimate_max_tokens_for_model",
        "model_name": model_name
    }
    error_context.update(get_full_context())
    
    try:
        model_name_lower = model_name.lower() if model_name else "default"
        
        # Búsqueda exacta primero
        settings = get_settings()
        MODEL_TOKEN_LIMITS = getattr(settings, "model_token_limits", {})
        if model_name_lower in MODEL_TOKEN_LIMITS:
            return MODEL_TOKEN_LIMITS[model_name_lower]
        
        # Búsqueda por coincidencia parcial si no se encuentra exacta
        for key, limit in MODEL_TOKEN_LIMITS.items():
            if key in model_name_lower:
                return limit
        
        # Si no se encuentra coincidencia, devolver el valor predeterminado
        logger.debug(f"No se encontró límite específico para modelo {model_name}, usando predeterminado", 
                    extra=error_context)
        return MODEL_TOKEN_LIMITS.get("default", 4096)
    except Exception as e:
        error_message = f"Error al estimar tokens máximos para modelo {model_name}: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        # Devolvemos un valor predeterminado conservador en caso de error
        return 4096

def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Cuenta tokens para un texto según el modelo especificado.
    Usa tiktoken para modelos OpenAI si está disponible.
    Para otros modelos o si tiktoken no está disponible, usa estimaciones.
    
    Args:
        text: Texto para contar tokens
        model_name: Nombre del modelo LLM
        
    Returns:
        int: Número estimado de tokens
        
    Raises:
        ServiceError: Si hay un error en el conteo de tokens y no se puede recuperar
    """
    error_context = {
        "function": "count_tokens",
        "model_name": model_name,
        "text_length": len(text) if text else 0
    }
    error_context.update(get_full_context())
    
    if not text:
        return 0
    
    try:
        # Si tiktoken está disponible y es un modelo OpenAI, usar conteo preciso
        if TIKTOKEN_AVAILABLE and ('gpt' in model_name.lower() or 'text-embedding' in model_name.lower()):
            try:
                # Mapear el modelo al encoding correcto
                if "gpt-3.5" in model_name:
                    encoding_name = "cl100k_base"
                elif "gpt-4" in model_name:
                    encoding_name = "cl100k_base"
                elif "text-embedding" in model_name:
                    encoding_name = "cl100k_base"
                else:
                    encoding_name = "cl100k_base"  # Valor por defecto para OpenAI
                
                # Crear encoder y contar tokens
                encoding = tiktoken.get_encoding(encoding_name)
                tokens = len(encoding.encode(text))
                return tokens
            except Exception as tiktoken_err:
                # Si hay error con tiktoken, caer en estimación
                logger.warning(f"Error usando tiktoken para {model_name}: {str(tiktoken_err)}", 
                              extra=error_context)
                # Continuar con método de estimación
        
        # Estimación basada en caracteres y espacios si tiktoken no está disponible
        # o para modelos no OpenAI
        factor = TOKEN_ESTIMATION_FACTORS.get(model_name.lower(), 
                                             TOKEN_ESTIMATION_FACTORS.get("default", 1.3))
        
        # Contar tokens basado en palabras y caracteres
        words = len(re.findall(r'\b\w+\b', text))
        chars = len(text)
        
        # Fórmula mejorada: palabras + factor * (caracteres / 4)
        estimated_tokens = int(words + factor * (chars / 4))
        
        return estimated_tokens
    except Exception as e:
        error_message = f"Error al contar tokens: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        # Estimación conservadora en caso de error
        try:
            # Intentar una estimación muy básica
            return len(text) // 4
        except:
            # Si todo falla, devolver un valor razonable
            return 100

def count_message_tokens(
    messages: List[Dict[str, str]], 
    model_name: str = "gpt-3.5-turbo"
) -> Dict[str, int]:
    """
    Cuenta tokens para una lista de mensajes de chat (formato ChatGPT).
    
    Args:
        messages: Lista de mensajes en formato {role, content}
        model_name: Nombre del modelo
        
    Returns:
        Dict[str, int]: Diccionario con tokens_in (prompt) y tokens_out (estimado para respuesta)
        
    Raises:
        ServiceError: Si hay un error en el conteo de tokens y no se puede recuperar
    """
    error_context = {
        "function": "count_message_tokens",
        "model_name": model_name,
        "messages_count": len(messages) if messages else 0
    }
    error_context.update(get_full_context())
    
    try:
        if not messages:
            return {"tokens_in": 0, "tokens_out": 0}
        
        total_tokens = 0
        
        # Verificar si podemos usar tiktoken para conteo preciso
        if TIKTOKEN_AVAILABLE and ('gpt' in model_name.lower()):
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                
                # Tokens base según el formato OpenAI
                tokens_per_message = 3  # Cada mensaje incluye <im_start>{role/name}\n{content}<im_end>\n
                tokens_per_name = 1  # Si hay un nombre, adicional a role
                
                for message in messages:
                    tokens = tokens_per_message
                    for key, value in message.items():
                        if key in ["role", "content", "name"]:
                            if value:
                                tokens += len(encoding.encode(value))
                                if key == "name":
                                    tokens += tokens_per_name
                    total_tokens += tokens
                
                # Tokens base de la respuesta
                total_tokens += 3  # Cada respuesta incluye <im_start>assistant\n
            except Exception as tiktoken_err:
                logger.warning(f"Error en tiktoken para mensajes: {str(tiktoken_err)}", 
                              extra=error_context)
                # Caer en método de estimación si falla tiktoken
                total_tokens = sum(count_tokens(msg.get("content", ""), model_name) for msg in messages)
        else:
            # Estimación para cada mensaje
            total_tokens = sum(count_tokens(msg.get("content", ""), model_name) for msg in messages)
        
        # Estimar tokens para la respuesta (aproximadamente 50% del prompt)
        estimated_response_tokens = max(50, int(total_tokens * 0.5))
        
        return {
            "tokens_in": total_tokens,
            "tokens_out": estimated_response_tokens
        }
    except Exception as e:
        error_message = f"Error al contar tokens de mensajes: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        
        # Intentar una estimación ultra conservadora en caso de error
        try:
            # Muy básico: contar caracteres totales y dividir
            total_chars = sum(len(msg.get("content", "")) for msg in messages)
            return {
                "tokens_in": total_chars // 4,
                "tokens_out": total_chars // 8
            }
        except:
            # Si todo falla, devolver valores razonables pero conservadores
            return {"tokens_in": 100, "tokens_out": 50}

def estimate_remaining_tokens(
    conversation_history: List[Dict[str, str]], 
    max_tokens: Optional[int] = None, 
    model_name: str = "gpt-3.5-turbo"
) -> int:
    """
    Estima cuántos tokens quedan disponibles basado en el historial de conversación
    y el límite del modelo.
    
    Args:
        conversation_history: Lista de mensajes de la conversación
        max_tokens: Límite personalizado (opcional)
        model_name: Nombre del modelo para el límite
        
    Returns:
        int: Número estimado de tokens disponibles
        
    Raises:
        ServiceError: Si hay un error en la estimación y no se puede recuperar
    """
    error_context = {
        "function": "estimate_remaining_tokens",
        "model_name": model_name,
        "custom_max_tokens": max_tokens is not None,
        "history_length": len(conversation_history) if conversation_history else 0
    }
    error_context.update(get_full_context())
    
    try:
        # Determinar el límite del modelo
        if max_tokens is None:
            max_tokens = estimate_max_tokens_for_model(model_name)
        
        # Contar tokens actuales en la conversación
        token_counts = count_message_tokens(conversation_history, model_name)
        current_tokens = token_counts["tokens_in"]
        
        # Considerar un margen de seguridad (10% del límite)
        safety_margin = int(max_tokens * 0.1)
        available_tokens = max(0, max_tokens - current_tokens - safety_margin)
        
        logger.debug(f"Tokens estimados para {model_name}: {current_tokens}/{max_tokens}, disponibles: {available_tokens}", 
                   extra=error_context)
        
        return available_tokens
    except Exception as e:
        error_message = f"Error al estimar tokens restantes: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        
        # En caso de error, devolver un valor conservador (25% del estimado del modelo)
        try:
            default_limit = estimate_max_tokens_for_model(model_name)
            return default_limit // 4
        except:
            # Si todo falla, valor fijo muy conservador
            return 1000