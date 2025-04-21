"""
Configuraciones específicas para el servicio de embeddings.
"""

from typing import Dict, Any, Optional, List

from common.config import (
    get_service_settings,
    get_available_embedding_models,
    get_embedding_model_details
)
from common.models import HealthResponse
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de embeddings.
    
    Esta función utiliza get_service_settings() centralizada que ya incluye
    todas las configuraciones específicas para el servicio de embeddings.
    
    Returns:
        Settings: Configuración para el servicio de embeddings
    """
    # Usar la función centralizada que ya incluye las configuraciones específicas
    return get_service_settings("embedding-service")

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de embeddings.
    
    Returns:
        HealthResponse: Estado de salud del servicio
    """
    settings = get_settings()
    
    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        status="healthy",
        timestamp=None  # Se generará automáticamente
    )

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