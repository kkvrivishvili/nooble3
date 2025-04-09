"""
Funciones para crear y gestionar herramientas para agentes LLM.
"""

import logging
from typing import Dict, Any, List, Optional, Callable

from fastapi import HTTPException
from pydantic import BaseModel

from common.settings import Settings
from common.context import get_current_conversation_id
from common.utils.http import call_service

settings = Settings()
logger = logging.getLogger(__name__)

async def create_rag_tool(tool_config: Dict[str, Any], tenant_id: str, agent_id: Optional[str] = None) -> Callable:
    """
    Crea una herramienta RAG que consulta una colección específica.
    
    Args:
        tool_config: Configuración de la herramienta
        tenant_id: ID del tenant
        agent_id: ID del agente (opcional)
        
    Returns:
        Callable: Función que puede ser usada como herramienta por un agente
    """
    collection_id = tool_config.get("collection_id")
    collection_name = tool_config.get("collection_name", "Documentos")
    description = tool_config.get("description", f"Busca información en {collection_name}")
    similarity_top_k = tool_config.get("similarity_top_k", 4)
    response_mode = tool_config.get("response_mode", "compact")
    
    if not collection_id:
        logger.error("No se puede crear herramienta RAG sin collection_id")
        # Crear una función dummy que devuelve un mensaje de error
        async def dummy_rag_tool(query: str) -> str:
            return "Error: Herramienta mal configurada. Contacte al administrador."
        return dummy_rag_tool
    
    logger.info(f"Creando herramienta RAG para collection_id={collection_id}")
    
    # Definición de la función de herramienta
    async def rag_query_tool(query: str) -> str:
        """
        Consulta documentos relevantes y genera una respuesta basada en ellos.
        
        Args:
            query: Consulta del usuario
            
        Returns:
            str: Respuesta basada en los documentos relevantes
        """
        logger.debug(f"Ejecutando consulta RAG: '{query}' en collection={collection_id}")
        
        try:
            # Usar el endpoint interno del Query Service
            # Usar timeout extendido para consultas RAG
            response = await call_service(
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
            
            # Verificar éxito de la operación
            if not response.get("success", False):
                error_msg = response.get("message", "Error desconocido en consulta RAG")
                logger.error(f"Error en consulta RAG: {error_msg}")
                return f"Error consultando documentos: {error_msg}"
            
            # Extraer datos de la respuesta estandarizada
            response_data = response.get("data", {})
            rag_response = response_data.get("response", "")
            sources = response_data.get("sources", [])
            
            # Formatear fuentes si están disponibles
            if sources:
                rag_response += "\n\nFuentes:"
                for i, source in enumerate(sources, 1):
                    metadata = source.get("metadata", {})
                    title = metadata.get("title", "Documento sin título")
                    url = metadata.get("url", "")
                    file_path = metadata.get("file_path", "")
                    
                    source_ref = f"\n{i}. {title}"
                    if url:
                        source_ref += f" - {url}"
                    elif file_path:
                        source_ref += f" - {file_path}"
                    
                    rag_response += source_ref
            
            return rag_response
            
        except Exception as e:
            logger.exception(f"Error ejecutando herramienta RAG: {str(e)}")
            return f"Error consultando documentos: {str(e)}"
    
    # Añadir metadatos a la función
    rag_query_tool.__name__ = f"search_{collection_id}"
    rag_query_tool.__description__ = description
    
    return rag_query_tool

# Solo implementamos las funciones para colecciones si Query Service está disponible
async def get_available_collections(tenant_id: str) -> List[Dict[str, Any]]:
    """Obtiene las colecciones disponibles para un tenant."""
    try:
        response = await call_service(
            url=f"{settings.query_service_url}/collections",
            data={},
            tenant_id=tenant_id,
            operation_type="health_check"  # Uso de timeout corto para consulta rápida
        )
        
        # Verificar éxito de la operación
        if not response.get("success", False):
            logger.warning(f"Error obteniendo colecciones: {response.get('message')}")
            return []
        
        # Extraer datos de la respuesta estandarizada
        response_data = response.get("data", {})
        return response_data.get("collections", [])
    except Exception as e:
        logger.warning(f"Error obteniendo colecciones: {str(e)}")
        return []