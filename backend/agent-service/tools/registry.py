"""
Registro centralizado para herramientas de agentes utilizando LangChain.
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Callable, Optional, Union, Type

from langchain_core.tools import BaseTool as LangChainBaseTool

from common.context import with_context, Context
from common.errors import handle_errors, ServiceError
from common.db import get_supabase_client
from common.cache import CacheManager

from config import get_settings
from config.constants import (
    TOOL_TYPE_QUERY, 
    TOOL_TYPE_EMBEDDING,
    TOOL_TYPE_EXTERNAL_API,
    TOOL_TYPE_CUSTOM,
    TABLE_TOOLS
)

from services.service_registry import ServiceRegistry
from tools.base import BaseTool, ToolResult
from tools.rag import RAGQueryTool, RAGSearchTool
from tools.general import DateTimeTool, CalculatorTool, FormatJSONTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registro centralizado para herramientas de agentes basado en LangChain.
    """
    
    def __init__(self):
        """Inicializa el registro de herramientas."""
        self.settings = get_settings()
        self.service_registry = ServiceRegistry()
        self._tools: Dict[str, BaseTool] = {}
        self._initialized = False
    
    @handle_errors(error_type="service", log_traceback=True)
    async def initialize(self):
        """
        Inicializa el registro cargando herramientas base.
        """
        if self._initialized:
            return
            
        logger.info("Inicializando registro de herramientas")
        
        # Registrar herramientas base
        self._register_base_tools()
        
        # Cargar herramientas personalizadas desde la base de datos
        # TODO: Implementar cuando sea necesario
        
        self._initialized = True
    
    def _register_base_tools(self):
        """
        Registra herramientas base disponibles para todos los tenants.
        """
        # Herramientas de utilidad general
        self.register_tool(DateTimeTool())
        self.register_tool(CalculatorTool())
        self.register_tool(FormatJSONTool())
        
        logger.info(f"Registradas {len(self._tools)} herramientas base")
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_tools_for_collection(
        self, 
        collection_id: str,
        tenant_id: str,
        ctx: Optional[Context] = None
    ) -> List[BaseTool]:
        """
        Obtiene herramientas RAG específicas para una colección.
        
        Args:
            collection_id: ID de la colección
            tenant_id: ID del tenant
            ctx: Contexto de la operación
            
        Returns:
            List[BaseTool]: Herramientas específicas para la colección
        """
        # Crear herramientas RAG específicas para esta colección
        query_tool = RAGQueryTool(
            name=f"query_collection_{collection_id[:8]}",
            description=f"Consulta la colección {collection_id} y genera una respuesta basada en sus documentos",
            collection_id=collection_id
        )
        
        search_tool = RAGSearchTool(
            name=f"search_collection_{collection_id[:8]}",
            description=f"Busca documentos en la colección {collection_id} y devuelve los resultados más relevantes",
            collection_id=collection_id
        )
        
        return [query_tool, search_tool]
    
    def register_tool(self, tool: BaseTool) -> bool:
        """
        Registra una herramienta en el registro.
        
        Args:
            tool: Herramienta a registrar
            
        Returns:
            bool: True si se registró correctamente
        """
        self._tools[tool.name] = tool
        return True
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Obtiene una herramienta por su nombre.
        
        Args:
            tool_name: Nombre de la herramienta
            
        Returns:
            Optional[BaseTool]: Herramienta encontrada o None si no existe
        """
        return self._tools.get(tool_name)
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        Obtiene todas las herramientas registradas.
        
        Returns:
            List[BaseTool]: Lista de todas las herramientas
        """
        return list(self._tools.values())
    
    def get_tools_for_agent(self, tool_names: List[str]) -> List[BaseTool]:
        """
        Obtiene un subconjunto de herramientas por sus nombres.
        
        Args:
            tool_names: Lista de nombres de herramientas
            
        Returns:
            List[BaseTool]: Lista de herramientas encontradas
        """
        tools = []
        for name in tool_names:
            tool = self.get_tool(name)
            if tool:
                tools.append(tool)
        
        return tools
    
    def unregister_tool(self, tool_name: str) -> bool:
        """
        Elimina una herramienta del registro.
        
        Args:
            tool_name: Nombre de la herramienta a eliminar
            
        Returns:
            bool: True si se eliminó correctamente
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            return True
        return False
    
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_tool(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ctx: Optional[Context] = None
    ) -> ToolResult:
        """
        Ejecuta una herramienta por su ID.
        
        Args:
            tool_id: ID de la herramienta a ejecutar
            parameters: Parámetros para la ejecución
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            ctx: Contexto de la operación
            
        Returns:
            ToolResult: Resultado de la ejecución
        """
        start_time = time.time()
        
        # Buscar la herramienta
        tool = self.get_tool(tool_id)
        
        if not tool:
            # Si no es una herramienta directa, podría ser una herramienta específica de colección
            # o una herramienta de servicio externo
            if "_collection_" in tool_id:
                # Extraer collection_id del nombre de la herramienta
                parts = tool_id.split("_collection_")
                if len(parts) == 2 and parts[0] in ["query", "search"]:
                    operation = parts[0]
                    collection_partial_id = parts[1]
                    
                    # Buscar el collection_id completo (podría requerir consulta a DB)
                    # Por ahora usamos el partial_id como collection_id completo
                    collection_id = collection_partial_id
                    
                    if operation == "query":
                        tool = RAGQueryTool(
                            name=tool_id,
                            description=f"Consulta la colección {collection_id}",
                            collection_id=collection_id
                        )
                    elif operation == "search":
                        tool = RAGSearchTool(
                            name=tool_id,
                            description=f"Busca en la colección {collection_id}",
                            collection_id=collection_id
                        )
            
            # Si sigue sin encontrarse, podría ser una herramienta de servicio externo
            if not tool:
                services = ["query", "embedding", "ingestion"]
                for service_name in services:
                    if tool_id.startswith(f"{service_name}_"):
                        # Es una herramienta de servicio, llamar al servicio correspondiente
                        return await self._execute_service_tool(
                            service_name=service_name,
                            tool_id=tool_id,
                            parameters=parameters,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            conversation_id=conversation_id,
                            ctx=ctx
                        )
                
                # Si llegamos aquí, la herramienta no existe
                raise ServiceError(f"Tool with ID {tool_id} not found")
        
        # Configurar el contexto en la herramienta
        tool.tenant_id = tenant_id
        tool.agent_id = agent_id
        tool.conversation_id = conversation_id
        tool.ctx = ctx
        
        # Ejecutar la herramienta usando el método execute() que está adaptado para nuestro sistema
        if hasattr(tool, 'execute'):
            return await tool.execute(parameters, tenant_id, agent_id, conversation_id, ctx)
        
        # Si no tiene el método execute(), crear un ToolResult manualmente
        result = ToolResult(
            success=True,
            data=None,
            error=None,
            execution_time=0.0,
            metadata={}
        )
        
        try:
            # Ejecutar la herramienta usando LangChain
            tool_result = await tool.arun(**parameters)
            result.data = tool_result
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_id}: {str(e)}", exc_info=True)
            result.success = False
            result.error = str(e)
        
        # Calcular tiempo de ejecución
        result.execution_time = time.time() - start_time
        
        return result
    
    async def _execute_service_tool(
        self,
        service_name: str,
        tool_id: str,
        parameters: Dict[str, Any],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ctx: Optional[Context] = None
    ) -> ToolResult:
        """
        Ejecuta una herramienta en un servicio externo.
        
        Args:
            service_name: Nombre del servicio
            tool_id: ID de la herramienta
            parameters: Parámetros para la ejecución
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            ctx: Contexto de la operación
            
        Returns:
            ToolResult: Resultado de la ejecución
        """
        start_time = time.time()
        
        result = ToolResult(
            success=True,
            data=None,
            error=None,
            execution_time=0.0,
            metadata={}
        )
        
        try:
            # Determinar el método correcto según el servicio
            if service_name == "query":
                response = await self.service_registry.call_query_service(
                    endpoint=f"internal/tools/{tool_id}",
                    method="POST",
                    data=parameters,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    ctx=ctx
                )
            elif service_name == "embedding":
                response = await self.service_registry.call_embedding_service(
                    endpoint=f"internal/tools/{tool_id}",
                    method="POST",
                    data=parameters,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    ctx=ctx
                )
            elif service_name == "ingestion":
                response = await self.service_registry.call_ingestion_service(
                    endpoint=f"internal/tools/{tool_id}",
                    method="POST",
                    data=parameters,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    ctx=ctx
                )
            else:
                result.success = False
                result.error = f"Servicio desconocido: {service_name}"
                return result
                
            # Procesar la respuesta
            if response.get("success", False):
                result.data = response.get("data")
                result.metadata = response.get("metadata", {})
            else:
                result.success = False
                result.error = response.get("error", {}).get("message", "Error desconocido")
                if "data" in response:
                    result.data = response.get("data")
                    
        except Exception as e:
            logger.error(f"Error executing service tool: {str(e)}", exc_info=True)
            result.success = False
            result.error = str(e)
            
        # Calcular tiempo de ejecución
        result.execution_time = time.time() - start_time
        
        return result
