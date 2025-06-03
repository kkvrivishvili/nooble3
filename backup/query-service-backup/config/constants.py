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
# ---------------

# Modelos tradicionales
DEFAULT_GROQ_MODEL = "llama3-70b-8192"  # Modelo predeterminado para Groq
# Especificaciones: 70B parámetros, ventana de contexto de 8192 tokens
# Uso recomendado: Generación de texto de alta calidad, RAG avanzado
# Rendimiento: Alta calidad de respuestas, buen razonamiento, velocidad media

DEFAULT_GROQ_LLM_MODEL = "llama3-70b-8192"  # Modelo LLM predeterminado para Groq
# Este es un alias del modelo anterior para compatibilidad con código existente

# Nuevos modelos de Groq con características avanzadas
GROQ_EXTENDED_CONTEXT_MODEL = "llama-3.1-8b-instant-128k" 
# Especificaciones: 8B parámetros, ventana de contexto extendida de 128K tokens
# Uso recomendado: Análisis de documentos largos, summarización de muchos documentos
# Rendimiento: Procesamiento rápido, especialmente útil para grandes volúmenes de texto
# Beneficio principal: Puede manejar hasta 128,000 tokens en una sola consulta

GROQ_FAST_MODEL = "llama-3.1-8b-instant" 
# Especificaciones: 8B parámetros, ventana estándar
# Uso recomendado: Consultas que requieren baja latencia, chatbots rápidos
# Rendimiento: Muy baja latencia (~200ms para respuestas iniciales)
# Beneficio principal: Optimizado para velocidad sin sacrificar demasiada calidad

# Modelos Llama 4 en Groq (última generación)
GROQ_MAVERICK_MODEL = "llama-4-maverick-17bx128e" 
# Especificaciones: Arquitectura 17B con 128 expertos (Mixture of Experts)
# Uso recomendado: Casos de uso empresariales que requieren alta precisión y razonamiento
# Rendimiento: Calidad excepcional, capacidad de razonamiento avanzada, contexto de 128K tokens
# Beneficio principal: Combina alto rendimiento con eficiencia de recursos

GROQ_SCOUT_MODEL = "llama-4-scout-17bx16e" 
# Especificaciones: Arquitectura 17B con 16 expertos (Mixture of Experts)
# Uso recomendado: Equilibrio entre rendimiento, calidad y costo
# Rendimiento: Buena calidad, razonamiento sólido con latencia media
# Beneficio principal: Opción balanceada para uso general

# Categorización de modelos por tier de tenant
# Esta estructura facilita la selección de modelos según el tier del tenant
GROQ_MODELS_BY_TIER = {
    # Enterprise: acceso a todos los modelos, incluyendo Llama 4
    "enterprise": {
        "default": GROQ_MAVERICK_MODEL,  # Máxima calidad por defecto
        "fast": GROQ_FAST_MODEL,         # Opción rápida
        "extended_context": GROQ_MAVERICK_MODEL,  # Mejor contexto extendido
        "balanced": GROQ_SCOUT_MODEL,    # Balance calidad/velocidad
    },
    
    # Business: acceso a modelos de contexto extendido y Llama 4 Scout
    "business": {
        "default": GROQ_SCOUT_MODEL,      # Opción balanceada por defecto
        "fast": GROQ_FAST_MODEL,          # Opción rápida
        "extended_context": GROQ_EXTENDED_CONTEXT_MODEL,  # Contexto extendido
        "balanced": GROQ_SCOUT_MODEL,     # Balance calidad/velocidad
    },
    
    # Premium: acceso a modelos Llama 3.1 y 3.3 
    "premium": {
        "default": "llama-3.3-70b-versatile",  # Alta calidad para premium
        "fast": GROQ_FAST_MODEL,               # Opción rápida
        "extended_context": GROQ_EXTENDED_CONTEXT_MODEL,  # Contexto extendido
        "balanced": "llama-3.1-8b-instant",     # Balance calidad/velocidad
    },
    
    # Standard: acceso a modelos 8B 
    "standard": {
        "default": "llama3-8b-8192",      # Modelo estándar
        "fast": GROQ_FAST_MODEL,          # Opción rápida
        "extended_context": "llama3-8b-8192",  # Sin contexto extendido real
        "balanced": "llama3-8b-8192",     # Modelo estándar
    },
    
    # Free: acceso limitado
    "free": {
        "default": "llama3-8b-8192",      # Modelo básico
        "fast": "llama3-8b-8192",         # Sin opción rápida real
        "extended_context": "llama3-8b-8192",  # Sin contexto extendido real
        "balanced": "llama3-8b-8192",     # Modelo básico
    }
}

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
