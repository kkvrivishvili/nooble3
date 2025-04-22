"""
Funciones para crear y gestionar herramientas para agentes LLM.
"""

import logging
from typing import Dict, Any, List, Optional, Callable

from fastapi import HTTPException
from pydantic import BaseModel

from common.config import get_settings
from common.context import with_context, Context, get_current_conversation_id
from common.utils.http import call_service
from common.cache import (
    get_with_cache_aside,
    generate_resource_id_hash,
    track_cache_metrics,
    serialize_for_cache,
    deserialize_from_cache
)
from common.errors import (
    CollectionNotFoundError,
    RetrievalError,
    QueryProcessingError,
    ServiceError,
    ErrorCode,
    handle_errors
)

settings = get_settings()
logger = logging.getLogger(__name__)

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
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
                error_info = response.get("error", {})
                error_msg = response.get("message", "Error desconocido en consulta RAG")
                error_code = error_info.get("details", {}).get("error_code", ErrorCode.QUERY_PROCESSING_ERROR)
                error_details = error_info.get("details", {})
                
                logger.error(f"Error en consulta RAG: {error_msg} (código: {error_code})")
                
                # Convertir a error específico basado en el código de error
                if error_code == ErrorCode.COLLECTION_NOT_FOUND:
                    raise CollectionNotFoundError(
                        message=f"Colección no encontrada: {collection_id}",
                        details=error_details
                    )
                elif error_code == ErrorCode.RETRIEVAL_ERROR:
                    raise RetrievalError(
                        message=f"Error recuperando documentos: {error_msg}",
                        details=error_details
                    )
                elif error_code == ErrorCode.QUERY_PROCESSING_ERROR:
                    raise QueryProcessingError(
                        message=f"Error procesando consulta RAG: {error_msg}",
                        details=error_details
                    )
                else:
                    # Error genérico si no podemos mapear a uno específico
                    raise ServiceError(
                        message=f"Error en servicio de consultas: {error_msg}",
                        error_code=error_code,
                        details=error_details
                    )
            
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
            
            # Manejo más específico según el tipo de error
            if isinstance(e, CollectionNotFoundError):
                return f"No se encuentra la colección de documentos '{collection_id}'. Por favor, verifica que el ID de colección sea correcto."
            elif isinstance(e, RetrievalError):
                return f"Error recuperando documentos: {e.message}"
            elif isinstance(e, QueryProcessingError):
                return f"Error procesando tu consulta: {e.message}"
            elif isinstance(e, ServiceError):
                return f"Error en el servicio de consultas: {e.message}"
            else:
                return f"Error consultando documentos: {str(e)}"
    
    # Añadir metadatos a la función
    rag_query_tool.__name__ = f"search_{collection_id}"
    rag_query_tool.__description__ = description
    
    return rag_query_tool

@with_context(tenant=True, agent=True)
@handle_errors(error_type="service", log_traceback=True)
async def create_agent_tools(agent_config: Dict[str, Any], tenant_id: str, agent_id: str) -> List[Callable]:
    """
    Crea todas las herramientas para un agente basado en su configuración.
    
    Args:
        agent_config: Configuración completa del agente
        tenant_id: ID del tenant
        agent_id: ID del agente
        
    Returns:
        List[Callable]: Lista de herramientas disponibles para el agente
    """
    # Inicializar lista de herramientas
    tools = []
    
    # Obtener configuración de herramientas del agente
    tools_config = agent_config.get("tools", [])
    
    for tool_config in tools_config:
        tool_type = tool_config.get("type")
        
        # Crear herramienta RAG si está configurada
        if tool_type == "rag":
            collection_id = tool_config.get("metadata", {}).get("collection_id")
            if collection_id:
                try:
                    rag_tool = await create_rag_tool(
                        tool_config=tool_config.get("metadata", {}),
                        tenant_id=tenant_id,
                        agent_id=agent_id
                    )
                    tools.append(rag_tool)
                except Exception as e:
                    logger.warning(f"Error creando herramienta RAG para colección {collection_id}: {str(e)}")
    
    # Si no hay herramientas configuradas, devolver una lista vacía
    if not tools:
        logger.info(f"No se encontraron herramientas configuradas para el agente {agent_id}")
        
    return tools

# Solo implementamos las funciones para colecciones si Query Service está disponible
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def get_available_collections(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene las colecciones disponibles para un tenant implementando el patrón Cache-Aside.
    
    Args:
        tenant_id: ID del tenant
        
    Returns:
        List[Dict[str, Any]]: Lista de colecciones disponibles
    """
    # Definir el tipo de datos y resource_id
    data_type = "collection_list"
    resource_id = "available_collections"
    
    # Función para buscar en Supabase (en este caso, llamada al servicio query)
    async def fetch_collections_from_service(resource_id, tenant_id, ctx):
        try:
            response = await call_service(
                url=f"{settings.query_service_url}/collections",
                method="GET",
                headers={},
                tenant_id=tenant_id,
                include_context=True,
                operation_type="query" 
            )
            
            # Verificar éxito de la operación
            if not response.get("success", False):
                error_info = response.get("error", {})
                error_msg = error_info.get("message", "Error desconocido obteniendo colecciones")
                error_code = error_info.get("code", ErrorCode.GENERAL_ERROR)
                
                logger.warning(f"Error obteniendo colecciones: {error_msg} (código: {error_code})")
                return None
            
            # Extraer datos de la respuesta estandarizada
            return response.get("data", {}).get("collections", [])
        except Exception as e:
            logger.warning(f"Error obteniendo colecciones: {str(e)}")
            return None
    
    # No necesitamos función de generación, solo obtenemos desde el servicio
    async def generate_collections(resource_id, tenant_id, ctx):
        return None
    
    # Implementar patrón Cache-Aside usando la función centralizada
    collections, metrics = await get_with_cache_aside(
        data_type=data_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_collections_from_service,
        generate_func=generate_collections,
        # TTL se determina automáticamente por el tipo de datos
    )
    
    # Retornar colecciones o lista vacía si no hay
    return collections or []