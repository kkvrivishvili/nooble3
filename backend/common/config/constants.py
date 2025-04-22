"""
Constantes globales para toda la aplicación.

Este módulo centraliza todas las constantes y valores por defecto
que se utilizan en múltiples partes del sistema.
NO DEBE IMPORTAR NINGÚN OTRO MÓDULO INTERNO para evitar ciclos de dependencia.
"""

# Constantes de caché
TTL_SHORT = 300       # 5 minutos por defecto
TTL_STANDARD = 3600   # 1 hora por defecto
TTL_EXTENDED = 86400  # 24 horas por defecto
TTL_PERMANENT = None  # Sin expiración

# Constantes para fuentes de datos (para métricas)
SOURCE_CACHE = "cache"
SOURCE_SUPABASE = "supabase"
SOURCE_GENERATION = "generation"

# Constantes para tipos de métricas
METRIC_CACHE_HIT = "cache_hit"
METRIC_CACHE_MISS = "cache_miss"
METRIC_LATENCY = "latency"
METRIC_CACHE_SIZE = "cache_size"
METRIC_CACHE_INVALIDATION = "cache_invalidation"
METRIC_CACHE_INVALIDATION_COORDINATED = "cache_invalidation_coordinated"
METRIC_SERIALIZATION_ERROR = "serialization_error"
METRIC_DESERIALIZATION_ERROR = "deserialization_error"

# Códigos de error básicos (solo los esenciales para evitar ciclos)
ERROR_GENERAL = "GENERAL_ERROR"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_TENANT_REQUIRED = "TENANT_REQUIRED"
ERROR_DATABASE = "DATABASE_ERROR"
ERROR_CACHE = "CACHE_ERROR"
ERROR_CONFIGURATION = "CONFIGURATION_ERROR"

# Mapeo de tipos de datos a TTL predeterminados
DEFAULT_TTL_MAPPING = {
    "embedding": TTL_EXTENDED,           # Embeddings (estables)
    "vector_store": TTL_STANDARD,        # Vector stores (moderadamente estables)
    "query_result": TTL_SHORT,           # Resultados de consulta (volátiles)
    "agent_config": TTL_STANDARD,        # Configuraciones de agentes (moderadamente estables)
    "configurations": TTL_STANDARD,      # Configuraciones (moderadamente estables)
    "default": TTL_STANDARD              # Valor por defecto
}
