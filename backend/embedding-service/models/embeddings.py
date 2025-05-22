"""
Modelos de request/response para el servicio de embeddings.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import Field, validator

from common.models.base import BaseModel, BaseResponse


class EnhancedEmbeddingRequest(BaseModel):
    """Request para generar embeddings."""
    texts: List[str] = Field(..., description="Textos para procesar")
    model: Optional[str] = Field(None, description="Modelo de embedding")
    tenant_id: str = Field(..., description="ID del tenant")
    collection_id: Optional[UUID] = Field(None, description="ID de colección")
    chunk_ids: Optional[List[str]] = Field(None, description="IDs de chunks")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    
    @validator('texts')
    def validate_texts(cls, v):
        if not v:
            raise ValueError("La lista de textos no puede estar vacía")
        return v


class EnhancedEmbeddingResponse(BaseResponse):
    """Response con embeddings generados."""
    embeddings: List[List[float]] = Field(..., description="Vectores de embedding")
    model: str = Field(..., description="Modelo utilizado")
    dimensions: int = Field(..., description="Dimensiones de los vectores")
    processing_time: float = Field(..., description="Tiempo de procesamiento")
    total_tokens: int = Field(..., description="Tokens procesados")
