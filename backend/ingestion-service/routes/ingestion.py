"""
Endpoints para la ingesta de documentos.
"""

import logging
import uuid
import time
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, Query, Body
from pydantic import BaseModel, Field

from common.models import TenantInfo, FileUploadResponse, BatchJobResponse
from common.errors import (
    ServiceError, handle_service_error_simple, ErrorCode,
    DocumentProcessingError, ValidationError
)
from common.context import with_context
from common.auth import verify_tenant, check_tenant_quotas
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

from services.document_processor import validate_file
from services.queue import queue_document_processing_job
from config import get_settings
from backend.common.db.storage import upload_to_storage

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentUploadMetadata(BaseModel):
    """Metadatos para carga de documentos."""
    title: Optional[str] = None
    description: Optional[str] = None
    collection_id: str
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    custom_metadata: Optional[dict] = None

@router.post(
    "/upload",
    summary="Cargar documento",
    description="Carga un documento para procesamiento y generación de embeddings"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def upload_document(
    file: UploadFile = File(...),
    tenant_info: TenantInfo = Depends(verify_tenant),
    collection_id: str = Form(...)
):
    """Endpoint simplificado que solo sube a Storage y encola"""
    # 1. Validar archivo
    file_info = await validate_file(file)
    
    # 2. Subir a Supabase Storage
    file_key = await upload_to_storage(
        tenant_id=tenant_info.id,
        collection_id=collection_id,
        file_content=await file.read(),
        file_name=file.filename
    )
    
    # 3. Encolar procesamiento
    job_id = await queue_document_processing_job(
        tenant_id=tenant_info.id,
        collection_id=collection_id,
        document_id=str(uuid.uuid4()),
        file_key=file_key  # Referencia al archivo en Storage
    )
    
    return {"job_id": job_id, "status": "queued"}

class UrlIngestionRequest(BaseModel):
    url: str
    collection_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

@router.post(
    "/ingest-url",
    response_model=FileUploadResponse,
    summary="Ingerir contenido de URL",
    description="Procesa y genera embeddings para el contenido de una URL"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def ingest_url(
    request: UrlIngestionRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Procesa y genera embeddings para el contenido de una URL.
    
    Args:
        request: Datos de la URL a procesar
        tenant_info: Información del tenant
        
    Returns:
        FileUploadResponse: Resultado de la operación
    """
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    await check_tenant_quotas(tenant_info)
    
    try:
        # Validar URL
        if not request.url.startswith(("http://", "https://")):
            raise ValidationError(
                message="URL inválida, debe comenzar con http:// o https://",
                details={"url": request.url}
            )
        
        # Generar ID único para el documento
        document_id = str(uuid.uuid4())
        
        # Crear metadatos para el documento
        document_metadata = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "collection_id": request.collection_id,
            "title": request.title or "URL Content",
            "description": request.description,
            "file_name": request.url,
            "file_type": "url",
            "tags": request.tags,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        # Guardar metadatos en Supabase
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("documents")).insert(document_metadata).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error guardando metadatos del documento URL: {result.error}",
                error_code="DOCUMENT_METADATA_ERROR"
            )
        
        # Encolamos el trabajo de procesamiento
        job_id = await queue_document_processing_job(
            tenant_id=tenant_id,
            document_id=document_id,
            collection_id=request.collection_id,
            url=request.url,
            file_info={"type": "url", "size": 0}
        )
        
        return FileUploadResponse(
            success=True,
            message="URL encolada para procesamiento",
            document_id=document_id,
            collection_id=request.collection_id,
            file_name=request.url,
            job_id=job_id,
            status="pending"
        )
        
    except Exception as e:
        logger.error(f"Error al procesar URL: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise DocumentProcessingError(
            message=f"Error al procesar URL: {str(e)}",
            details={"url": request.url}
        )

class TextIngestionRequest(BaseModel):
    text: str
    collection_id: str
    title: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None

@router.post(
    "/ingest-text",
    response_model=FileUploadResponse,
    summary="Ingerir texto plano",
    description="Procesa y genera embeddings para texto plano"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def ingest_text(
    request: TextIngestionRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Procesa y genera embeddings para texto plano.
    
    Args:
        request: Datos del texto a procesar
        tenant_info: Información del tenant
        
    Returns:
        FileUploadResponse: Resultado de la operación
    """
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    await check_tenant_quotas(tenant_info)
    
    try:
        # Validar texto
        if not request.text.strip():
            raise ValidationError(
                message="El texto no puede estar vacío",
                details={"text_length": 0}
            )
        
        # Generar ID único para el documento
        document_id = str(uuid.uuid4())
        
        # Crear metadatos para el documento
        document_metadata = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "collection_id": request.collection_id,
            "title": request.title,
            "description": request.description,
            "file_name": "custom_text.txt",
            "file_type": "text",
            "tags": request.tags,
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        # Guardar metadatos en Supabase
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("documents")).insert(document_metadata).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error guardando metadatos del documento de texto: {result.error}",
                error_code="DOCUMENT_METADATA_ERROR"
            )
        
        # Encolamos el trabajo de procesamiento
        job_id = await queue_document_processing_job(
            tenant_id=tenant_id,
            document_id=document_id,
            collection_id=request.collection_id,
            text_content=request.text,
            file_info={"type": "text", "size": len(request.text)}
        )
        
        return FileUploadResponse(
            success=True,
            message="Texto encolado para procesamiento",
            document_id=document_id,
            collection_id=request.collection_id,
            file_name="custom_text.txt",
            job_id=job_id,
            status="pending"
        )
        
    except Exception as e:
        logger.error(f"Error al procesar texto: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise DocumentProcessingError(
            message=f"Error al procesar texto: {str(e)}",
            details={"text_length": len(request.text) if hasattr(request, "text") else 0}
        )

class BatchUrlsRequest(BaseModel):
    urls: List[str]
    collection_id: str
    title_prefix: Optional[str] = None
    tags: Optional[List[str]] = None

@router.post(
    "/batch-urls",
    response_model=BatchJobResponse,
    summary="Procesar lote de URLs",
    description="Procesa un lote de URLs en segundo plano"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def batch_process_urls(
    request: BatchUrlsRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Procesa un lote de URLs en segundo plano.
    
    Args:
        request: Lista de URLs y metadatos
        tenant_info: Información del tenant
        
    Returns:
        BatchJobResponse: ID del trabajo por lotes y estadísticas
    """
    tenant_id = tenant_info.tenant_id
    
    # Verificar cuotas del tenant
    await check_tenant_quotas(tenant_info)
    
    try:
        # Validar URLs
        urls = [url for url in request.urls if url.startswith(("http://", "https://"))]
        if len(urls) == 0:
            raise ValidationError(
                message="No se proporcionaron URLs válidas",
                details={"urls_count": len(request.urls)}
            )
        
        # Generar ID único para el trabajo por lotes
        batch_id = str(uuid.uuid4())
        
        # Crear trabajos individuales para cada URL
        job_ids = []
        for i, url in enumerate(urls):
            # Título generado automáticamente si no se proporciona
            title = f"{request.title_prefix or 'URL'} {i+1}" if not request.title_prefix else f"{request.title_prefix} {i+1}"
            
            # Generar ID único para el documento
            document_id = str(uuid.uuid4())
            
            # Crear metadatos para el documento
            document_metadata = {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "collection_id": request.collection_id,
                "title": title,
                "description": f"Procesado en lote {batch_id}",
                "file_name": url,
                "file_type": "url",
                "tags": request.tags,
                "batch_id": batch_id,
                "status": "pending",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            # Guardar metadatos en Supabase
            supabase = get_supabase_client()
            result = await supabase.table(get_table_name("documents")).insert(document_metadata).execute()
            
            if result.error:
                logger.error(f"Error guardando metadatos para URL {url}: {result.error}")
                continue
            
            # Encolar trabajo de procesamiento
            job_id = await queue_document_processing_job(
                tenant_id=tenant_id,
                document_id=document_id,
                collection_id=request.collection_id,
                url=url,
                file_info={"type": "url", "size": 0},
                batch_id=batch_id
            )
            
            job_ids.append(job_id)
        
        return BatchJobResponse(
            success=True,
            message=f"Lote de {len(job_ids)} URLs encoladas para procesamiento",
            batch_id=batch_id,
            job_count=len(job_ids),
            failed_count=len(urls) - len(job_ids),
            status="processing"
        )
        
    except Exception as e:
        logger.error(f"Error al procesar lote de URLs: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise DocumentProcessingError(
            message=f"Error al procesar lote de URLs: {str(e)}",
            details={"urls_count": len(request.urls) if hasattr(request, "urls") else 0}
        )