"""
Routes for handling agents and conversations.

Este módulo define las rutas REST API para la gestión de agentes
y conversaciones utilizando modelos estandarizados y patrones consistentes.
"""

import logging
import uuid
import time
from typing import Dict, List, Optional, Any, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Path
from fastapi.responses import JSONResponse

from common.context import with_context, Context
from common.db import get_supabase_client
from common.errors import handle_errors, ServiceError
from common.cache import CacheManager, get_with_cache_aside
from common.auth import validate_model_access
from common.tracking import track_token_usage, track_operation_latency
from common.config.tiers import get_tier_limits

from config import get_settings, get_tenant_agent_limits
from config.constants import TOKEN_TYPE_LLM, OPERATION_AGENT_CHAT

from models import (
    # Modelos base de agentes
    Agent, AgentCreate, AgentUpdate, AgentResponse, 
    ChatRequest, ChatResponse, ConversationMessage,
    
    # Modelos de contexto
    ContextConfig, ContextPayload, ContextManager,
    
    # Modelos de colecciones
    CollectionType, CollectionMetadata, CollectionStrategyConfig,
    StrategyType, SelectionCriteria, CollectionSelectionResult,
    
    # Modelos de herramientas
    ToolType, ToolExecutionMetadata, RAGQueryInput, RAGQueryOutput
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
@with_context(tenant=True, user=True)
@handle_errors(error_type="service", log_traceback=True, error_map={
    "AgentNotFound": (404, "Agente no encontrado"),
    "AgentInactive": (400, "Agente no activo"),
    "ModelAccessError": (403, "Acceso al modelo no permitido")
})
async def chat_with_agent(
    chat_request: ChatRequest,
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    """
    Chatea con un agente utilizando propagación de contexto y gestión de colecciones.
    
    Args:
        chat_request: Solicitud de chat con mensaje y metadata
        agent_id: ID del agente para chatear
        agent_service: Servicio de agentes inyectado
        ctx: Contexto de la operación
        
    Returns:
        ChatResponse: Respuesta del agente con mensaje y metadatos
        
    Raises:
        HTTPException: Si el agente no existe, no está activo o hay otro error
    """
    # Obtener IDs esenciales del contexto
    tenant_id = ctx.get_tenant_id()
    user_id = ctx.get_user_id(False)  # Opcional
    
    # Validar agente utilizando caché con patrón Cache-Aside
    cache_key = f"agent:{agent_id}:{tenant_id}"
    agent = await CacheManager.get_with_cache_aside(
        data_type="agent",
        resource_id=cache_key,
        fetch_function=lambda: agent_service.get_agent_by_id(agent_id, tenant_id),
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard
    )
    
    if not agent:
        raise ServiceError(
            "AgentNotFound",
            f"Agent with ID {agent_id} not found",
            status_code=404
        )
    
    if agent.state != "active":
        raise ServiceError(
            "AgentInactive",
            f"Agent is not active, current state: {agent.state}",
            status_code=400
        )
    
    # Si no se proporciona conversation_id, crear uno nuevo
    conversation_id = chat_request.conversation_id
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        chat_request.conversation_id = conversation_id
    
    # Crear payload de contexto para propagación
    context_payload = ContextPayload(
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        collection_id=None,  # Se asignará si se usan colecciones específicas
        source_service="agent"
    )
    
    # Configurar gestor de contexto
    context_manager = ContextManager(
        context=context_payload
    )
    
    # Gestionar colecciones si se proporcionan
    collection_ids = chat_request.collection_ids
    if collection_ids:
        # Validar las colecciones accesibles para este tenant
        validated_collections = []
        for collection_id in collection_ids:
            # Aquí se podría usar CollectionStrategyConfig en el futuro
            # para seleccionar las mejores colecciones automáticamente
            is_valid = await agent_service.validate_collection_access(
                collection_id=collection_id,
                tenant_id=tenant_id
            )
            if is_valid:
                validated_collections.append(collection_id)
        
        # Actualizar la solicitud con las colecciones validadas
        chat_request.collection_ids = validated_collections
    
    # Procesar la solicitud de chat con contexto completo
    start_time = time.time()
    response = await agent_service.process_chat(
        agent=agent,
        chat_request=chat_request,
        tenant_id=tenant_id,
        ctx=ctx
    )
    
    # Registrar tiempo de procesamiento
    processing_time_ms = int((time.time() - start_time) * 1000)
    
    # Realizar tracking de tokens
    tokens_used = response.metadata.get("total_tokens", 0) if response.metadata else 0
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=tokens_used,
        model=agent.config.model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type=TOKEN_TYPE_LLM,
        operation=OPERATION_AGENT_CHAT,
        metadata={
            "processing_time_ms": processing_time_ms,
            "collection_count": len(chat_request.collection_ids) if chat_request.collection_ids else 0,
            "message_length": len(chat_request.message)
        }
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
