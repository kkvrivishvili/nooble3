"""
Endpoints internos para uso exclusivo de otros servicios (principalmente Agent Service).
"""

import time
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel, Field

from common.models import TenantInfo, QueryContextItem
from common.errors import ServiceError, handle_service_error_simple
from common.context import with_context, get_current_tenant_id, set_current_collection_id
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
@handle_service_error_simple
@with_context(tenant=True, collection=True, agent=True, conversation=True)
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
    set_current_collection_id(request.collection_id)
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
        
        # Construir respuesta de error estandarizada
        error_response = {
            "success": False,
            "message": f"Error procesando consulta RAG: {str(e)}",
            "data": None,
            "metadata": {
                "query": request.query,
                "collection_id": request.collection_id,
                "timestamp": time.time()
            },
            "error": {
                "message": str(e),
                "details": {
                    "error_type": e.__class__.__name__,
                    "error_code": getattr(e, "error_code", "INTERNAL_QUERY_ERROR") if isinstance(e, ServiceError) else "INTERNAL_QUERY_ERROR"
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
@handle_service_error_simple
@with_context(tenant=True, collection=True, agent=True, conversation=True)
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
    
    # Establecer ID de colección en el contexto
    set_current_collection_id(request.collection_id)
    
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
        logger.error(f"Error en internal_search: {str(e)}")
        return {
            "success": False,
            "message": f"Error en búsqueda: {str(e)}",
            "data": None,
            "metadata": {
                "processing_time": time.time() - start_time,
                "error_type": type(e).__name__
            },
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }