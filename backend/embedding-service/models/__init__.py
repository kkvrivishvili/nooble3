"""
Modelos de datos específicos para el servicio de embeddings.
"""

# Importar desde common.models para mantener compatibilidad
from common.models import (
    EmbeddingRequest, EmbeddingResponse,
    BatchEmbeddingRequest, BatchEmbeddingResponse, 
    FailedEmbeddingItem, InternalEmbeddingResponse, TextItem
)

# Re-exportar clases importantes
__all__ = [
    'EmbeddingRequest', 'EmbeddingResponse',
    'BatchEmbeddingRequest', 'BatchEmbeddingResponse',
    'FailedEmbeddingItem', 'InternalEmbeddingResponse', 'TextItem'
]
