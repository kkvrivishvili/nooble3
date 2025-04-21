"""
Endpoints públicos para consultas RAG.
"""

import time
import logging
from typing import Optional, List, Dict, Any, Union

from fastapi import APIRouter, Depends, Query
from pydantic import UUID4, BaseModel, Field

from common.models import TenantInfo, QueryRequest, QueryResponse
from common.errors import (
    ServiceError, handle_service_error_simple,
    QueryProcessingError
)
from common.context import with_context, set_current_tenant_id, get_current_tenant_id, get_current_collection_id, set_current_context_value
from common.auth import verify_tenant, validate_model_access, RoleType
from common.config import get_settings
from common.config.tiers import get_available_llm_models
from common.tracking import track_usage
from services.query_engine import create_query_engine, process_query_with_sources

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

@router.post(
    "/collections/{collection_id}/query",
    response_model=QueryResponse,
    summary="Consultar colección",
    description="Realiza una consulta RAG sobre una colección específica"
)
@with_context(tenant=True, collection=True)
@handle_service_error_simple
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
    # Forzar el collection_id de la ruta en la solicitud
    request.collection_id = collection_id
    
    # Validar acceso al modelo LLM
    if request.llm_model:
        try:
            # Intentar validar el modelo solicitado
            request.llm_model = await validate_model_access(tenant_info, request.llm_model, "llm", tenant_id=tenant_info.tenant_id)
        except ServiceError as e:
            # Si el modelo no está permitido, usar el modelo por defecto para su tier
            logger.info(f"Cambiando al modelo por defecto: {e.message}", extra=e.context)
            allowed_models = get_available_llm_models(tenant_info.subscription_tier, tenant_id=tenant_info.tenant_id)
            request.llm_model = allowed_models[0] if allowed_models else settings.default_llm_model
            # Informar al usuario sobre el cambio de modelo en los metadatos de respuesta
            set_current_context_value("model_downgraded", True)
    
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
        await track_usage(
            tenant_id=tenant_info.tenant_id,
            operation="query",
            metadata={
                "operation_type": "query",
                "model": result.get("model", request.llm_model),
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
                "agent_id": None,
                "conversation_id": None
            }
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
        raise QueryProcessingError(
            message=f"Error procesando consulta: {str(e)}",
            details={
                "query": request.query,
                "collection_id": request.collection_id,
                "response_mode": request.response_mode
            }
        )

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consulta general",
    description="Realiza una consulta RAG (para compatibilidad con versiones anteriores)",
    deprecated=True
)
@with_context(tenant=True, collection=True)
@handle_service_error_simple
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