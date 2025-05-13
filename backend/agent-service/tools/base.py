"""
Clases base para herramientas de agentes.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Union, Callable, AsyncCallable, Awaitable
from pydantic import BaseModel, Field

# LangChain 0.3 ya usa Pydantic v2 internamente
from langchain_core.tools import BaseTool as LCBaseTool

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError

logger = logging.getLogger(__name__)


class ToolResult(BaseModel):
    """Resultado de la ejecución de una herramienta."""
    success: bool = Field(True, description="Indica si la ejecución fue exitosa")
    data: Optional[Any] = Field(None, description="Datos de resultado de la herramienta")
    error: Optional[str] = Field(None, description="Error si la ejecución falló")
    execution_time: float = Field(0.0, description="Tiempo de ejecución en segundos")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales del resultado")


class BaseTool(LCBaseTool):
    """
    Herramienta base que extiende LangChain Tool con soporte para contexto y multitenancy.
    """
    name: str
    description: str
    return_direct: bool = False
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    ctx: Optional[Context] = None
    
    def _run(self, *args, **kwargs) -> str:
        """Implementación sincrónica - no recomendada, requerida por la interfaz."""
        raise NotImplementedError("Synchronous execution not supported, use arun instead")
    
    async def _arun(self, *args, **kwargs) -> str:
        """
        Implementación asincrónica a ser sobrescrita por la herramienta específica.
        """
        raise NotImplementedError("Tool implementation must override _arun")
    
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
        Ejecuta la herramienta con los parámetros proporcionados.
        
        Args:
            parameters: Parámetros de entrada
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            ctx: Contexto de la operación
            
        Returns:
            ToolResult: Resultado de la ejecución
        """
        start_time = time.time()
        
        # Configurar el contexto y tenancy
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.ctx = ctx
        
        # Crear un resultado base
        result = ToolResult(
            success=True,
            data=None,
            error=None,
            execution_time=0.0,
            metadata={}
        )
        
        try:
            # Ejecutar la herramienta (siempre de forma asíncrona)
            tool_result = await self.arun(**parameters)
            
            # Procesar el resultado
            if isinstance(tool_result, dict) and "error" in tool_result:
                # Si contiene un error
                result.success = False
                result.error = tool_result["error"]
                if "data" in tool_result:
                    result.data = tool_result["data"]
            else:
                # Resultado exitoso
                result.data = tool_result
                
            # Añadir metadatos si existen
            if isinstance(tool_result, dict) and "metadata" in tool_result:
                result.metadata = tool_result["metadata"]
                
        except Exception as e:
            logger.error(f"Error executing tool {self.name}: {str(e)}", exc_info=True)
            result.success = False
            result.error = str(e)
        
        # Calcular tiempo de ejecución
        result.execution_time = time.time() - start_time
        
        return result
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte la herramienta a un diccionario para API JSON.
        
        Returns:
            Dict[str, Any]: Representación de la herramienta como diccionario
        """
        args_schema = None
        if hasattr(self, 'args_schema'):
            schema_cls = self.args_schema
            # Usar model_json_schema() para Pydantic v2
            if hasattr(schema_cls, 'model_json_schema'):
                args_schema = schema_cls.model_json_schema()
            # Fallback para compatibilidad con v1
            elif hasattr(schema_cls, 'schema'):
                args_schema = schema_cls.schema()
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": args_schema or {},
            }
        }
