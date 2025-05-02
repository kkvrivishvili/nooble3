"""
Paquete de configuración para el servicio de ingestion.

Este paquete centraliza toda la configuración específica del servicio,
siguiendo el patrón de configuración unificado para todos los servicios.
"""

from config.settings import (
    get_settings, 
    get_health_status, 
    get_document_processor_config,
    get_extraction_config_for_mimetype
)
from config.constants import (
    # Configuración de fragmentación de documentos
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    
    # Configuración de procesamiento
    MAX_WORKERS,
    MAX_DOC_SIZE_MB,
    
    # Límites y timeouts
    MAX_QUEUE_RETRIES,
    MAX_EMBEDDING_RETRIES,
    PROCESSING_TIMEOUT,
    QUEUE_TIMEOUT,
    
    # Claves y límites para colas de trabajo
    JOBS_QUEUE_KEY,
    MAX_QUEUE_SIZE,
    WORKER_CONCURRENCY,
    
    # Configuración de modelos
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSION,
    
    # Tipos de archivo soportados
    SUPPORTED_MIMETYPES,
    EXTRACTION_CONFIG,
    
    # Métricas y umbrales
    CACHE_EFFICIENCY_THRESHOLDS,
    QUALITY_THRESHOLDS,
    TIME_INTERVALS,
    METRICS_CONFIG,
    TIMEOUTS
)

# Exportar todo lo necesario para facilitar el uso en otros módulos
__all__ = [
    # Funciones de configuración
    "get_settings",
    "get_health_status",
    "get_document_processor_config",
    "get_extraction_config_for_mimetype",
    
    # Configuración de fragmentación de documentos
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    
    # Configuración de procesamiento
    "MAX_WORKERS",
    "MAX_DOC_SIZE_MB",
    
    # Límites y timeouts
    "MAX_QUEUE_RETRIES",
    "MAX_EMBEDDING_RETRIES",
    "PROCESSING_TIMEOUT",
    "QUEUE_TIMEOUT",
    
    # Claves y límites para colas de trabajo
    "JOBS_QUEUE_KEY",
    "MAX_QUEUE_SIZE",
    "WORKER_CONCURRENCY",
    
    # Configuración de modelos
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSION",
    
    # Tipos de archivo soportados
    "SUPPORTED_MIMETYPES",
    "EXTRACTION_CONFIG",
    
    # Métricas y umbrales
    "CACHE_EFFICIENCY_THRESHOLDS",
    "QUALITY_THRESHOLDS",
    "TIME_INTERVALS",
    "METRICS_CONFIG",
    "TIMEOUTS"
]
