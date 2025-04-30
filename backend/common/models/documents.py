"""
Modelos para la gestión de documentos.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import Field

from .base import BaseResponse, BaseModel

class DocumentInfo(BaseModel):
    """Información básica de un documento."""
    document_id: str
    tenant_id: str
    collection_id: str
    file_name: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    chunk_count: Optional[int] = 0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class DocumentChunk(BaseModel):
    """Fragmento de un documento procesado."""
    chunk_id: str
    document_id: str
    text: str
    page_number: Optional[int] = None
    chunk_number: int
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class DocumentListResponse(BaseResponse):
    """Respuesta con lista de documentos."""
    documents: List[DocumentInfo]
    total_count: int
    offset: int
    limit: int
    collection_id: Optional[str] = None
    status_filter: Optional[str] = None

class DocumentDetailResponse(BaseResponse):
    """Respuesta con detalles completos de un documento."""
    document: DocumentInfo
    chunks: Optional[List[DocumentChunk]] = None
    job_status: Optional[str] = None
    job_id: Optional[str] = None
    processing_stats: Optional[Dict[str, Any]] = Field(default_factory=dict)

# La clase DeleteDocumentResponse se importa desde .collections para evitar duplicación
