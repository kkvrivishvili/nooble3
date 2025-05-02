"""
Configuraciones para el servicio de ingestion.

Este módulo centraliza todas las configuraciones específicas del servicio
de ingestion, utilizando el patrón get_service_settings para obtener las
configuraciones específicas del servicio.
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from common.config import get_service_settings
from common.config.settings import Settings as CommonSettings
from common.models import HealthResponse, TenantInfo
from config.constants import (
    SUPPORTED_MIMETYPES,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_WORKERS,
    MAX_DOC_SIZE_MB,
    EXTRACTION_CONFIG,
    # Nuevas constantes para la cola de trabajos
    JOBS_QUEUE_KEY,
    MAX_QUEUE_SIZE,
    WORKER_CONCURRENCY
)

logger = logging.getLogger(__name__)

class IngestionSettings(CommonSettings):
    """
    Modelo de configuración específico para el servicio de ingestión.
    
    Extiende el modelo base de configuración común y añade campos
    específicos para el servicio de ingestión.
    """
    # Configuración de cola de trabajos
    jobs_queue_key: str = Field(JOBS_QUEUE_KEY, description="Clave para la cola de trabajos principal")
    max_queue_size: int = Field(MAX_QUEUE_SIZE, description="Tamaño máximo de la cola de trabajos")
    worker_concurrency: int = Field(WORKER_CONCURRENCY, description="Número de workers concurrentes")
    
    # Otras configuraciones específicas del servicio de ingestión
    # que podrían añadirse en el futuro


def get_settings(tenant_id: Optional[str] = None) -> IngestionSettings:
    """
    Obtiene la configuración para el servicio de ingestion.
    
    Esta función construye un objeto IngestionSettings basado en la
    configuración común pero con los campos específicos del servicio
    de ingestión.
    
    Args:
        tenant_id: ID opcional del tenant
        
    Returns:
        IngestionSettings: Configuración específica para el servicio de ingestión
    """
    # Obtener la configuración común
    common_settings = get_service_settings("ingestion-service", tenant_id=tenant_id)
    
    # Crear y devolver la configuración específica del servicio de ingestión
    # usando los valores de la configuración común como base
    return IngestionSettings(**common_settings.model_dump())

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de ingestion.
    
    Returns:
        HealthResponse: Estado de salud del servicio
    """
    settings = get_settings()
    
    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        status="available",
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
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_workers": MAX_WORKERS,
        "supported_mimetypes": SUPPORTED_MIMETYPES
    }

def get_extraction_config_for_mimetype(mimetype: str) -> Dict[str, Any]:
    """
    Obtiene la configuración de extracción para un tipo MIME específico.
    
    Args:
        mimetype: Tipo MIME del documento
    
    Returns:
        Dict[str, Any]: Configuración para extracción
    """
    mimetype = mimetype.lower()
    
    # Intentar obtener configuración exacta
    if mimetype in EXTRACTION_CONFIG:
        return EXTRACTION_CONFIG[mimetype]
    
    # Si no hay configuración exacta, buscar por tipo general
    for supported_type in EXTRACTION_CONFIG:
        if mimetype.startswith(supported_type.split('/')[0]):
            return EXTRACTION_CONFIG[supported_type]
    
    # Devolver configuración por defecto para texto plano si no hay coincidencia
    logger.warning(f"No se encontró configuración para mimetype: {mimetype}, usando configuración por defecto")
    return EXTRACTION_CONFIG["text/plain"]
