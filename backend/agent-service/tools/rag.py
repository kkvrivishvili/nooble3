"""
Herramientas RAG (Retrieval Augmented Generation) para consultar documentos.

Este módulo proporciona herramientas para interactuar con el sistema RAG,
permitiendo realizar consultas sobre colecciones de documentos y buscar
información relevante utilizando modelos estandarizados.
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Union

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError
from common.tracking import track_token_usage
from common.cache import CacheManager

from config import get_settings
from config.constants import TOKEN_TYPE_LLM, OPERATION_AGENT_RAG

# Constantes adicionales para tracking
OPERATION_AGENT_RAG_SEARCH = "agent_rag_search"

from services.service_registry import ServiceRegistry
from tools.base import BaseTool, ToolResult
from models import (
    RAGQueryInput, RAGQueryOutput, RAGQuerySource,
    ToolExecutionMetadata, CollectionSelectionResult,
    SelectionCriteria, StrategyType, CollectionSource
)

logger = logging.getLogger(__name__)


class RAGQueryTool(BaseTool):
    """Herramienta para consultar colecciones de documentos mediante RAG."""
    
    name = "rag_query"
    description = "Consulta una colección de documentos y genera una respuesta basada en ellos. Útil para obtener información específica de una colección de documentos."
    collection_id: str
    similarity_top_k: int = 4
    threshold: float = 0.7
    include_metadata: bool = True
    include_sources: bool = True
    metadata_fields: Optional[List[str]] = None
    cached_responses: bool = True
    
    # Variables para tracking interno
    _execution_metadata: Optional[ToolExecutionMetadata] = None
    
    class Config:
        arbitrary_types_allowed = True
        
    @handle_errors(error_type="service", log_traceback=True)
    async def execute(
        self, 
        parameters: Dict[str, Any],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ctx: Optional[Context] = None
    ) -> ToolResult:
        """
        Ejecuta la herramienta con parámetros estandarizados.
        
        Args:
            parameters: Parámetros para la herramienta
            tenant_id: ID del tenant
            agent_id: ID del agente 
            conversation_id: ID de la conversación
            ctx: Contexto de la operación
            
        Returns:
            ToolResult: Resultado de la ejecución con datos tipados
        """
        # Asignar contexto
        self.tenant_id = tenant_id or (ctx.get_tenant_id(validate=True) if ctx else None)
        if not self.tenant_id:
            return ToolResult(
                success=False,
                error="Se requiere tenant_id para ejecutar herramientas RAG",
                execution_time=0.0,
                metadata={"tool_name": self.name}
            )
            
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.ctx = ctx
        
        # Extraer parámetros para la consulta
        query = parameters.get("query")
        if not query:
            return ToolResult(
                success=False,
                error="Se requiere un parámetro 'query' para la consulta RAG",
                execution_time=0.0,
                metadata={
                    "tool_name": self.name,
                    "collection_id": self.collection_id
                }
            )
            
        # Resto de parámetros opcionales
        similarity_top_k = parameters.get("similarity_top_k", None)
        threshold = parameters.get("threshold", None)
        include_sources = parameters.get("include_sources", None)
        
        # Iniciar tracking de ejecución
        start_time = time.time()
        execution_id = str(uuid.uuid4())
        
        self._execution_metadata = ToolExecutionMetadata(
            tool_name=self.name,
            execution_id=execution_id,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            operation=OPERATION_AGENT_RAG,
            start_time=start_time,
            parameters={
                "query": query,
                "collection_id": self.collection_id,
                "top_k": similarity_top_k or self.similarity_top_k,
                "threshold": threshold or self.threshold
            }
        )
        
        # Ejecutar la herramienta
        try:
            result = await self._arun(
                query=query,
                similarity_top_k=similarity_top_k,
                threshold=threshold,
                include_sources=include_sources
            )
            
            # Calcular tiempo de ejecución
            execution_time = time.time() - start_time
            
            # Actualizar metadatos de ejecución
            self._execution_metadata.end_time = time.time()
            self._execution_metadata.success = True
            self._execution_metadata.execution_time = execution_time
            
            # Construir ToolResult
            return ToolResult(
                success=True,
                data=result,
                execution_time=execution_time,
                metadata={
                    "tool_name": self.name,
                    "collection_id": self.collection_id,
                    "execution_id": execution_id,
                    "similarity_top_k": similarity_top_k or self.similarity_top_k,
                    "threshold": threshold or self.threshold,
                    "token_usage": self._execution_metadata.token_usage
                }
            )
        except Exception as e:
            # Calcular tiempo de ejecución
            execution_time = time.time() - start_time
            
            # Actualizar metadatos de ejecución
            if self._execution_metadata:
                self._execution_metadata.end_time = time.time()
                self._execution_metadata.success = False
                self._execution_metadata.error = str(e)
                self._execution_metadata.execution_time = execution_time
            
            logger.error(f"Error ejecutando RAGQueryTool: {str(e)}")
            
            # Construir ToolResult con error
            return ToolResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
                metadata={
                    "tool_name": self.name,
                    "collection_id": self.collection_id,
                    "execution_id": execution_id
                }
            )
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(
        self, 
        query: str,
        similarity_top_k: Optional[int] = None,
        threshold: Optional[float] = None,
        include_sources: Optional[bool] = None,
        **kwargs
    ) -> str:
        """
        Consulta la colección y genera una respuesta.
        
        Args:
            query: Texto de la consulta
            similarity_top_k: Número de documentos a recuperar
            threshold: Umbral de similitud para considerar relevante un documento
            include_sources: Si se deben incluir las fuentes en la respuesta
            
        Returns:
            str: Respuesta generada basada en los documentos
        """
        # Crear objeto de entrada estandarizado
        input_data = RAGQueryInput(
            query=query,
            collection_id=self.collection_id,
            top_k=similarity_top_k or self.similarity_top_k,
            threshold=threshold or self.threshold,
            include_metadata=self.include_metadata,
            include_sources=include_sources if include_sources is not None else self.include_sources,
            metadata_fields=self.metadata_fields,
            cache_results=self.cached_responses
        )
        
        # Generar metadatos de ejecución 
        execution_metadata = ToolExecutionMetadata(
            tool_name=self.name,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            operation=OPERATION_AGENT_RAG,
            start_time=time.time()
        )
        
        # Validar el tenant_id
        if not self.tenant_id:
            return "Error: Se requiere tenant_id para realizar consultas RAG."
        
        try:
            # Usar service registry para llamar al servicio de consulta
            service_registry = ServiceRegistry()
            
            # Crear clave para caché
            cache_key = f"rag_query:{self.collection_id}:{query}:{input_data.top_k}"
            
            # Llamar al endpoint de consulta RAG
            response = await service_registry.call_query_service(
                endpoint="internal/query",
                method="POST",
                data=input_data.dict(),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                ctx=self.ctx,
                idempotency_key=cache_key if input_data.cache_results else None
            )
            
            # Procesar la respuesta
            if not response.get("success", False):
                error_msg = response.get("error", {}).get("message", "Unknown error")
                return f"Error querying collection: {error_msg}"
                
            # Convertir respuesta al modelo estandarizado
            data = response.get("data", {})
            
            # Mapear sources a objetos tipados
            sources = []
            for source_data in data.get("sources", []):
                source = RAGQuerySource(
                    document_id=source_data.get("document_id", ""),
                    chunk_id=source_data.get("chunk_id", ""),
                    title=source_data.get("title", ""),
                    url=source_data.get("url"),
                    content_preview=source_data.get("content", "")[:200],
                    relevance_score=source_data.get("score", 0.0),
                    metadata=source_data.get("metadata", {})
                )
                sources.append(source)

            # Crear objeto de respuesta
            output_data = RAGQueryOutput(
                response=data.get("response", ""),
                sources=sources,
                token_usage=data.get("token_usage", {}),
                model=data.get("model", "unknown"),
                latency_ms=data.get("latency_ms", 0)
            )
            
            # Actualizar metadatos de ejecución
            execution_metadata.end_time = time.time()
            execution_metadata.success = True
            execution_metadata.token_usage = output_data.token_usage
            
            # Realizar tracking de tokens
            if output_data.token_usage and "total_tokens" in output_data.token_usage:
                # Generar idempotency_key para evitar doble conteo
                idempotency_key = f"rag:{self.tenant_id}:{self.agent_id}:{self.conversation_id}:{hash(query)}:{input_data.top_k}"
                
                # Usar el patrón estandarizado de tracking de tokens
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=output_data.token_usage.get("total_tokens", 0),
                    model=output_data.model,
                    token_type=TOKEN_TYPE_LLM,  # Tipo de token estandarizado
                    operation=OPERATION_AGENT_RAG,
                    metadata={
                        "agent_id": self.agent_id,
                        "conversation_id": self.conversation_id,
                        "collection_id": self.collection_id,
                        "query": query,
                        "similarity_top_k": input_data.top_k,
                        "sources_count": len(output_data.sources),
                        "execution_time": execution_metadata.end_time - execution_metadata.start_time
                    },
                    idempotency_key=idempotency_key  # Añadido para evitar duplicación
                )
                
            # Formatear fuentes para la respuesta
            if output_data.sources and len(output_data.sources) > 0 and input_data.include_sources:
                sources_text = "\n\nFuentes utilizadas:\n"
                for i, source in enumerate(output_data.sources, 1):
                    sources_text += f"\n{i}. {source.title}"
                    if source.url:
                        sources_text += f" ({source.url})"
                    
                return output_data.response + sources_text
            
            return output_data.response
            
        except Exception as e:
            # Actualizar metadatos de ejecución
            execution_metadata.end_time = time.time()
            execution_metadata.success = False
            execution_metadata.error = str(e)
            
            logger.error(f"Error en RAGQueryTool: {str(e)}")
            return f"Error al consultar la colección: {str(e)}"


class RAGSearchTool(BaseTool):
    """Herramienta para buscar documentos en una colección."""
    
    name = "rag_search"
    description = "Busca documentos en una colección y devuelve los resultados más relevantes. Útil para explorar qué documentos están disponibles antes de hacer una consulta específica."
    collection_id: str
    limit: int = 5
    threshold: float = 0.6
    include_metadata: bool = True
    metadata_fields: Optional[List[str]] = None
    cached_responses: bool = True
    
    class Config:
        arbitrary_types_allowed = True
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(
        self, 
        query: str,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Busca documentos en la colección.
        
        Args:
            query: Texto de la búsqueda
            limit: Número máximo de resultados
            threshold: Umbral de similitud mínima para incluir resultados
            
        Returns:
            str: Resultados de la búsqueda formateados
        """
        # Crear objeto de entrada estandarizado
        input_data = RAGQueryInput(
            query=query,
            collection_id=self.collection_id,
            top_k=limit or self.limit,
            threshold=threshold or self.threshold,
            include_metadata=self.include_metadata,
            include_sources=False,  # En búsqueda solo queremos los documentos, no generar una respuesta
            metadata_fields=self.metadata_fields,
            cache_results=self.cached_responses
        )
        
        # Generar metadatos de ejecución
        execution_metadata = ToolExecutionMetadata(
            tool_name=self.name,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            operation="rag_search",
            start_time=time.time()
        )
        
        # Validar el tenant_id
        if not self.tenant_id:
            return "Error: Se requiere tenant_id para realizar búsquedas RAG."
        
        try:
            # Usar service registry para llamar al servicio de consulta
            service_registry = ServiceRegistry()
            
            # Crear clave para caché
            cache_key = f"rag_search:{self.collection_id}:{query}:{input_data.top_k}"
            
            # Llamar al endpoint de búsqueda RAG
            response = await service_registry.call_query_service(
                endpoint="internal/search",
                method="POST",
                data=input_data.dict(),
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                ctx=self.ctx,
                idempotency_key=cache_key if input_data.cache_results else None
            )
            
            # Procesar la respuesta
            if not response.get("success", False):
                error_msg = response.get("error", {}).get("message", "Unknown error")
                return f"Error searching collection: {error_msg}"
                
            # Extraer resultados y metadatos
            data = response.get("data", {})
            
            # Mapear resultados a objetos tipados
            sources = []
            for source_data in data.get("results", []):
                source = CollectionSource(
                    document_id=source_data.get("document_id", ""),
                    collection_id=self.collection_id,
                    tenant_id=self.tenant_id,
                    chunk_id=source_data.get("chunk_id", ""),
                    title=source_data.get("title", "Documento sin título"),
                    url=source_data.get("url"),
                    relevance_score=source_data.get("score", 0.0),
                    content_preview=source_data.get("content", "")[:200],
                    metadata=source_data.get("metadata", {})
                )
                sources.append(source)
            
            # Actualizar metadatos de ejecución
            execution_metadata.end_time = time.time()
            execution_metadata.success = True
            execution_metadata.token_usage = data.get("token_usage", {})
            
            # Realizar tracking de tokens si hay información
            if data.get("token_usage") and "total_tokens" in data.get("token_usage", {}):
                # Generar idempotency_key para evitar doble conteo
                idempotency_key = f"rag_search:{self.tenant_id}:{self.agent_id}:{self.conversation_id}:{hash(query)}:{input_data.top_k}"
                
                # Usar el patrón estandarizado de tracking de tokens
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=data["token_usage"].get("total_tokens", 0),
                    model=data.get("model", "unknown"),
                    token_type=TOKEN_TYPE_LLM,  # Tipo de token estandarizado
                    operation=OPERATION_AGENT_RAG_SEARCH,
                    metadata={
                        "agent_id": self.agent_id,
                        "conversation_id": self.conversation_id,
                        "collection_id": self.collection_id,
                        "query": query,
                        "limit": input_data.top_k,
                        "results_count": len(sources),
                        "execution_time": execution_metadata.end_time - execution_metadata.start_time
                    },
                    idempotency_key=idempotency_key  # Añadido para evitar duplicación
                )
            
            # No hay resultados
            if not sources:
                return f"No se encontraron documentos para la búsqueda: '{query}'"
            
            # Formatear resultados para la respuesta
            output = f"Resultados para la búsqueda: '{query}'\n\n"
            
            for i, source in enumerate(sources, 1):
                output += f"{i}. {source.title}\n"
                if source.url:
                    output += f"   URL: {source.url}\n"
                output += f"   Relevancia: {source.relevance_score:.2f}\n"
                output += f"   Vista previa: {source.content_preview}...\n\n"
            
            return output
            
        except Exception as e:
            # Actualizar metadatos de ejecución
            execution_metadata.end_time = time.time()
            execution_metadata.success = False
            execution_metadata.error = str(e)
            
            logger.error(f"Error en RAGSearchTool: {str(e)}")
            return f"Error al buscar documentos: {str(e)}"
