"""
Modelos específicos para el servicio de embeddings.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import Field, BaseModel

# Importamos EmbeddingRequest y EmbeddingResponse desde common.models para mantener consistencia
from common.models.responses import EmbeddingRequest, EmbeddingResponse, BatchEmbeddingRequest, BatchEmbeddingResponse, TextItem

class BatchEmbeddingItem(BaseModel):
    """Item individual en un lote de procesamiento de embeddings."""
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    error: Optional[str] = None


class BatchEmbeddingResult(BaseModel):
    """Resultado del procesamiento de un lote de embeddings."""
    items: List[BatchEmbeddingItem]
    model: str
    dimensions: int
    processing_time: float
    cached_count: int = 0
    total_tokens: Optional[int] = None


class InternalEmbeddingResponse(BaseModel):
    """Formato de respuesta para el endpoint interno de embedding."""
    success: bool
    message: str
    data: Optional[List[List[float]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Embeddings generados correctamente",
                "data": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                "metadata": {
                    "model": "text-embedding-ada-002",
                    "dimensions": 1536,
                    "processing_time": 0.125
                }
            }
        }
    }
