"""
Configuraciones específicas para el servicio de agentes.
"""

from typing import Dict, Any, Optional

from common.config import (
    get_service_settings,
)
from common.models import HealthResponse
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de agentes.
    
    Esta función utiliza get_service_settings() centralizada que ya incluye
    todas las configuraciones específicas para el servicio de agentes.
    
    Returns:
        Settings: Configuración para el servicio de agentes
    """
    # Usar la función centralizada que ya incluye las configuraciones específicas
    return get_service_settings("agent-service")

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de agentes.
    
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