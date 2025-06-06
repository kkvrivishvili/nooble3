"""
Modelos relacionados con colecciones de documentos y su gestión.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import Field

from .base import BaseModel, BaseResponse
from .agents import AgentTool

class CollectionInfo(BaseModel):
    """
    Información sobre una colección de documentos.
    
    Proporciona detalles sobre una colección, incluyendo su identificador único,
    nombre amigable y estadísticas básicas.
    """
    collection_id: UUID  # ID único de la colección (UUID)
    name: str  # Nombre amigable de la colección
    description: Optional[str] = None
    document_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CollectionsListResponse(BaseResponse):
    """Respuesta con lista de colecciones para un tenant."""
    tenant_id: str
    collections: List[CollectionInfo]
    total: int


class CollectionToolResponse(BaseResponse):
    """Respuesta con información de la colección para integración con herramientas."""
    collection_id: UUID
    name: Optional[str] = None  # Solo para UI
    tenant_id: str
    tool: Optional[AgentTool] = None


class CollectionCreationResponse(BaseResponse):
    """Respuesta para creación de colecciones."""
    collection_id: UUID
    name: str
    description: Optional[str] = None
    tenant_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CollectionUpdateResponse(BaseResponse):
    """Respuesta para actualización de colecciones."""
    collection_id: UUID
    name: str
    description: Optional[str] = None
    tenant_id: str
    is_active: bool = True
    updated_at: Optional[str] = None


class CollectionStatsResponse(BaseResponse):
    """Respuesta con estadísticas de una colección."""
    tenant_id: str
    collection_id: UUID
    name: Optional[str] = None  # Solo para UI
    chunks_count: int = 0
    unique_documents_count: int = 0
    queries_count: int = 0
    last_updated: Optional[str] = None


class DeleteCollectionResponse(BaseResponse):
    """Respuesta a la eliminación de una colección."""
    collection_id: UUID
    name: Optional[str] = None
    deleted: bool = True
    documents_deleted: int = 0
    chunks_deleted: int = 0


# Alias para compatibilidad con código existente
class CollectionListResponse(CollectionsListResponse):
    """Alias de CollectionsListResponse para compatibilidad con código existente."""
    pass


class DocumentMetadata(BaseModel):
    """Metadatos para documentos."""
    source: str
    author: Optional[str] = None
    created_at: Optional[str] = None
    document_type: str
    tenant_id: str
    custom_metadata: Optional[Dict[str, Any]] = None


class DeleteDocumentResponse(BaseResponse):
    """
    Respuesta para operación de eliminación de documento.
    
    Confirma si el documento fue eliminado satisfactoriamente y proporciona 
    información sobre la colección a la que pertenecía.
    """
    document_id: str
    deleted: bool
    collection_id: Optional[UUID] = None
    name: Optional[str] = None