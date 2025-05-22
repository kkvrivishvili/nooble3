"""
Endpoints internos para Agent Service.
"""

import logging
import time
from fastapi import APIRouter, Body

from models.query import InternalQueryRequest, InternalSearchRequest, QueryResponse
from services.query_processor import process_rag_query, search_documents
from common.errors import handle_errors, ServiceError
from common.context import with_context, Context
from common.tracking import track_token_usage, TOKEN_TYPE_LLM, OPERATION_QUERY

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/internal/query", response_model=QueryResponse)
@handle_errors(error_type="service", log_traceback=True)
@with_context
async def internal_query(
    request: InternalQueryRequest = Body(...),
    ctx: Context = None
) -> QueryResponse:
    """
    Procesa consulta RAG con embedding pre-calculado.
    """
    start_time = time.time()
    
    try:
        # Procesar consulta
        result = await process_rag_query(
            query=request.query,
            query_embedding=request.query_embedding,
            tenant_id=request.tenant_id,
            collection_id=request.collection_id,
            agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            similarity_top_k=request.similarity_top_k,
            llm_model=request.llm_model,
            include_sources=request.include_sources,
            # Nuevos parámetros para manejo de fallback
            agent_description=request.agent_description,
            fallback_behavior=request.fallback_behavior,
            relevance_threshold=request.relevance_threshold
        )
        
        # Limitar fuentes si es necesario
        if request.max_sources and len(result['sources']) > request.max_sources:
            result['sources'] = result['sources'][:request.max_sources]
        
        return QueryResponse(
            success=True,
            message="Consulta procesada correctamente",
            data={
                "query": request.query,
                "response": result['response'],
                "sources": result['sources']
            },
            metadata={
                **result['metadata'],
                "total_time": time.time() - start_time,
                "agent_id": request.agent_id,
                "conversation_id": request.conversation_id
            }
        )
        
    except Exception as e:
        logger.error(f"Error en consulta: {str(e)}")
        return QueryResponse(
            success=False,
            message="Error procesando consulta",
            data={},
            metadata={"error_time": time.time() - start_time},
            error={
                "type": type(e).__name__,
                "message": str(e)
            }
        )

@router.post("/internal/search", response_model=QueryResponse)
@handle_errors(error_type="service", log_traceback=True)
@with_context
async def internal_search(
    request: InternalSearchRequest = Body(...),
    ctx: Context = None
) -> QueryResponse:
    """
    Busca documentos sin generar respuesta.
    """
    start_time = time.time()
    
    try:
        # Buscar documentos
        documents = await search_documents(
            query_embedding=request.query_embedding,
            tenant_id=request.tenant_id,
            collection_id=request.collection_id,
            limit=request.limit,
            threshold=request.similarity_threshold
        )
        
        return QueryResponse(
            success=True,
            message="Búsqueda completada",
            data={
                "documents": [doc.dict() for doc in documents],
                "count": len(documents)
            },
            metadata={
                "search_time": time.time() - start_time
            }
        )
        
    except Exception as e:
        logger.error(f"Error en búsqueda: {str(e)}")
        return QueryResponse(
            success=False,
            message="Error en búsqueda",
            data={},
            metadata={"error_time": time.time() - start_time},
            error={
                "type": type(e).__name__,
                "message": str(e)
            }
        )
