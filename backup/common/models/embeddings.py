"""
Modelos específicos para el servicio de embeddings.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import Field

from .base import BaseModel as CommonBaseModel, BaseResponse

class FailedEmbeddingItem(CommonBaseModel):
    """Item que falló durante el procesamiento de embeddings."""
    index: int
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    error: str

class InternalEmbeddingResponse(CommonBaseModel):
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
