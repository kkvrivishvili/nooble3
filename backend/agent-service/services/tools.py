"""
Funciones para crear y gestionar herramientas para agentes LLM.
"""

import logging
import hashlib
from typing import Dict, Any, List, Optional, Union

from langchain.tools import Tool

from common.config import get_settings
from common.context import with_context, set_current_collection_id, get_current_conversation_id
from common.utils.http import call_service_with_context
from common.errors import ServiceError
from common.cache.manager import CacheManager

logger = logging.getLogger(__name__)
settings = get_settings()

@with_context(tenant=True, agent=True, collection=True)
async def create_rag_tool(tool_config: Dict[str, Any], tenant_id: str, agent_id: Optional[str] = None) -> Tool:
    """
    Crea una herramienta RAG que consulta una colección específica.
    """
    # Extraer configuración de la herramienta
    tool_name = tool_config.get("name", "search_documents")
    tool_description = tool_config.get("description", "Busca información en documentos para responder preguntas.")
    metadata = tool_config.get("metadata", {})
    
    collection_id = metadata.get("collection_id")
    collection_name = metadata.get("collection_name", "default")
    similarity_top_k = metadata.get("similarity_top_k", 4)
    response_mode = metadata.get("response_mode", "compact")
    
    # Establecer ID de colección en el contexto si está disponible
    if collection_id:
        set_current_collection_id(str(collection_id))
    
    async def query_tool(query: str) -> str:
        """Herramienta para consultar documentos usando RAG."""
        logger.info(f"RAG consulta: {query}")
        
        # Verificar caché para esta consulta específica
        cached_result = await CacheManager.get_rag_result(
            query=query,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
            similarity_top_k=similarity_top_k,
            response_mode=response_mode
        )
        
        if cached_result:
            logger.info(f"Resultado RAG obtenido de caché para consulta: {query[:30]}...")
            return cached_result
        
        try:
            # Usar el endpoint interno del Query Service
            # Usar timeout extendido para consultas RAG
            response = await call_service_with_context(
                url=f"{settings.query_service_url}/internal/query",
                data={
                    "tenant_id": tenant_id,
                    "query": query,
                    "collection_id": collection_id,
                    "agent_id": agent_id,
                    "conversation_id": get_current_conversation_id(),
                    "similarity_top_k": similarity_top_k,
                    "response_mode": response_mode,
                    "llm_model": None,  # Usar modelo determinado por Query Service
                    "include_sources": True
                },
                tenant_id=tenant_id,
                agent_id=agent_id,
                collection_id=collection_id,
                operation_type="rag_query"  # Usar tipo de operación para timeout adaptado
            )
            
            # Preparar respuesta
            if not response.get("success", False):
                error_msg = response.get("message", "Error desconocido en consulta RAG")
                logger.error(f"Error en consulta RAG: {error_msg}")
                return f"Error consultando documentos: {error_msg}"
            
            rag_response = response.get("response", "")
            sources = response.get("sources", [])
            
            # Formatear fuentes si están disponibles
            if sources:
                rag_response += "\n\nFuentes:"
                for i, source in enumerate(sources, 1):
                    source_text = source.get("text", "")
                    source_metadata = source.get("metadata", {})
                    source_name = source_metadata.get("source") or source_metadata.get("filename", f"Fuente {i}")
                    rag_response += f"\n[{i}] {source_name}: {source_text[:200]}..."
            
            # Cachear el resultado formateado
            await CacheManager.set_rag_result(
                query=query,
                result=rag_response,
                tenant_id=tenant_id,
                agent_id=agent_id,
                collection_id=collection_id,
                similarity_top_k=similarity_top_k,
                response_mode=response_mode,
                ttl=1800
            )
            
            return rag_response
                
        except Exception as e:
            logger.error(f"Error ejecutando herramienta RAG: {str(e)}", exc_info=True)
            return f"Error consultando documentos: {str(e)}"
    
    # Crear herramienta LangChain con la función RAG
    return Tool(
        name=tool_name,
        description=tool_description,
        func=query_tool
    )

# Solo implementamos las funciones para colecciones si Query Service está disponible
async def get_available_collections(tenant_id: str) -> List[Dict[str, Any]]:
    """Obtiene las colecciones disponibles para un tenant."""
    try:
        response = await call_service_with_context(
            url=f"{settings.query_service_url}/collections",
            data={},
            tenant_id=tenant_id,
            operation_type="health_check"  # Uso de timeout corto para consulta rápida
        )
        
        if not response.get("success", False):
            logger.warning(f"Error obteniendo colecciones: {response.get('message')}")
            return []
        
        return response.get("collections", [])
    except Exception as e:
        logger.warning(f"Error obteniendo colecciones: {str(e)}")
        return []