"""
Modelos de datos específicos para el servicio de embeddings.
"""

# Solo importamos los modelos necesarios
from .embeddings import EnhancedEmbeddingRequest, EnhancedEmbeddingResponse

# Re-exportar solo las clases necesarias
__all__ = ['EnhancedEmbeddingRequest', 'EnhancedEmbeddingResponse']

