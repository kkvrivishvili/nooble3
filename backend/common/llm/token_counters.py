"""
Utilidades para el conteo preciso de tokens LLM.
Proporciona funciones para estimar tokens según diferentes modelos.
"""
import re
from typing import List, Dict, Any, Optional, Union
import logging

# Configurar logger
logger = logging.getLogger(__name__)

# Intentar importar tiktoken para conteo preciso
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken no está disponible, se usarán estimaciones aproximadas para el conteo de tokens")

# Factores de conversión aproximados para modelos que no tienen encoder específico
TOKEN_ESTIMATION_FACTORS = {
    # OpenAI
    "gpt-3.5-turbo": 1.33,
    "gpt-4": 1.33,
    "gpt-4-turbo": 1.33,
    # Embeddings
    "text-embedding-ada-002": 0.75,
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
    # Default para modelos desconocidos
    "default": 1.3
}

# Límites de tokens para diferentes modelos
MODEL_TOKEN_LIMITS = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "gpt-4-turbo": 16384,
    "llama3:7b": 8192,
    "llama3:8b": 8192,
    "llama3:70b": 8192,
    "llama3.1:8b": 8192,
    "llama3.1:70b": 8192,
    "claude-3-opus": 32768,
    "claude-3-sonnet": 16384,
    "claude-3-haiku": 8192,
    "mistral-7b": 8192,
    "mistral-8x7b": 32768,
    "gemma:2b": 8192,
    "gemma:7b": 8192,
    "gemma3:1b": 4096,
    "default": 4096  # Valor conservador por defecto
}

def estimate_max_tokens_for_model(model_name: str) -> int:
    """
    Estima el máximo de tokens para un modelo específico.
    
    Args:
        model_name: Nombre del modelo
        
    Returns:
        int: Número máximo de tokens que puede manejar el modelo
    """
    model_name_lower = model_name.lower()
    
    # Búsqueda exacta primero
    if model_name_lower in MODEL_TOKEN_LIMITS:
        return MODEL_TOKEN_LIMITS[model_name_lower]
    
    # Búsqueda por coincidencia parcial si no se encuentra exacta
    for key, limit in MODEL_TOKEN_LIMITS.items():
        if key in model_name_lower:
            return limit
    
    # Si no se encuentra coincidencia, devolver el valor predeterminado
    return MODEL_TOKEN_LIMITS["default"]

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
    """
    if not text:
        return 0
        
    # Normalizar nombre del modelo para búsquedas
    model_name_lower = model_name.lower()
    
    # Usar tiktoken para modelos OpenAI si está disponible
    if TIKTOKEN_AVAILABLE:
        try:
            # Modelos GPT
            if "gpt" in model_name_lower:
                encoding = tiktoken.encoding_for_model(model_name)
                return len(encoding.encode(text))
                
            # Embeddings de OpenAI
            elif "embedding" in model_name_lower:
                encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Error usando tiktoken para {model_name}: {str(e)}")
            # Continuar con estimación en caso de error
    
    # Estimación basada en factores predefinidos
    # Buscar factor más específico primero
    factor = None
    
    # Búsqueda exacta
    if model_name_lower in TOKEN_ESTIMATION_FACTORS:
        factor = TOKEN_ESTIMATION_FACTORS[model_name_lower]
    else:
        # Búsqueda por prefijo
        for model_prefix, model_factor in TOKEN_ESTIMATION_FACTORS.items():
            if model_name_lower.startswith(model_prefix):
                factor = model_factor
                break
    
    # Si no se encontró factor específico, usar default
    if factor is None:
        factor = TOKEN_ESTIMATION_FACTORS["default"]
    
    # Estimación basada en palabras
    word_count = len(re.findall(r'\S+', text))
    estimated_tokens = int(word_count * factor)
    
    return max(1, estimated_tokens)  # Al menos 1 token

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
    """
    if not messages:
        return {"tokens_in": 0, "tokens_out": 0}
    
    # Tokens fijos por mensaje según modelo GPT
    tokens_per_message = 4  # Valor por defecto
    tokens_per_name = 1  # Valor adicional si hay 'name' en el mensaje
    
    # Ajustar según modelo específico
    if "gpt-3.5-turbo" in model_name:
        tokens_per_message = 4
    elif "gpt-4" in model_name:
        tokens_per_message = 3
    
    # Contar tokens
    num_tokens = 0
    for message in messages:
        # Tokens base por mensaje
        num_tokens += tokens_per_message
        
        # Tokens por cada campo del mensaje
        for key, value in message.items():
            if isinstance(value, str):
                num_tokens += count_tokens(value, model_name)
                if key == "name":
                    num_tokens += tokens_per_name
    
    # Tokens de finalización
    num_tokens += 3  # Tokens finales para modelo GPT
    
    # Estimar tokens para la respuesta (aproximadamente 50% del input para conversaciones típicas)
    estimated_output = max(20, int(num_tokens * 0.5))
    
    return {
        "tokens_in": num_tokens,
        "tokens_out": estimated_output
    }

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
    """
    # Obtener límite del modelo
    if max_tokens is None:
        max_tokens = estimate_max_tokens_for_model(model_name)
    
    # Contar tokens actuales
    current_tokens = count_message_tokens(conversation_history, model_name)
    
    # Calcular tokens restantes (dejando margen para la respuesta)
    response_margin = max(150, int(max_tokens * 0.25))  # 25% del contexto o al menos 150 tokens
    remaining = max_tokens - current_tokens["tokens_in"] - response_margin
    
    return max(0, remaining)  # No devolver valores negativos