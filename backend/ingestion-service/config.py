"""
Configuraciones específicas para el servicio de ingesta.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_settings as get_common_settings
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de ingesta.
    
    Esta función extiende get_settings() de common con configuraciones
    específicas del servicio de ingesta.
    
    Returns:
        Settings: Configuración combinada
    """
    # Obtener configuración base
    settings = get_common_settings()
    
    # Agregar configuraciones específicas del servicio de ingesta
    settings.service_name = "ingestion-service"
    settings.service_version = os.getenv("SERVICE_VERSION", "1.0.0")
    
    # Configuración de procesamiento de documentos
    settings.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    settings.chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
    settings.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
    settings.supported_file_types = [
        "pdf", "txt", "docx", "csv", "xlsx", "md", "html", "pptx"
    ]
    settings.max_workers = int(os.getenv("MAX_WORKERS", "5"))
    settings.queue_ttl = int(os.getenv("QUEUE_TTL", "3600"))  # 1 hora por defecto
    
    return settings

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
        "supported_file_types": settings.supported_file_types,
        "max_file_size_mb": settings.max_file_size_mb
    }