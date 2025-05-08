"""
Constantes específicas para el servicio de ingestion.

Este módulo centraliza todas las constantes y configuraciones específicas
del servicio de ingestion, separándolas de la configuración global.
"""

# Configuración de fragmentación de documentos
CHUNK_SIZE = 512    # Alineado con el valor en common config
CHUNK_OVERLAP = 51  # Alineado con el valor en common config

# Configuración de procesamiento
MAX_WORKERS = 4       # Máximo de workers para procesamiento simultáneo
MAX_DOC_SIZE_MB = 10  # Tamaño máximo de documentos (MB)

# Límites y timeouts
MAX_QUEUE_RETRIES = 3  # Máximo de reintentos para operaciones de cola
MAX_EMBEDDING_RETRIES = 3  # Máximo de reintentos para generación de embeddings
PROCESSING_TIMEOUT = 600  # Timeout para procesamiento de documentos (segundos)
QUEUE_TIMEOUT = 30  # Timeout para operaciones de cola (segundos)

# Claves para colas de trabajo
JOBS_QUEUE_KEY = "ingestion:jobs"  # Clave para la cola de trabajos principal
MAX_QUEUE_SIZE = 1000  # Tamaño máximo de la cola de trabajos
WORKER_CONCURRENCY = MAX_WORKERS  # Número de workers concurrentes

# Configuración de modelos
# OpenAI
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"  # Modelo de embedding predeterminado para OpenAI

# Ollama
DEFAULT_OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"  # Modelo de embedding predeterminado para Ollama

# Groq
DEFAULT_GROQ_MODEL = "llama3-70b-8192"  # Modelo predeterminado para Groq

# Dimensiones de embeddings según modelo
DEFAULT_EMBEDDING_DIMENSION = 1536  # Dimensión de embedding predeterminada

# Tipos de archivo soportados
SUPPORTED_MIMETYPES = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/markdown",
    "text/html",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
]

# Configuración para extracción de diferentes tipos de archivo
EXTRACTION_CONFIG = {
    "application/pdf": {
        "reader_class": "PDFReader",
        "extraction_params": {
            "metadata_extraction": True
        }
    },
    "text/plain": {
        "reader_class": "SimpleDirectoryReader",
        "extraction_params": {}
    },
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "reader_class": "DocxReader",
        "extraction_params": {}
    },
    "text/csv": {
        "reader_class": "CSVReader",
        "extraction_params": {
            "concat_rows": True
        }
    },
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "reader_class": "PandasExcelReader",
        "extraction_params": {}
    },
    "text/markdown": {
        "reader_class": "MarkdownReader",
        "extraction_params": {}
    },
    "text/html": {
        "reader_class": "CustomHTMLReader",
        "extraction_params": {
            "remove_scripts": True
        }
    }
}

# Parámetros para eficiencia de caché y rendimiento
CACHE_EFFICIENCY_THRESHOLDS = {
    "excellent": 0.8,  # 80% o más de hit ratio es excelente
    "good": 0.6,       # 60-80% hit ratio es bueno
    "acceptable": 0.4, # 40-60% hit ratio es aceptable
    "poor": 0.2        # Menos de 20% hit ratio es pobre
}

# Umbrales de calidad para verificaciones de salud
QUALITY_THRESHOLDS = {
    "processing_time_seconds": {
        "excellent": 5,    # Menos de 5s es excelente
        "good": 10,        # 5-10s es bueno
        "acceptable": 20,  # 10-20s es aceptable
        "poor": 30         # Más de 30s es pobre
    },
    "queue_latency_seconds": {
        "excellent": 1,
        "good": 2,
        "acceptable": 5,
        "poor": 10
    }
}

# Intervalos de tiempo para diversas operaciones
TIME_INTERVALS = {
    "job_check_interval": 10,   # 10 segundos entre chequeos de estado de jobs
    "cache_refresh": 3600,      # 1 hora
    "metrics_retention": 86400, # 24 horas
    "status_check_timeout": 2   # 2 segundos para health checks
}

# Configuración de métricas
METRICS_CONFIG = {
    "max_samples": 100,         # Máximas muestras para cálculo de métricas
    "processing_threshold_s": 20,    # Umbral para tiempo de procesamiento aceptable
    "cache_hit_ratio_threshold": 0.6  # Umbral mínimo de hit ratio en caché
}

# Timeouts para diversas operaciones
TIMEOUTS = {
    "embedding_service": 10,    # 10 segundos para llamadas al servicio de embeddings
    "storage_operation": 15,    # 15 segundos para operaciones de almacenamiento
    "document_extraction": 30,  # 30 segundos para extracción de documentos
    "queue_operation": 5,       # 5 segundos para operaciones de cola
    "health_check": 1           # 1 segundo para health checks básicos
}
