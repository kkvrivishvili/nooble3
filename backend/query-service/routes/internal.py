"""
Endpoints internos para uso exclusivo de otros servicios (principalmente Agent Service).
"""

import time
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel, Field

from common.models import TenantInfo, QueryContextItem
from common.errors import (
    ServiceError, handle_service_error_simple, ErrorCode,
    QueryProcessingError, CollectionNotFoundError, 
    RetrievalError, GenerationError, InvalidQueryParamsError,
    EmbeddingGenerationError, EmbeddingModelError, TextTooLargeError
)
from common.context import with_context, get_current_tenant_id
from common.auth import verify_tenant, validate_model_access
from common.tracking import track_query

from services.query_engine import create_query_engine, process_query_with_sources

router = APIRouter()
logger = logging.getLogger(__name__)

# Modelo para solicitudes internas desde Agent Service
class InternalQueryRequest(BaseModel):
    tenant_id: str
    query: str
    collection_id: str
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    similarity_top_k: int = 4
    response_mode: str = "compact"
    llm_model: Optional[str] = None
    include_sources: bool = True
    max_sources: int = 3
    context_filter: Optional[Dict[str, Any]] = None

# Modelo para solicitudes de búsqueda internas
class InternalSearchRequest(BaseModel):
    tenant_id: str
    query: str
    collection_id: str
    limit: int = 5
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context_filter: Optional[Dict[str, Any]] = None

@router.post(
    "/internal/query",
    summary="Consulta RAG interna",
    description="Endpoint para uso exclusivo del Agent Service"
)
@with_context(tenant=True, collection=True, agent=True, conversation=True)
@handle_service_error_simple
async def internal_query(
    request: InternalQueryRequest = Body(...)
):
    """
    Procesa una consulta RAG para uso interno del Agent Service.
    
    Este endpoint está optimizado para ser consumido por el servicio de agentes
    y proporciona respuestas RAG para uso como herramienta.
    
    Args:
        request: Solicitud de consulta interna
        
    Returns:
        Dict con formato estandarizado:
        {
            "success": bool,           # Éxito/fallo de la operación
            "message": str,            # Mensaje descriptivo
            "data": Any,               # Datos principales (respuesta RAG y fuentes)
            "metadata": Dict[str, Any] # Metadatos adicionales
            "error": Dict[str, Any]    # Presente solo en caso de error
        }
    """
    # Establecer contexto explícitamente basado en la solicitud
    tenant_id = request.tenant_id
    
    # Obtener tiempo de inicio para medición
    start_time = time.time()
    
    try:
        # Crear tenant_info mínima para el motor de consulta
        tenant_info = TenantInfo(tenant_id=tenant_id)
        
        # Crear motor de consulta
        query_engine, debug_handler = await create_query_engine(
            tenant_info=tenant_info,
            collection_id=request.collection_id,
            llm_model=request.llm_model,
            similarity_top_k=request.similarity_top_k,
            response_mode=request.response_mode
        )
        
        # Procesar consulta
        result = await process_query_with_sources(
            query_engine=query_engine,
            debug_handler=debug_handler,
            query=request.query,
            filters=request.context_filter
        )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Limitar fuentes si se especifica
        sources = result.get("sources", [])
        if request.max_sources > 0 and len(sources) > request.max_sources:
            sources = sources[:request.max_sources]
        
        # Registrar uso de tokens para facturación
        await track_query(
            tenant_id=tenant_id,
            operation_type="agent_tool_query",
            model=result.get("model", request.llm_model),
            tokens_in=result.get("tokens_in", 0),
            tokens_out=result.get("tokens_out", 0),
            agent_id=request.agent_id,
            conversation_id=request.conversation_id
        )
        
        # Construir respuesta en formato estandarizado
        response_data = {
            "response": result["response"]
        }
        
        # Incluir fuentes solo si se solicitan
        if request.include_sources:
            response_data["sources"] = sources
        
        return {
            "success": True,
            "message": "Consulta RAG procesada correctamente",
            "data": response_data,
            "metadata": {
                "processing_time": processing_time,
                "model": result["model"],
                "tokens_total": result.get("tokens_total", 0),
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
                "similarity_top_k": request.similarity_top_k,
                "response_mode": request.response_mode,
                "collection_id": request.collection_id,
                "timestamp": time.time()
            }
        }
        
    except Exception as e:
        logger.error(f"Error procesando consulta interna: {str(e)}")
        
        # Si es un error genérico, convertirlo a un tipo específico
        if not isinstance(e, ServiceError):
            # Verificar primero si es un error relacionado con embeddings
            if "embedding" in str(e).lower() or isinstance(e, (EmbeddingGenerationError, EmbeddingModelError, TextTooLargeError)):
                # Manejar errores específicos del servicio de embeddings
                if isinstance(e, EmbeddingGenerationError):
                    specific_error = e  # Mantener el error original
                elif isinstance(e, EmbeddingModelError):
                    specific_error = e  # Mantener el error original
                elif isinstance(e, TextTooLargeError):
                    specific_error = e  # Mantener el error original
                else:
                    # Si es un error genérico relacionado con embeddings
                    specific_error = EmbeddingGenerationError(
                        message=f"Error generando embeddings para la consulta: {str(e)}",
                        details={
                            "query": request.query,
                            "collection_id": request.collection_id,
                            "query_length": len(request.query) if request.query else 0
                        }
                    )
            else:
                specific_error = QueryProcessingError(
                    message=f"Error procesando consulta RAG: {str(e)}",
                    details={
                        "query": request.query,
                        "collection_id": request.collection_id,
                        "similarity_top_k": request.similarity_top_k,
                        "response_mode": request.response_mode
                    }
                )
        else:
            specific_error = e
        
        # Construir respuesta de error estandarizada según el patrón de comunicación
        error_response = {
            "success": False,
            "message": specific_error.message,
            "data": None,
            "metadata": {
                "query": request.query,
                "collection_id": request.collection_id,
                "timestamp": time.time()
            },
            "error": {
                "message": specific_error.message,
                "details": {
                    "error_type": specific_error.__class__.__name__,
                    "error_code": specific_error.error_code
                },
                "timestamp": time.time()
            }
        }
        
        return error_response

@router.post(
    "/internal/search",
    summary="Búsqueda interna para otros servicios",
    description="Endpoint para búsqueda rápida entre documentos, para uso exclusivo de otros servicios"
)
@with_context(tenant=True, collection=True, agent=True, conversation=True)
@handle_service_error_simple
async def internal_search(
    request: InternalSearchRequest = Body(...)
):
    """
    Procesa una búsqueda rápida para uso interno de otros servicios.
    Devuelve documentos relevantes sin generar una respuesta.
    
    Args:
        request: Detalles de la búsqueda a realizar
        
    Returns:
        Dict: Resultados de la búsqueda en formato estandarizado
    """
    # Registrar solicitud
    start_time = time.time()
    
    # Validar tenant
    tenant_id = request.tenant_id
    tenant_info = await verify_tenant(tenant_id)
    
    try:
        # Crear motor de consulta
        query_engine = await create_query_engine(
            tenant_info=tenant_info, 
            collection_id=request.collection_id
        )
        
        # Realizar búsqueda simple
        results = await query_engine.similarity_search(
            query=request.query,
            k=request.limit,
            context_filter=request.context_filter
        )
        
        # Formatear resultados
        formatted_results = []
        for node in results:
            formatted_results.append({
                "text": node.text,
                "metadata": node.metadata,
                "score": node.score if hasattr(node, "score") else 1.0,
                "id": node.id if hasattr(node, "id") else "unknown"
            })
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Devolver respuesta en formato estandarizado
        return {
            "success": True,
            "message": "Búsqueda procesada correctamente",
            "data": {
                "results": formatted_results
            },
            "metadata": {
                "processing_time": processing_time,
                "count": len(formatted_results),
                "collection_id": request.collection_id,
                "query": request.query,
                "timestamp": time.time()
            }
        }
    except Exception as e:
        logger.error(f"Error procesando búsqueda interna: {str(e)}")
        
        # Si es un error genérico, convertirlo a un tipo específico
        if not isinstance(e, ServiceError):
            if "not found" in str(e).lower() or "no encontrada" in str(e).lower():
                specific_error = CollectionNotFoundError(
                    message=f"Colección no encontrada: {request.collection_id}",
                    details={
                        "query": request.query,
                        "collection_id": request.collection_id,
                        "tenant_id": tenant_id
                    }
                )
            elif "embedding" in str(e).lower() or isinstance(e, (EmbeddingGenerationError, EmbeddingModelError, TextTooLargeError)):
                # Manejar errores específicos del servicio de embeddings
                if isinstance(e, EmbeddingGenerationError):
                    specific_error = e  # Mantener el error original
                elif isinstance(e, EmbeddingModelError):
                    specific_error = e  # Mantener el error original
                elif isinstance(e, TextTooLargeError):
                    specific_error = e  # Mantener el error original
                else:
                    # Si es un error genérico relacionado con embeddings
                    specific_error = EmbeddingGenerationError(
                        message=f"Error generando embeddings para la búsqueda: {str(e)}",
                        details={
                            "query": request.query,
                            "collection_id": request.collection_id,
                            "query_length": len(request.query) if request.query else 0
                        }
                    )
            else:
                specific_error = RetrievalError(
                    message=f"Error recuperando documentos: {str(e)}",
                    details={
                        "query": request.query,
                        "collection_id": request.collection_id,
                        "limit": request.limit
                    }
                )
        else:
            specific_error = e
        
        # Construir respuesta de error estandarizada según el patrón de comunicación
        error_response = {
            "success": False,
            "message": specific_error.message,
            "data": [],
            "metadata": {
                "query": request.query,
                "collection_id": request.collection_id,
                "limit": request.limit,
                "timestamp": time.time()
            },
            "error": {
                "message": specific_error.message,
                "details": {
                    "error_type": specific_error.__class__.__name__,
                    "error_code": specific_error.error_code
                },
                "timestamp": time.time()
            }
        }
        
        return error_response