"""
Routes for handling agents and conversations.
"""

import logging
import uuid
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Path
from fastapi.responses import JSONResponse

from common.context import with_context, Context
from common.db import get_supabase_client
from common.errors import handle_errors
from common.cache import CacheManager, get_with_cache_aside
from common.auth import validate_model_access
from common.tracking import track_token_usage
from common.config.tiers import get_tier_limits

from config import get_settings, get_tenant_agent_limits
from models import (
    Agent, AgentCreate, AgentUpdate, AgentResponse, 
    ChatRequest, ChatResponse, ConversationMessage
)
from services import LangChainAgentService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def create_agent(
    agent_data: AgentCreate,
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Create a new agent for the tenant.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Validate tenant permissions and limits
    agent_limits = await get_tenant_agent_limits(tenant_id)
    
    # Check if the tenant has reached their agent limit
    supabase = get_supabase_client()
    result = await supabase.table("agents").select("count(*)", count="exact").eq("tenant_id", tenant_id).execute()
    current_agent_count = result.count
    
    if current_agent_count >= agent_limits["max_agents"]:
        raise HTTPException(
            status_code=403,
            detail=f"Maximum number of agents ({agent_limits['max_agents']}) reached for this tenant"
        )
    
    # Validate LLM model access
    model = agent_data.config.model
    await validate_model_access(tenant_id, model, "llm")
    
    # Create the agent
    agent = await agent_service.create_agent(agent_data)
    
    return AgentResponse(
        success=True,
        message="Agent created successfully",
        data=agent
    )


@router.get("", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def list_agents(
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_public: Optional[bool] = Query(None)
):
    """
    List agents for the tenant.
    """
    tenant_id = ctx.get_tenant_id()
    
    # List agents
    agents = await agent_service.list_agents(
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        is_public=is_public
    )
    
    return AgentResponse(
        success=True,
        message="Agents retrieved successfully",
        data=agents
    )


@router.get("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def get_agent(
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Get agent by ID.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Get agent using cache-aside pattern
    async def fetch_agent_from_db(resource_id):
        return await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    agent, _ = await get_with_cache_aside(
        data_type="agent",
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_agent_from_db,
        ttl=CacheManager.ttl_standard
    )
    
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    return AgentResponse(
        success=True,
        message="Agent retrieved successfully",
        data=agent
    )


@router.put("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def update_agent(
    update_data: AgentUpdate,
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Update an existing agent.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Check if agent exists and belongs to the tenant
    existing_agent = await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    if not existing_agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    # Validate LLM model access if model is being updated
    if update_data.config and update_data.config.model:
        model = update_data.config.model
        await validate_model_access(tenant_id, model, "llm")
    
    # Update the agent
    updated_agent = await agent_service.update_agent(agent_id, update_data, tenant_id)
    
    # Invalidate cache
    await CacheManager.invalidate(tenant_id=tenant_id, data_type="agent", resource_id=agent_id)
    
    return AgentResponse(
        success=True,
        message="Agent updated successfully",
        data=updated_agent
    )


@router.delete("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def delete_agent(
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Delete an agent (mark as deleted).
    """
    tenant_id = ctx.get_tenant_id()
    
    # Check if agent exists and belongs to the tenant
    existing_agent = await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    if not existing_agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    # Delete the agent (soft delete)
    success = await agent_service.delete_agent(agent_id, tenant_id)
    
    # Invalidate cache
    await CacheManager.invalidate(tenant_id=tenant_id, data_type="agent", resource_id=agent_id)
    
    return AgentResponse(
        success=success,
        message="Agent deleted successfully" if success else "Failed to delete agent"
    )


@router.post("/{agent_id}/chat", response_model=ChatResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def chat_with_agent(
    chat_request: ChatRequest,
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Chat with an agent.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Validate agent exists and is active
    agent = await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    if agent.state != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Agent is not active, current state: {agent.state}"
        )
    
    # If conversation_id is not provided, create a new one
    conversation_id = chat_request.conversation_id
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        chat_request.conversation_id = conversation_id
    
    # Process the chat request
    response = await agent_service.process_chat(
        agent=agent,
        chat_request=chat_request,
        tenant_id=tenant_id,
        ctx=ctx
    )
    
    # Track token usage
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=response.metadata.get("total_tokens", 0) if response.metadata else 0,
        model=agent.config.model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type="llm",
        operation="agent_chat",
    )
    
    return response


@router.get("/{agent_id}/conversations", response_model=dict)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def list_conversations(
    agent_id: str = Path(...),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: Context = None
):
    """
    List conversations for an agent.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Create agent service instance
    agent_service = AgentService()
    
    # Check if agent exists and belongs to the tenant
    existing_agent = await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    if not existing_agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    # List conversations
    conversations = await agent_service.list_conversations(
        agent_id=agent_id,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset
    )
    
    return {
        "success": True,
        "message": "Conversations retrieved successfully",
        "data": conversations
    }


@router.get("/{agent_id}/conversations/{conversation_id}", response_model=dict)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def get_conversation(
    agent_id: str = Path(...),
    conversation_id: str = Path(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: Context = None
):
    """
    Get a conversation with messages.
    """
    tenant_id = ctx.get_tenant_id()
    
    # Create agent service instance
    agent_service = AgentService()
    
    # Check if agent exists and belongs to the tenant
    existing_agent = await agent_service.get_agent_by_id(agent_id, tenant_id)
    
    if not existing_agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent with ID {agent_id} not found"
        )
    
    # Get conversation messages
    messages = await agent_service.get_conversation_messages(
        agent_id=agent_id,
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset
    )
    
    return {
        "success": True,
        "message": "Conversation messages retrieved successfully",
        "data": {
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "messages": messages
        }
    }
