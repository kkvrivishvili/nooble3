"""
Constantes fundamentales del sistema.

Este módulo contiene todas las constantes globales y valores por defecto
utilizados en múltiples partes del sistema. Al centralizar estos valores aquí,
evitamos dependencias circulares y mantenemos una única fuente de verdad.

IMPORTANTE: Este módulo NO DEBE IMPORTAR de ningún otro módulo de la aplicación
para evitar dependencias circulares.
"""

# =========== Constantes de TTL ===========
TTL_SHORT = 300       # 5 minutos
TTL_STANDARD = 3600   # 1 hora
TTL_EXTENDED = 86400  # 24 horas
TTL_PERMANENT = 0     # Sin expiración

# =========== Constantes de fuente de datos ===========
SOURCE_CACHE = "cache"
SOURCE_SUPABASE = "supabase"
SOURCE_GENERATION = "generation"

# =========== Constantes de métricas ===========
METRIC_CACHE_HIT = "cache_hit"
METRIC_CACHE_MISS = "cache_miss"
METRIC_LATENCY = "latency"
METRIC_CACHE_SIZE = "cache_size"
METRIC_CACHE_INVALIDATION = "cache_invalidation"
METRIC_CACHE_INVALIDATION_COORDINATED = "cache_invalidation_coordinated"
METRIC_SERIALIZATION_ERROR = "serialization_error"
METRIC_DESERIALIZATION_ERROR = "deserialization_error"

# =========== Constantes de métricas para chunks ===========
METRIC_CHUNK_CACHE_HIT = "chunk_cache_hit"
METRIC_CHUNK_CACHE_MISS = "chunk_cache_miss"
METRIC_CHUNK_CACHE_INVALIDATION = "chunk_cache_invalidation"
METRIC_CHUNK_EMBEDDING_GENERATION = "chunk_embedding_generation"

# =========== Códigos de error básicos ===========
ERROR_GENERAL = "GENERAL_ERROR"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_TENANT_REQUIRED = "TENANT_REQUIRED"
ERROR_DATABASE = "DATABASE_ERROR"
ERROR_CACHE = "CACHE_ERROR"
ERROR_CONFIGURATION = "CONFIGURATION_ERROR"

# =========== Mapeos de TTL ===========
DEFAULT_TTL_MAPPING = {
    "embedding": TTL_EXTENDED,         # 24 horas
    "vector_store": TTL_STANDARD,      # 1 hora
    "query_result": TTL_SHORT,         # 5 minutos
    "agent_config": TTL_STANDARD,      # 1 hora
    "retrieval_cache": TTL_SHORT,      # 5 minutos
    "semantic_index": TTL_STANDARD,    # 1 hora
    "embedding_batch": TTL_EXTENDED,   # 24 horas
}

# =========== Constantes de inicio de componentes ===========
COMPONENT_PRIORITY_CORE = 0        # Componentes fundamentales (registry, constants)
COMPONENT_PRIORITY_CONFIG = 10     # Configuraciones del sistema
COMPONENT_PRIORITY_DB = 20         # Conexiones a bases de datos
COMPONENT_PRIORITY_CACHE = 30      # Sistema de caché
COMPONENT_PRIORITY_AUTH = 40       # Sistema de autenticación
COMPONENT_PRIORITY_ERROR = 50      # Manejadores de errores
COMPONENT_PRIORITY_SERVICE = 60    # Servicios de negocio
COMPONENT_PRIORITY_API = 70        # Endpoints de API
