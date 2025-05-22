"""
Módulo de servicios para el Query Service.

Contiene los componentes principales de procesamiento de consultas RAG
y búsqueda vectorial del servicio refactorizado.
"""

from .query_processor import (
    process_rag_query,
    search_documents
)
from .vector_store import (
    search_by_embedding,
    get_collection_info
)

__all__ = [
    "process_rag_query",
    "search_documents",
    "search_by_embedding",
    "get_collection_info"
]
