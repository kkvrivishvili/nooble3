"""
Configuraciones específicas para el servicio de ingesta.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_settings as get_common_settings

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
        
        # Almacenamiento
        self.storage_path = os.getenv("STORAGE_PATH", "documents")
        
        # Chunking
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
        
        # Cola
        self.queue_ttl = int(os.getenv("QUEUE_TTL", "3600"))  # 1 hora

# Instancia global de configuración
ingestion_config = IngestionConfig()

def get_settings():
    """
    Obtiene configuración combinada (common + ingestion).
    Mantenido por compatibilidad.
    """
    settings = get_common_settings()
    
    # Merge con configuración de ingesta
    for attr, value in vars(ingestion_config).items():
        setattr(settings, attr, value)
    
    return settings

def get_extraction_config_for_mimetype(mimetype: str) -> Dict[str, Any]:
    """
    Obtiene configuración específica para tipo MIME.
    """
    extraction_configs = {
        "application/pdf": {
            "pdf_parser": "pdfminer",
            "ocr_enabled": False
        },
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
            "extract_headers": True,
            "extract_tables": True
        },
        # Otras configuraciones por tipo MIME
    }
    
    # Buscar por prefijo de MIME
    for mime_pattern, config in extraction_configs.items():
        if mime_pattern in mimetype:
            return config
    
    return {"default_parser": "text"}

def get_document_processor_config() -> Dict[str, Any]:
    """
    Obtiene configuración para el procesador de documentos.
    
    Returns:
        Dict[str, Any]: Configuración para procesamiento de documentos
    """
    return {
        "chunk_size": ingestion_config.chunk_size,
        "chunk_overlap": ingestion_config.chunk_overlap,
        "supported_file_types": ingestion_config.supported_file_types,
        "max_file_size_mb": ingestion_config.max_file_size_mb
    }