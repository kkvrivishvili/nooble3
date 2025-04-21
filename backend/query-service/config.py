"""
Configuraciones específicas para el servicio de consultas.
"""

from typing import Dict, Any, Optional, List

from common.config import get_service_settings
from common.models import HealthResponse
from common.context import get_current_tenant_id

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

def get_collection_config(collection_id: str) -> Dict[str, Any]:
    """
    Obtiene la configuración específica para una colección.
    
    Args:
        collection_id: ID de la colección
        
    Returns:
        Dict[str, Any]: Configuración de la colección
    """
    # Obtener configuraciones por defecto
    settings = get_settings()
    
    # Configuración por defecto para cualquier colección
    default_config = {
        "similarity_top_k": settings.default_similarity_top_k,
        "response_mode": settings.default_response_mode,
        "similarity_threshold": settings.similarity_threshold,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }
    
    # En un sistema real, aquí podríamos obtener configuraciones 
    # específicas para cada colección desde la base de datos
    
    # Por ahora, solo devolvemos la configuración por defecto
    return default_config