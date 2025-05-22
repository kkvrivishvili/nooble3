"""
Modelos específicos para el servicio de embeddings.
"""

from typing import Dict, Any, List, Optional, Union, Literal
from uuid import UUID
from pydantic import BaseModel as PydanticBaseModel, Field, validator
from enum import Enum

# Importamos sólo la clase base para mantener la compatibilidad
from common.models.base import BaseModel, BaseResponse


class FailedEmbeddingItem(BaseModel):
    """Item que falló durante el procesamiento de embeddings."""
    index: int
    text: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    error: str


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
                    "model": "text-embedding-3-small",
                    "dimensions": 1536,
                    "processing_time": 0.125
                }
            }
        }
    }


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


class EmbeddingTaskType(str, Enum):
    """Tipos de tareas para el servicio de embedding."""
    QUERY = "query"
    DOCUMENT = "document"
    RERANKING = "reranking"
    CLASSIFICATION = "classification"
    CLUSTERING = "clustering"
    CUSTOM = "custom"


class EmbeddingTaskConfig(BaseModel):
    """Configuración específica para tareas de embedding."""
    task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY
    similarity_threshold: Optional[float] = 0.7
    normalize: bool = True
    truncate_strategy: Optional[Literal["head", "tail", "middle"]] = "tail"
    truncate_to_n_tokens: Optional[int] = None
    custom_parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    @validator('similarity_threshold')
    def validate_similarity_threshold(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError("similarity_threshold debe estar entre 0 y 1")
        return v


class ConversationContext(BaseModel):
    """Contexto de la conversación para enriquecer los embeddings."""
    conversation_id: Optional[str] = None
    agent_id: Optional[str] = None
    query_history: Optional[List[str]] = Field(default_factory=list)
    active_tools: Optional[List[str]] = Field(default_factory=list)
    user_preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)
    session_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class EnhancedEmbeddingRequest(BaseModel):
    """
    Solicitud mejorada para generar embeddings con contexto y configuración específica.
    
    Esta solicitud incluye configuración específica para la tarea, contexto de la
    conversación, y permite especificar metadatos adicionales para mejorar la
    calidad de los embeddings generados.
    """
    texts: List[str]
    model: Optional[str] = None
    tenant_id: str
    collection_id: Optional[UUID] = None
    chunk_ids: Optional[List[str]] = None
    subscription_tier: Optional[str] = None
    task_config: Optional[EmbeddingTaskConfig] = None
    conversation_context: Optional[ConversationContext] = None
    source_service: Optional[str] = None
    target_service: Optional[str] = None
    metadata: Optional[List[Dict[str, Any]]] = None

    @validator('texts')
    def validate_texts(cls, v):
        if not v:
            raise ValueError("La lista de textos no puede estar vacía")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "texts": ["¿Cuál es la capital de Francia?", "París es una ciudad hermosa."],
                "model": "text-embedding-3-small",
                "tenant_id": "tenant_123",
                "collection_id": "123e4567-e89b-12d3-a456-426614174000",
                "task_config": {
                    "task_type": "query",
                    "normalize": True
                },
                "conversation_context": {
                    "conversation_id": "conv_123",
                    "agent_id": "agent_456"
                }
            }
        }
    }


class EnhancedEmbeddingResponse(BaseResponse):
    """
    Respuesta mejorada con embeddings generados y metadatos enriquecidos.
    
    Incluye información sobre la configuración utilizada, métricas de procesamiento
    y datos de compatibilidad con LlamaIndex y LangChain.
    """
    embeddings: List[List[float]]
    model: str
    dimensions: int
    task_config: Optional[EmbeddingTaskConfig] = None
    processing_time: float
    cached_count: int = 0
    total_tokens: Optional[int] = None
    collection_id: Optional[UUID] = None
    llama_index_compatible: bool = True
    langchain_compatible: bool = True
    compatibility_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
