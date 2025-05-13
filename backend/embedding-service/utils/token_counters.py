"""
Utilidades para el conteo preciso de tokens para embeddings.
Proporciona funciones para estimar tokens según diferentes modelos de embedding.
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
    logger.warning("tiktoken no está disponible, se usarán estimaciones aproximadas para el conteo de tokens de embeddings")

# Factores de estimación para diferentes tipos de modelos de embedding
EMBEDDING_TOKEN_ESTIMATION_FACTORS = {
    # OpenAI
    "text-embedding-3-small": 1.33,
    "text-embedding-3-large": 1.33,
    "text-embedding-ada-002": 1.33,
    # Otros modelos
    "default": 1.3
}

# Límites de contexto para modelos de embedding
EMBEDDING_MODEL_LIMITS = {
    "text-embedding-3-small": 8191,
    "text-embedding-3-large": 8191,
    "text-embedding-ada-002": 8191,
    "default": 8191
}

def count_embedding_tokens(text: str, model_name: str = "text-embedding-3-small") -> int:
    """
    Cuenta tokens para un texto según el modelo de embedding especificado.
    Usa tiktoken si está disponible para modelos compatibles.
    Para otros modelos o si tiktoken no está disponible, usa estimaciones.
    
    Args:
        text: Texto para contar tokens
        model_name: Nombre del modelo de embedding
        
    Returns:
        int: Número estimado de tokens
    """
    if not text:
        return 0
    
    try:
        # Si tiktoken está disponible, intentar usarlo
        if TIKTOKEN_AVAILABLE:
            try:
                # Para modelos de OpenAI, usar el encoding apropiado
                if "text-embedding-3" in model_name:
                    encoding = tiktoken.get_encoding("cl100k_base")
                elif "text-embedding-ada-002" in model_name:
                    encoding = tiktoken.get_encoding("cl100k_base")
                else:
                    # Para otros modelos, usar cl100k_base como aproximación razonable
                    encoding = tiktoken.get_encoding("cl100k_base")
                
                return len(encoding.encode(text))
            except Exception as tiktoken_err:
                logger.warning(f"Error usando tiktoken para {model_name}: {str(tiktoken_err)}")
                # Continuar con método de estimación
        
        # Estimación basada en caracteres y espacios
        # Determinar factor según el tipo de modelo
        factor = EMBEDDING_TOKEN_ESTIMATION_FACTORS.get("default", 1.3)
        for model_type, est_factor in EMBEDDING_TOKEN_ESTIMATION_FACTORS.items():
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
        logger.error(f"Error al contar tokens de embedding: {str(e)}")
        # Estimación conservadora en caso de error
        return max(1, len(text) // 4)

def estimate_embedding_tokens_batch(texts: List[str], model_name: str = "text-embedding-3-small") -> Dict[str, Any]:
    """
    Estima el número de tokens para un lote de textos para embeddings.
    
    Args:
        texts: Lista de textos
        model_name: Nombre del modelo de embedding
        
    Returns:
        Dict: Diccionario con tokens_total y detalle por texto
    """
    if not texts:
        return {"tokens_total": 0, "texts_count": 0, "token_counts": []}
    
    token_counts = []
    total_tokens = 0
    
    for text in texts:
        tokens = count_embedding_tokens(text, model_name)
        token_counts.append(tokens)
        total_tokens += tokens
    
    return {
        "tokens_total": total_tokens,
        "texts_count": len(texts),
        "token_counts": token_counts,
        "avg_tokens_per_text": total_tokens / len(texts) if texts else 0
    }

def check_embedding_context_limit(text: str, model_name: str = "text-embedding-3-small") -> Dict[str, Any]:
    """
    Verifica si un texto está dentro del límite de contexto para el modelo de embedding.
    
    Args:
        text: Texto a verificar
        model_name: Nombre del modelo de embedding
        
    Returns:
        Dict: Información sobre el conteo de tokens y límites
    """
    # Obtener límite para el modelo
    model_name_lower = model_name.lower()
    context_limit = EMBEDDING_MODEL_LIMITS.get("default", 8191)
    
    for model_key, limit in EMBEDDING_MODEL_LIMITS.items():
        if model_key in model_name_lower:
            context_limit = limit
            break
    
    # Contar tokens
    token_count = count_embedding_tokens(text, model_name)
    
    # Determinar si excede el límite
    exceeds_limit = token_count > context_limit
    
    return {
        "token_count": token_count,
        "context_limit": context_limit,
        "exceeds_limit": exceeds_limit,
        "model": model_name,
        "available_tokens": max(0, context_limit - token_count)
    }
