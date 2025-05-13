"""
Constantes específicas para el servicio de consultas.

Este módulo centraliza todas las constantes y configuraciones específicas
del servicio de consultas, separándolas de la configuración global.
"""

# Configuración de consultas LLM
LLM_DEFAULT_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 2048
DEFAULT_SIMILARITY_TOP_K = 4
MAX_SIMILARITY_TOP_K = 10
DEFAULT_RESPONSE_MODE = "compact"
SIMILARITY_THRESHOLD = 0.7

# Configuración de fragmentación de documentos
# Estos valores deben coincidir con los de common/config/settings.py
CHUNK_SIZE = 512    # Alineado con el valor en common config
CHUNK_OVERLAP = 51  # Alineado con el valor en common config

# Optimización de consultas
MAX_QUERY_RETRIES = 3  # Máximo de reintentos de consulta
MAX_WORKERS = 4       # Máximo de workers para procesamiento simultáneo
STREAMING_TIMEOUT = 60 # Timeout para streaming (segundos)

# Modelos predeterminados
# Estos valores provienen de common/config/settings.py pero se definen aquí
# para reducir dependencias con la configuración global

# Modelos de OpenAI
DEFAULT_LLM_MODEL = "gpt-3.5-turbo"  # Modelo LLM predeterminado para OpenAI
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small" # Modelo de embedding predeterminado para OpenAI

# Ollama ya no es compatible con el sistema
# Los modelos de Ollama han sido eliminados

# Modelos de Groq
DEFAULT_GROQ_MODEL = "llama3-70b-8192" # Modelo predeterminado para Groq
DEFAULT_GROQ_LLM_MODEL = "llama3-70b-8192" # Modelo LLM predeterminado para Groq

# La configuración de proveedores ahora se determina por variables en .env
# Nota: Solo se soporta Groq para LLMs y OpenAI para embeddings

# Límites de recursos
MAX_DOC_SIZE_MB = 10  # Tamaño máximo de documentos (MB)

# Rate Limiting
ENABLE_RATE_LIMITING = True  # Activar limitación de tasa
DEFAULT_RATE_LIMIT = 10    # Límite de tasa por defecto (req/min)

# Dimensiones de embeddings esperadas
EMBEDDING_DIMENSIONS = 1536  # Valor por defecto para OpenAI
DEFAULT_EMBEDDING_DIMENSION = 1536

# Parámetros para eficiencia de caché y rendimiento
CACHE_EFFICIENCY_THRESHOLDS = {
    "excellent": 0.8,  # 80% o más de hit ratio es excelente
    "good": 0.6,       # 60-80% hit ratio es bueno
    "acceptable": 0.4, # 40-60% hit ratio es aceptable
    "poor": 0.2        # Menos de 20% hit ratio es pobre
}

# Umbrales de calidad para verificaciones de salud
QUALITY_THRESHOLDS = {
    "response_time_ms": {
        "excellent": 150,  # Menos de 150ms es excelente
        "good": 300,       # 150-300ms es bueno
        "acceptable": 500, # 300-500ms es aceptable
        "poor": 1000       # Más de 1000ms es pobre
    },
    "vector_retrieval_time_ms": {
        "excellent": 50,
        "good": 100,
        "acceptable": 200,
        "poor": 500
    }
}

# Intervalos de tiempo para diversas operaciones
TIME_INTERVALS = {
    "rate_limit_expiry": 300,  # 5 minutos
    "cache_refresh": 3600,     # 1 hora
    "metrics_retention": 86400, # 24 horas
    "status_check_timeout": 2   # 2 segundos para health checks
}

# Configuración de métricas
METRICS_CONFIG = {
    "max_latency_samples": 100,     # Máximas muestras para cálculo de latencia
    "latency_threshold_ms": 500,    # Umbral para latencia aceptable
    "cache_hit_ratio_threshold": 0.6 # Umbral mínimo de hit ratio en caché
}

# Timeouts para diversas operaciones
TIMEOUTS = {
    "vector_store_connection": 5,  # 5 segundos para conexión a vector store
    "embedding_service": 10,       # 10 segundos para llamadas al servicio de embeddings
    "supabase_query": 5,           # 5 segundos para consultas a Supabase
    "cache_operation": 2,          # 2 segundos para operaciones de caché
    "health_check": 1              # 1 segundo para health checks básicos
}
