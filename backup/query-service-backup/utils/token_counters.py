"""
Utilidades para el conteo preciso de tokens LLM.
Proporciona funciones para estimar tokens según diferentes modelos.
"""
import re
import logging
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Intentar importar tiktoken para conteo preciso
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken no está disponible, se usarán estimaciones aproximadas para el conteo de tokens")

# Factores de estimación para diferentes tipos de modelos
TOKEN_ESTIMATION_FACTORS = {
    # OpenAI
    "gpt-3.5-turbo": 1.33,
    "gpt-4": 1.33,
    # Llama
    "llama3": 1.4,
    "llama-3": 1.4,
    "llama-4": 1.4,
    # Gemma
    "gemma": 1.4,
    # Default para modelos desconocidos
    "default": 1.3
}

def count_tokens(text: str, model_name: str = "llama3-70b-8192") -> int:
    """
    Cuenta tokens para un texto según el modelo especificado.
    Usa tiktoken si está disponible para modelos compatibles.
    Para otros modelos o si tiktoken no está disponible, usa estimaciones.
    
    Args:
        text: Texto para contar tokens
        model_name: Nombre del modelo LLM
        
    Returns:
        int: Número estimado de tokens
    """
    if not text:
        return 0
    
    try:
        # Si tiktoken está disponible, intentar usarlo
        if TIKTOKEN_AVAILABLE:
            try:
                # Para modelos Llama, Gemma y similares, cl100k_base es una aproximación razonable
                encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            except Exception as tiktoken_err:
                logger.warning(f"Error usando tiktoken para {model_name}: {str(tiktoken_err)}")
                # Continuar con método de estimación
        
        # Estimación basada en caracteres y espacios
        # Determinar factor según el tipo de modelo
        factor = TOKEN_ESTIMATION_FACTORS.get("default", 1.3)
        for model_type, est_factor in TOKEN_ESTIMATION_FACTORS.items():
            if model_type in model_name.lower():
                factor = est_factor
                break
        
        # Contar tokens basado en palabras y caracteres
        words = len(re.findall(r'\b\w+\b', text))
        chars = len(text)
        
        # Fórmula mejorada: palabras + factor * (caracteres / 4)
        estimated_tokens = int(words + factor * (chars / 4))
        
        return estimated_tokens
    except Exception as e:
        logger.error(f"Error al contar tokens: {str(e)}")
        # Estimación conservadora en caso de error
        return max(1, len(text) // 4)

def count_message_tokens(
    messages: List[Dict[str, str]], 
    model_name: str = "llama3-70b-8192"
) -> Dict[str, int]:
    """
    Cuenta tokens para una lista de mensajes de chat (formato ChatGPT).
    
    Args:
        messages: Lista de mensajes en formato {role, content}
        model_name: Nombre del modelo
        
    Returns:
        Dict[str, int]: Diccionario con tokens_in (prompt) y tokens_out (estimado para respuesta)
    """
    try:
        if not messages:
            return {"tokens_in": 0, "tokens_out": 0}
        
        total_tokens = 0
        
        # Verificar si podemos usar tiktoken para conteo preciso
        if TIKTOKEN_AVAILABLE:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                
                # Tokens base según el formato de mensaje estándar
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
                logger.warning(f"Error en tiktoken para mensajes: {str(tiktoken_err)}")
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
        logger.error(f"Error al contar tokens de mensajes: {str(e)}")
        
        # Estimación ultra conservadora en caso de error
        try:
            total_chars = sum(len(msg.get("content", "")) for msg in messages)
            return {
                "tokens_in": total_chars // 4,
                "tokens_out": total_chars // 8
            }
        except:
            # Si todo falla, devolver valores razonables pero conservadores
            return {"tokens_in": 100, "tokens_out": 50}

def estimate_model_max_tokens(model_name: str) -> int:
    """
    Estima el máximo de tokens para un modelo específico de Groq.
    
    Args:
        model_name: Nombre del modelo
        
    Returns:
        int: Número máximo de tokens que puede manejar el modelo
    """
    # Mapeo de modelos a sus límites de contexto
    model_token_limits = {
        # Llama 3 original
        "llama3-8b-8192": 8192,
        "llama3-70b-8192": 8192,
        # Llama 3.1 y 3.3
        "llama-3.1-8b-instant": 8192,
        "llama-3.3-70b-versatile": 8192,
        # Llama 3.1 128k
        "llama-3.1-8b-instant-128k": 128000,
        # Llama 4
        "llama-4-maverick-17bx128e": 32768,
        "llama-4-scout-17bx16e": 32768,
        # Gemma
        "gemma-2-9b-it": 8192,
        # Valor predeterminado
        "default": 8192
    }
    
    model_name_lower = model_name.lower() if model_name else "default"
    
    # Búsqueda exacta primero
    if model_name_lower in model_token_limits:
        return model_token_limits[model_name_lower]
    
    # Búsqueda por coincidencia parcial
    for key, limit in model_token_limits.items():
        if key in model_name_lower:
            return limit
    
    # Valor por defecto si no se encuentra ninguna coincidencia
    logger.debug(f"No se encontró límite específico para modelo {model_name}, usando predeterminado")
    return model_token_limits["default"]
