"""
Archivo de configuración legado para el servicio de embeddings.

Este archivo ahora redirecciona a la configuración centralizada en el paquete 'config'.
Se mantiene por compatibilidad con el código existente.
"""

from typing import Dict, Any, Optional, List

# Importar desde la configuración centralizada
from config.settings import get_settings, get_health_status
from config.constants import (
    EMBEDDING_DIMENSIONS,
    QUALITY_THRESHOLDS,
    CACHE_EFFICIENCY_THRESHOLDS,
    OLLAMA_API_ENDPOINTS,
    TIMEOUTS
)

# Mantener compatibilidad con importaciones del código existente
from common.config import (
    get_available_embedding_models,
    get_embedding_model_details
)

# La función get_health_status está importada desde config.settings

def get_model_details_for_tier(tier: str) -> Dict[str, Dict[str, Any]]:
    """
    Obtiene los detalles de los modelos de embeddings disponibles para un tier específico.
    
    Args:
        tier: Nivel de suscripción
        
    Returns:
        Dict[str, Dict[str, Any]]: Detalles de los modelos disponibles
    """
    # Obtener los modelos disponibles para este tier
    available_models = get_available_embedding_models(tier)
    
    # Obtener los detalles para cada modelo disponible
    model_details = {}
    for model_id in available_models:
        details = get_embedding_model_details(model_id)
        if details:  # Solo incluir si hay detalles disponibles
            model_details[model_id] = details
    
    return model_details