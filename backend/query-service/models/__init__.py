"""
Módulo de modelos de datos para el Query Service.

Contiene las estructuras de datos y modelos Pydantic utilizados en el servicio.
"""

from .query import (
    InternalQueryRequest,
    InternalSearchRequest,
    DocumentMatch,
    QueryResponse
)

__all__ = [
    "InternalQueryRequest",
    "InternalSearchRequest",
    "DocumentMatch",
    "QueryResponse"
]
