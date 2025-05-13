"""
Herramientas RAG (Retrieval Augmented Generation) para consultar documentos.
"""

import logging
from typing import Dict, Any, List, Optional

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError
from common.tracking import track_token_usage

from config import get_settings
from config.constants import TOKEN_TYPE_LLM, OPERATION_AGENT_RAG
from services.service_registry import ServiceRegistry
from tools.base import BaseTool

logger = logging.getLogger(__name__)


class RAGQueryTool(BaseTool):
    """Herramienta para consultar colecciones de documentos mediante RAG."""
    
    name = "rag_query"
    description = "Consulta una colección de documentos y genera una respuesta basada en ellos. Útil para obtener información específica de una colección de documentos."
    collection_id: str
    similarity_top_k: int = 4
    
    class Config:
        arbitrary_types_allowed = True
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(
        self, 
        query: str,
        similarity_top_k: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Consulta la colección y genera una respuesta.
        
        Args:
            query: Texto de la consulta
            similarity_top_k: Número de documentos a recuperar
            
        Returns:
            str: Respuesta generada basada en los documentos
        """
        # Usar service registry para llamar al servicio de consulta
        service_registry = ServiceRegistry()
        top_k = similarity_top_k or self.similarity_top_k
        
        # Validar el tenant_id
        if not self.tenant_id:
            return "Error: Se requiere tenant_id para realizar consultas RAG."
        
        try:
            # Llamar al endpoint de consulta RAG
            response = await service_registry.call_query_service(
                endpoint="internal/query",
                method="POST",
                data={
                    "query": query,
                    "collection_id": self.collection_id,
                    "similarity_top_k": top_k
                },
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                ctx=self.ctx
            )
            
            # Procesar la respuesta
            if not response.get("success", False):
                error_msg = response.get("error", {}).get("message", "Unknown error")
                return f"Error querying collection: {error_msg}"
                
            # Extraer respuesta y metadatos
            answer = response.get("data", {}).get("response", "")
            sources = response.get("data", {}).get("sources", [])
            token_usage = response.get("data", {}).get("token_usage", {})
            
            # Realizar tracking de tokens si está disponible
            if token_usage and "total_tokens" in token_usage:
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=token_usage.get("total_tokens", 0),
                    model=token_usage.get("model", "unknown"),
                    agent_id=self.agent_id,
                    conversation_id=self.conversation_id,
                    collection_id=self.collection_id,
                    token_type=TOKEN_TYPE_LLM,
                    operation=OPERATION_AGENT_RAG,
                    metadata={
                        "query": query,
                        "similarity_top_k": top_k,
                        "sources_count": len(sources)
                    }
                )
                
            # Formatear fuentes para la respuesta
            if sources and len(sources) > 0:
                source_text = "\n\nFuentes:\n"
                for i, source in enumerate(sources, 1):
                    source_text += f"{i}. {source.get('document_name', 'Unknown')} ({source.get('score', 0):.2f})\n"
                answer += source_text
                
            return answer
            
        except Exception as e:
            logger.error(f"Error in RAG query: {str(e)}")
            return f"Error querying documents: {str(e)}"


class RAGSearchTool(BaseTool):
    """Herramienta para buscar documentos en una colección."""
    
    name = "rag_search"
    description = "Busca documentos en una colección y devuelve los resultados más relevantes. Útil para explorar qué documentos están disponibles antes de hacer una consulta específica."
    collection_id: str
    limit: int = 5
    
    class Config:
        arbitrary_types_allowed = True
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(
        self, 
        query: str,
        limit: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Busca documentos en la colección.
        
        Args:
            query: Texto de la búsqueda
            limit: Número máximo de resultados
            
        Returns:
            str: Resultados de la búsqueda formateados
        """
        # Usar service registry para llamar al servicio de consulta
        service_registry = ServiceRegistry()
        result_limit = limit or self.limit
        
        # Validar el tenant_id
        if not self.tenant_id:
            return "Error: Se requiere tenant_id para realizar búsquedas RAG."
        
        try:
            # Llamar al endpoint de búsqueda
            response = await service_registry.call_query_service(
                endpoint="internal/search",
                method="POST",
                data={
                    "query": query,
                    "collection_id": self.collection_id,
                    "limit": result_limit
                },
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                ctx=self.ctx
            )
            
            # Procesar la respuesta
            if not response.get("success", False):
                error_msg = response.get("error", {}).get("message", "Unknown error")
                return f"Error searching collection: {error_msg}"
                
            # Extraer resultados
            results = response.get("data", {}).get("results", [])
            
            # Formatear resultados
            if not results:
                return "No se encontraron documentos que coincidan con la consulta."
                
            formatted_results = "Resultados de la búsqueda:\n\n"
            
            for i, doc in enumerate(results, 1):
                title = doc.get("document_name", "Documento sin título")
                snippet = doc.get("text", "No hay contenido disponible.")[:200] + "..."
                score = doc.get("score", 0)
                
                formatted_results += f"{i}. {title} (Score: {score:.2f})\n"
                formatted_results += f"   {snippet}\n\n"
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error in RAG search: {str(e)}")
            return f"Error searching documents: {str(e)}"
