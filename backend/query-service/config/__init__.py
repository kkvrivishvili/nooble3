"""
Paquete de configuración para el servicio de consultas.

Este paquete centraliza toda la configuración específica del servicio,
siguiendo el patrón de configuración unificado para todos los servicios.
"""

from config.settings import get_settings, get_health_status
from config.constants import (
    LLM_DEFAULT_TEMPERATURE,
    LLM_MAX_TOKENS,
    DEFAULT_SIMILARITY_TOP_K,
    MAX_SIMILARITY_TOP_K,
    DEFAULT_RESPONSE_MODE,
    SIMILARITY_THRESHOLD,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    CACHE_EFFICIENCY_THRESHOLDS,
    QUALITY_THRESHOLDS,
    TIME_INTERVALS,
    METRICS_CONFIG,
    TIMEOUTS,
    # Optimización de consultas
    MAX_QUERY_RETRIES,
    MAX_WORKERS,
    STREAMING_TIMEOUT,
    # Modelos predeterminados
    DEFAULT_LLM_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_GROQ_LLM_MODEL,
    # Nota: Solo soportamos Groq para LLMs y OpenAI para embeddings
    # Límites de recursos
    MAX_DOC_SIZE_MB,
    # Rate Limiting
    ENABLE_RATE_LIMITING,
    DEFAULT_RATE_LIMIT
)

# Exportar todo lo necesario para facilitar el uso en otros módulos
__all__ = [
    "get_settings",
    "get_health_status",
    "LLM_DEFAULT_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "DEFAULT_SIMILARITY_TOP_K",
    "MAX_SIMILARITY_TOP_K",
    "DEFAULT_RESPONSE_MODE",
    "SIMILARITY_THRESHOLD",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "EMBEDDING_DIMENSIONS",
    "DEFAULT_EMBEDDING_DIMENSION",
    "CACHE_EFFICIENCY_THRESHOLDS",
    "QUALITY_THRESHOLDS",
    "TIME_INTERVALS",
    "METRICS_CONFIG",
    "TIMEOUTS",
    # Optimización de consultas
    "MAX_QUERY_RETRIES",
    "MAX_WORKERS",
    "STREAMING_TIMEOUT",
    # Modelos predeterminados (Ollama ya no es compatible)
    "DEFAULT_LLM_MODEL",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_GROQ_MODEL",
    "DEFAULT_GROQ_LLM_MODEL",
    # Límites de recursos
    "MAX_DOC_SIZE_MB",
    # Rate Limiting
    "ENABLE_RATE_LIMITING",
    "DEFAULT_RATE_LIMIT"
]
