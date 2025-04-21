"""
Configuraciones específicas para el servicio de ingesta.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_service_settings, get_tier_limits
from common.models import HealthResponse

def get_settings(tenant_id: Optional[str] = None):
    """
    Obtiene la configuración para el servicio de ingesta.
    
    Esta función utiliza get_service_settings() centralizada que ya incluye
    todas las configuraciones específicas para el servicio de ingesta.
    
    Args:
        tenant_id: ID opcional del tenant
        
    Returns:
        Settings: Configuración para el servicio de ingesta
    """
    # Usar la función centralizada que ya incluye las configuraciones específicas
    return get_service_settings("ingestion-service", tenant_id=tenant_id)

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de ingesta.
    
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

def get_document_processor_config() -> Dict[str, Any]:
    """
    Obtiene configuración para el procesador de documentos.
    
    Returns:
        Dict[str, Any]: Configuración para procesamiento de documentos
    """
    settings = get_settings()
    
    return {
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "max_workers": settings.max_workers,
        "supported_mimetypes": [
            "application/pdf",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/markdown",
            "text/html",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ]
    }

# Esta función se ha trasladado a services/extraction.py para evitar duplicación
# y mantener la configuración de extracción centralizada
from .services.extraction import get_extraction_config_for_mimetype