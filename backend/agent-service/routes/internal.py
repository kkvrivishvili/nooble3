"""
Internal routes for service-to-service communication.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, Body, HTTPException
from pydantic import BaseModel, Field

from common.context import with_context, Context
from common.errors import handle_errors
from common.models.base import BaseResponse

from services import LangChainAgentService
from services.service_registry import ServiceRegistry
from tools.base import ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


class InternalAgentRequest(BaseModel):
    """Internal request model for agent operations."""
    agent_id: str
    tenant_id: str
    operation: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None


class ToolExecution(BaseModel):
    """Model for tool execution request."""
    tool_id: str = Field(..., description="ID of the tool to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters for execution")
    agent_id: Optional[str] = Field(None, description="ID of the requesting agent")
    conversation_id: Optional[str] = Field(None, description="ID of the conversation context")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional execution metadata")


class InternalAgentResponse(BaseResponse):
    """Internal response model for agent operations."""
    data: Optional[Dict[str, Any]] = None


@router.post("/execute-tool", response_model=InternalAgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def execute_tool(
    execution: ToolExecution,
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Execute a tool registered with the agent service.
    This endpoint is used by agents to execute tools during conversations.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Execute the tool using the tool registry from agent service
    result = await agent_service.tool_registry.execute_tool(
        tool_id=execution.tool_id,
        parameters=execution.parameters,
        tenant_id=tenant_id,
        agent_id=execution.agent_id,
        conversation_id=execution.conversation_id,
        ctx=ctx
    )
    
    return InternalAgentResponse(
        success=result.success,
        message="Tool executed successfully" if result.success else f"Tool execution failed: {result.error}",
        data={
            "result": result.dict()
        }
    )


@router.post("/query-agent", response_model=InternalAgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def query_agent(
    request: InternalAgentRequest,
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Internal endpoint for other services to query an agent directly.
    Allows for direct agent interaction without going through the chat interface.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Get the agent
    agent = await agent_service.get_agent_by_id(request.agent_id, request.tenant_id)
    
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {request.agent_id} not found"
        )
    
    # Process the internal query
    result = await agent_service.process_internal_query(
        agent=agent,
        operation=request.operation,
        parameters=request.parameters,
        tenant_id=tenant_id,
        ctx=ctx
    )
    
    return InternalAgentResponse(
        success=True,
        message="Agent query processed successfully",
        data=result
    )


@router.post("/register-tool", response_model=InternalAgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def register_tool(
    request: Dict[str, Any] = Body(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Register a new tool with the agent service.
    This endpoint is used by other services to register their tools.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Extract tool information
    tool_type = request.get("tool_type")
    name = request.get("name")
    description = request.get("description")
    service_name = request.get("service_name")
    endpoint = request.get("endpoint")
    parameters = request.get("parameters", {})
    metadata = request.get("metadata", {})
    
    if not all([tool_type, name, description, service_name, endpoint]):
        raise HTTPException(
            status_code=400,
            detail="Missing required fields for tool registration"
        )
    
    # Get the tool registry from the agent service
    tool_registry = agent_service.tool_registry
    
    # Ensure tool registry is initialized
    if not tool_registry._initialized:
        await tool_registry.initialize()
    
    # Register the tool
    tool = await tool_registry.register_service_tool(
        tool_type=tool_type,
        name=name,
        description=description,
        service_name=service_name,
        endpoint=endpoint,
        parameters=parameters,
        tenant_id=tenant_id,
        metadata=metadata
    )
    
    return InternalAgentResponse(
        success=True,
        message="Tool registered successfully",
        data={"tool_id": tool.tool_id}
    )


@router.post("/agent-health", response_model=InternalAgentResponse)
@handle_errors(error_type="service", log_traceback=True)
async def agent_health(
    agent_service: LangChainAgentService = Depends(),
):
    """
    Internal health check endpoint for service registry.
    Verifica la salud del servicio de agentes y sus dependencias críticas.
    
    Returns:
        InternalAgentResponse: Respuesta con el estado del servicio y sus dependencias
    """
    start_time = time.time()
    dependencies = []
    service_registry = ServiceRegistry()
    
    # Verificar servicios dependientes críticos: query y embedding
    critical_services = ["query", "embedding"]
    all_healthy = True
    
    for service_name in critical_services:
        try:
            service_status = await service_registry.check_service_health(service_name)
            service_healthy = service_status.get("status") == "available"
            
            dependencies.append({
                "name": service_name,
                "status": "healthy" if service_healthy else "degraded",
                "message": service_status.get("message", ""),
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            })
            
            if not service_healthy:
                all_healthy = False
                
        except Exception as e:
            dependencies.append({
                "name": service_name,
                "status": "unavailable",
                "message": str(e),
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            })
            all_healthy = False
    
    # Verificar herramientas disponibles
    try:
        tool_count = len(agent_service.tool_registry.available_tools)
        tool_status = "healthy" if tool_count > 0 else "degraded"
    except Exception as e:
        tool_status = "unavailable"
        tool_count = 0
    
    return InternalAgentResponse(
        success=all_healthy,
        message="Agent service is healthy" if all_healthy else "Agent service is degraded",
        data={
            "status": "ok" if all_healthy else "degraded",
            "dependencies": dependencies,
            "tools": {
                "status": tool_status,
                "count": tool_count
            },
            "latency_ms": round((time.time() - start_time) * 1000, 2)
        }
    )
