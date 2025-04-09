"""
Endpoints públicos para consultas RAG.
"""

import time
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4

from common.models import TenantInfo, QueryRequest, QueryResponse
from common.errors import ServiceError, handle_service_error_simple
from common.context import with_context, set_current_collection_id
from common.auth import verify_tenant, validate_model_access
from common.tracking import track_query

from services.query_engine import create_query_engine, process_query_with_sources

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/collections/{collection_id}/query",
    response_model=QueryResponse,
    summary="Consultar colección",
    description="Realiza una consulta RAG sobre una colección específica"
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def query_collection(
    collection_id: str,
    request: QueryRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Procesa una consulta RAG (Retrieval Augmented Generation) sobre una colección específica.
    
    Este endpoint realiza una búsqueda semántica de información relevante en los documentos 
    de la colección especificada y genera una respuesta contextualizada utilizando un modelo de lenguaje.
    
    Args:
        collection_id: ID único de la colección a consultar (UUID)
        request: Solicitud de consulta
            - query: Texto de la consulta a procesar
            - similarity_top_k: Número de documentos a recuperar (opcional)
            - llm_model: Modelo LLM a utilizar (opcional)
            - response_mode: Modo de generación de respuesta (opcional)
        tenant_info: Información del tenant (inyectada)
        
    Returns:
        QueryResponse: Respuesta generada con fuentes y metadatos
    """
    # Establecer collection_id en el contexto
    set_current_collection_id(collection_id)
    
    # Forzar el collection_id de la ruta en la solicitud
    request.collection_id = collection_id
    
    # Validar acceso al modelo LLM
    if request.llm_model:
        # Capturar el modelo validado y asignarlo
        request.llm_model = await validate_model_access(tenant_info, request.llm_model, "llm")
    
    # Obtener tiempo de inicio para medición de rendimiento
    start_time = time.time()
    
    try:
        # Crear motor de consulta
        query_engine, debug_handler = await create_query_engine(
            tenant_info=tenant_info,
            collection_id=collection_id,
            llm_model=request.llm_model,
            similarity_top_k=request.similarity_top_k,
            response_mode=request.response_mode
        )
        
        # Procesar consulta
        result = await process_query_with_sources(
            query_engine=query_engine,
            debug_handler=debug_handler,
            query=request.query,
            filters=request.filters
        )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Registrar uso de tokens para facturación
        await track_query(
            tenant_id=tenant_info.tenant_id,
            operation_type="query",
            model=result.get("model", request.llm_model),
            tokens_in=result.get("tokens_in", 0),
            tokens_out=result.get("tokens_out", 0),
            agent_id=None,
            conversation_id=None
        )
        
        # Construir respuesta
        return QueryResponse(
            success=True,
            query=request.query,
            response=result["response"],
            sources=result["sources"],
            processing_time=processing_time,
            llm_model=result["model"],
            collection_id=collection_id,
            metadata={
                "similarity_top_k": request.similarity_top_k,
                "response_mode": request.response_mode,
                "tokens": result.get("tokens_total", 0)
            }
        )
        
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error procesando consulta: {str(e)}",
            error_code="QUERY_PROCESSING_ERROR"
        )

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consulta general",
    description="Realiza una consulta RAG (para compatibilidad con versiones anteriores)",
    deprecated=True
)
@handle_service_error_simple
@with_context(tenant=True, collection=True)
async def legacy_query_endpoint(
    request: QueryRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Endpoint de compatibilidad para consultas RAG.
    Redirige a /collections/{collection_id}/query.
    
    Args:
        request: Solicitud de consulta
        tenant_info: Información del tenant
        
    Returns:
        QueryResponse: Respuesta RAG
    """
    if not request.collection_id:
        raise ServiceError(
            message="Se requiere collection_id para realizar consultas",
            error_code="MISSING_COLLECTION_ID",
            status_code=400
        )
    
    # Redirigir a la ruta RESTful moderna
    return await query_collection(str(request.collection_id), request, tenant_info)