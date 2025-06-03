"""
Utilidades para la selección inteligente de modelos LLM.
Ayuda a elegir el modelo óptimo según el contexto, tier y requisitos.
"""
import logging
from typing import Optional, Dict, Any

from common.models import TenantInfo
from utils.token_counters import estimate_model_max_tokens
from config.constants import (
    DEFAULT_GROQ_MODEL,
    DEFAULT_GROQ_LLM_MODEL,
    GROQ_EXTENDED_CONTEXT_MODEL,
    GROQ_FAST_MODEL,
    GROQ_MAVERICK_MODEL,
    GROQ_SCOUT_MODEL
)

logger = logging.getLogger(__name__)

# Mapeo de tiers a modelos recomendados para diferentes escenarios
TIER_MODEL_MAPPING = {
    # Tiers empresariales
    "enterprise": {
        "default": GROQ_MAVERICK_MODEL,
        "fast": GROQ_SCOUT_MODEL,
        "extended_context": GROQ_EXTENDED_CONTEXT_MODEL
    },
    "business": {
        "default": GROQ_MAVERICK_MODEL,
        "fast": GROQ_SCOUT_MODEL,
        "extended_context": GROQ_EXTENDED_CONTEXT_MODEL
    },
    # Tier premium
    "premium": {
        "default": "llama-3.3-70b-versatile",
        "fast": GROQ_FAST_MODEL,
        "extended_context": GROQ_SCOUT_MODEL
    },
    # Tier standard
    "standard": {
        "default": "llama3-8b-8192",
        "fast": GROQ_FAST_MODEL,
        "extended_context": "llama3-8b-8192"
    },
    # Tier gratuito/básico
    "free": {
        "default": "llama3-8b-8192",
        "fast": "llama3-8b-8192",
        "extended_context": "llama3-8b-8192"
    }
}

def select_model_for_tenant(
    tenant_info: TenantInfo,
    requested_model: Optional[str] = None,
    context_size: Optional[int] = None,
    fast_response: bool = False
) -> str:
    """
    Selecciona el modelo LLM más adecuado según el tier del tenant y requisitos.
    
    Args:
        tenant_info: Información del tenant (incluye tier)
        requested_model: Modelo específicamente solicitado (opcional)
        context_size: Tamaño de contexto necesario (tokens)
        fast_response: Si es True, prioriza velocidad sobre calidad
        
    Returns:
        str: Nombre del modelo seleccionado
    """
    # Si hay un modelo específicamente solicitado, validarlo y usar ese
    if requested_model:
        # Verificar si el modelo tiene el contexto suficiente para la solicitud
        if context_size and context_size > estimate_model_max_tokens(requested_model):
            logger.warning(f"Modelo solicitado {requested_model} no tiene contexto suficiente ({context_size} tokens)")
            # Continuar con la selección automática
        else:
            return requested_model
    
    # Normalizar el tier y usar "free" como fallback
    tier = tenant_info.tier.lower() if tenant_info.tier else "free"
    if tier not in TIER_MODEL_MAPPING:
        tier = "free"
        
    # Obtener mapeo de modelos para el tier
    tier_models = TIER_MODEL_MAPPING.get(tier)
    
    # Seleccionar modelo según los requisitos
    if context_size and context_size > 8192:
        # Para contextos grandes, usar modelo con ventana extendida
        if context_size > 32768 and tier in ["enterprise", "business"]:
            return GROQ_EXTENDED_CONTEXT_MODEL  # 128K contexto
        return tier_models.get("extended_context")
    elif fast_response:
        # Priorizar velocidad
        return tier_models.get("fast")
    else:
        # Caso general: modelo por defecto para el tier
        return tier_models.get("default")

def get_model_capabilities(model_name: str) -> Dict[str, Any]:
    """
    Obtiene información sobre las capacidades del modelo.
    
    Args:
        model_name: Nombre del modelo
        
    Returns:
        Dict: Diccionario con información del modelo (contexto, velocidad, etc.)
    """
    context_window = estimate_model_max_tokens(model_name)
    
    # Determinar características del modelo
    is_fast = "instant" in model_name.lower() or "scout" in model_name.lower()
    quality_tier = "high" if ("70b" in model_name or "maverick" in model_name) else "standard"
    
    return {
        "model": model_name,
        "context_window": context_window,
        "is_fast_model": is_fast,
        "quality_tier": quality_tier,
        "max_output_tokens": min(4096, context_window // 2)  # Estimación conservadora
    }
