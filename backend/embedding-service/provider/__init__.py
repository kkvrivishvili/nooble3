"""
Módulo de proveedores para el servicio de embeddings.

Este paquete contiene las implementaciones de los diferentes proveedores
de embeddings utilizados por el servicio.
"""

# Exportar clases y funciones principales de OpenAI
from .openai import (
    OpenAIEmbeddingProvider,
    get_openai_embedding,
    OpenAIEmbeddingError,
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIModelNotFoundError,
    estimate_openai_tokens,
    OPENAI_EMBEDDING_MODELS
)

__all__ = [
    "OpenAIEmbeddingProvider",
    "get_openai_embedding",
    "OpenAIEmbeddingError",
    "OpenAIAuthenticationError",
    "OpenAIRateLimitError",
    "OpenAIModelNotFoundError",
    "estimate_openai_tokens",
    "OPENAI_EMBEDDING_MODELS"
]
