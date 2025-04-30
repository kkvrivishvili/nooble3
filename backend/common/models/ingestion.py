"""
Modelos para el servicio de ingestion y procesamiento de documentos.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .base import BaseResponse, BaseModel as CommonBaseModel

class FileUploadResponse(BaseResponse):
    """Respuesta para operaciones de subida e ingesta de documentos"""
    document_id: str
    job_id: Optional[str] = None
    message: str
    status: str = "accepted"
    collection_id: Optional[str] = None
    file_name: Optional[str] = None
    success: bool = True

class BatchJobResponse(BaseResponse):
    """Respuesta para operaciones de procesamiento por lotes"""
    success: bool = True
    message: str
    batch_id: str
    job_count: int
    failed_count: int = 0
    status: str = "processing"

class DocumentUploadMetadata(CommonBaseModel):
    """Metadatos para la subida de documentos"""
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    custom_properties: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[List[str]] = Field(default_factory=list)

class UrlIngestionRequest(CommonBaseModel):
    """Solicitud para ingerir contenido desde una URL"""
    url: str
    collection_id: str
    metadata: Optional[DocumentUploadMetadata] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None

class TextIngestionRequest(CommonBaseModel):
    """Solicitud para ingerir texto plano"""
    text: str
    collection_id: str
    metadata: Optional[DocumentUploadMetadata] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None

class BatchUrlsRequest(CommonBaseModel):
    """Solicitud para procesar múltiples URLs en un lote"""
    urls: List[str]
    collection_id: str
    title_prefix: Optional[str] = None
    tags: Optional[List[str]] = None
