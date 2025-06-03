"""
Configuraciones específicas para el servicio de consultas.

Este módulo implementa la configuración específica del servicio de consultas
utilizando el sistema centralizado de configuración, separando las configuraciones
específicas del servicio de las configuraciones globales.
"""

from typing import Dict, Any, Optional, List
from pydantic import Field, BaseModel

from common.config import get_service_settings
from common.models import HealthResponse
from common.context import Context

def get_settings():
    """
    Obtiene la configuración específica para el servicio de consultas.
    
    Esta función utiliza get_service_settings() centralizada que ya incluye
    todas las configuraciones específicas para el servicio de consultas.
    
    Returns:
        Settings: Configuración para el servicio de consultas
    """
    # Usar la función centralizada que ya incluye las configuraciones específicas
    return get_service_settings("query-service")

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de consultas.
    
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

# Nota: La función get_collection_config se ha eliminado ya que no se utilizaba
# y hemos migrado a un sistema de configuración centralizada en common/

# Si se necesita obtener configuraciones específicas para colecciones,
# utilizar el nuevo sistema de configuración centralizada que proporciona
# métodos estandarizados para todos los servicios.
