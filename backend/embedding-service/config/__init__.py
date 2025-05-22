"""
Configuración centralizada para el servicio de embeddings.

Este módulo define la configuración principal y exporta las funciones
y clases necesarias para mantener centralizada la configuración del servicio.
"""

from .settings import EmbeddingServiceSettings, get_settings

__all__ = [
    'EmbeddingServiceSettings',
    'get_settings',
    'get_health_status',
    'EMBEDDING_DIMENSIONS',
    'DEFAULT_EMBEDDING_DIMENSION',
    'QUALITY_THRESHOLDS',
    'CACHE_EFFICIENCY_THRESHOLDS',
    'OLLAMA_API_ENDPOINTS',
    'TIMEOUTS',
    'MOCK_METRICS',
    'TIME_INTERVALS',
    'METRICS_CONFIG'
]
