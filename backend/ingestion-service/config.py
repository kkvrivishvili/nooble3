"""
Configuraciones específicas para el servicio de ingesta.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_settings as get_common_settings
from common.config.tiers import get_tier_limits

class IngestionConfig:
    """
    Configuración centralizada para el servicio de ingesta.
    """
    def __init__(self):
        # Configuración base
        self.service_name = "ingestion-service"
        self.service_version = os.getenv("SERVICE_VERSION", "1.0.0")
        
        # Límites de archivos
        self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        self.supported_file_types = [
            "pdf", "txt", "docx", "csv", "xlsx", "md", "html", "pptx"
        ]
        
        # Procesamiento paralelo
        self.max_workers = int(os.getenv("MAX_WORKERS", "3"))
        self.job_timeout_seconds = int(os.getenv("JOB_TIMEOUT_SECONDS", "3600"))
        
        # Manejo de errores
        self.max_retries = int(os.getenv("MAX_RETRIES", "3"))
        self.retry_backoff_base = float(os.getenv("RETRY_BACKOFF_BASE", "2.0"))
        
        # NOTA: Se eliminó storage_path (os.getenv("STORAGE_PATH", "documents"))
        # ya que no se utiliza en el código actual. Si se necesita almacenamiento
        # local en el futuro, se debe implementar siguiendo el patrón común.config
        
        # Chunking
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
        
        # Cola
        self.queue_ttl = int(os.getenv("QUEUE_TTL", "3600"))  # 1 hora

# Instancia global de configuración
ingestion_config = IngestionConfig()

def get_settings(tenant_id: Optional[str] = None):
    """
    Obtiene configuración combinada (common + ingestion).
    
    Args:
        tenant_id: ID del tenant para obtener configuraciones específicas
        
    Returns:
        Objeto con configuración combinada de ingestion y common
    """
    # Obtener configuración base desde common
    common_settings = get_common_settings(tenant_id)
    
    # Combinar ambas configuraciones en un solo objeto
    # primero configuraciones de common, luego específicas de ingestion
    settings = common_settings
    
    # Añadir las configuraciones específicas del servicio de ingesta
    # como atributos adicionales
    settings.ingestion = ingestion_config
    
    return settings

# Esta función se ha trasladado a services/extraction.py para evitar duplicación
# y mantener la configuración de extracción centralizada
from .services.extraction import get_extraction_config_for_mimetype

def get_document_processor_config() -> Dict[str, Any]:
    """
    Obtiene configuración para el procesador de documentos.
    
    Returns:
        Dict[str, Any]: Configuración para procesamiento de documentos
    """
    return {
        "chunk_size": ingestion_config.chunk_size,
        "chunk_overlap": ingestion_config.chunk_overlap,
        "max_file_size_mb": ingestion_config.max_file_size_mb,
        "supported_file_types": ingestion_config.supported_file_types
    }