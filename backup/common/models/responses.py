"""
Modelos de respuesta estándar para los diferentes servicios.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import Field, BaseModel as PydanticBaseModel

from .base import BaseResponse, BaseModel

class ServiceStatusResponse(BaseResponse):
    """Respuesta estándar para endpoints de status del servicio."""
    service_name: str
    version: str
    environment: str
    uptime: float
    uptime_formatted: str
    status: str = "online"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CacheStatsResponse(BaseResponse):
    """Estadísticas de uso del caché."""
    tenant_id: str
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    cache_enabled: bool = False
    cached_embeddings: int = 0
    memory_usage_bytes: int = 0
    memory_usage_mb: float = 0.0


class CacheClearResponse(BaseResponse):
    """Respuesta a la operación de limpieza de caché."""
    keys_deleted: int = 0


class ModelListResponse(BaseResponse):
    """Respuesta con la lista de modelos disponibles."""
    models: Dict[str, Any] = Field(default_factory=dict)
    default_model: str
    subscription_tier: str
    tenant_id: str


class TextItem(BaseModel):
    """Item de texto con metadatos para procesar."""
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    """Solicitud para generar embeddings."""
    tenant_id: str
    texts: List[str]
    metadata: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    collection_id: Optional[UUID] = None
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None


class EmbeddingResponse(BaseResponse):
    """Respuesta con embeddings generados."""
    embeddings: List[List[float]]
    model: str
    dimensions: int
    collection_id: Optional[UUID] = None
    processing_time: float
    cached_count: int = 0
    total_tokens: Optional[int] = None


class BatchEmbeddingRequest(BaseModel):
    """Solicitud para procesar un lote de textos con embeddings."""
    tenant_id: str
    items: List[TextItem]
    model: Optional[str] = None
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None


class BatchEmbeddingResponse(BaseResponse):
    """Respuesta con embeddings generados para un lote de textos con metadatos."""
    embeddings: List[List[float]]
    items: List[TextItem]
    model: str
    dimensions: int
    processing_time: float
    cached_count: int = 0
    total_tokens: Optional[int] = None
    collection_id: Optional[UUID] = None


class QueryContextItem(BaseModel):
    """Item de contexto para respuestas de consulta."""
    text: str
    metadata: Optional[Dict[str, Any]] = None
    score: Optional[float] = None


class QueryRequest(BaseModel):
    """
    Solicitud para realizar una consulta RAG.
    
    Permite buscar información en una colección identificada por collection_id.
    """
    tenant_id: str
    query: str
    collection_id: UUID  # ID único de la colección (UUID)
    llm_model: Optional[str] = None
    similarity_top_k: Optional[int] = 4
    additional_metadata_filter: Optional[Dict[str, Any]] = None
    response_mode: Optional[str] = "compact"  # compact, refine, tree
    stream: Optional[bool] = False
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None


class QueryResponse(BaseResponse):
    """
    Respuesta a una consulta RAG.
    
    Incluye la respuesta generada y las fuentes utilizadas para la generación.
    """
    query: str
    response: str
    sources: List[QueryContextItem]
    processing_time: float
    collection_id: UUID
    name: Optional[str] = None  # Solo para UI
    llm_model: Optional[str] = None
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None