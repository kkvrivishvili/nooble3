import logging
import uuid
from typing import Optional, List
import re

from fastapi import APIRouter, Depends, Path, Query, HTTPException

from common.models import TenantInfo, AgentConfig, AgentRequest, AgentResponse, AgentListResponse, DeleteAgentResponse
from common.errors import ServiceError, handle_service_error_simple, InvalidAgentIdError, ErrorCode, AgentNotFoundError, AgentExecutionError
from common.context import with_context
from common.config import get_settings, invalidate_settings_cache
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.auth import verify_tenant, validate_model_access, get_allowed_models_for_tier
from common.cache.counters import invalidate_agent_cache
from common.cache.contextual import invalidate_cache_hierarchy

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

@router.post("", response_model=AgentResponse)
@handle_service_error_simple
@with_context(tenant=True)
async def create_agent(
    request: AgentRequest, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentResponse:
    """Crea un nuevo agente para el inquilino."""
    tenant_id = tenant_info.tenant_id
    
    # Validar acceso al modelo de LLM
    model_name = request.llm_model
    if model_name:
        try:
            model_name = await validate_model_access(tenant_info, model_name, "llm")
        except ServiceError as e:
            # Si el modelo no está permitido, usar el modelo por defecto para su tier
            logger.info(f"Cambiando al modelo por defecto: {e.message}", extra=e.context)
            allowed_models = get_allowed_models_for_tier(tenant_info.subscription_tier, "llm")
            model_name = allowed_models[0] if allowed_models else settings.default_llm_model
            # Guardar información sobre el downgrade para incluirla en la respuesta
            request.metadata = request.metadata or {}
            request.metadata["model_downgraded"] = True
    else:
        # Usar modelo predeterminado
        model_name = settings.default_llm_model
    
    # Generar ID para el nuevo agente
    agent_id = str(uuid.uuid4())
    
    # Validar formato de ID
    if not re.match(r"^agent_[a-z0-9]{8}$", agent_id):
        raise InvalidAgentIdError(agent_id)
    
    # Crear objeto de configuración del agente
    agent_data = {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "name": request.name,
        "description": request.description,
        "agent_type": request.agent_type or "conversational",
        "llm_model": model_name,
        "tools": request.tools or [],
        "system_prompt": request.system_prompt,
        "memory_enabled": request.memory_enabled,
        "memory_window": request.memory_window,
        "is_active": True,
        "is_public": request.is_public or False,
        "metadata": request.metadata or {},
        "rag_config": request.rag_config.dict() if request.rag_config else {}
    }
    
    try:
        # Guardar en Supabase
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("agent_configs")).insert(agent_data).execute()
        
        if result.error:
            logger.error(f"Error creando agente para tenant '{tenant_id}': {result.error}")
            if "duplicate key" in str(result.error):
                raise ServiceError(
                    message="Agent ya existe",
                    error_code=ErrorCode.AGENT_ALREADY_EXISTS,
                    status_code=409
                ) from result.error
            raise ServiceError(
                message="Error creando agente",
                error_code=ErrorCode.AGENT_SETUP_ERROR
            ) from result.error
        
        # Obtener el agente creado
        created_agent = result.data[0] if result.data else agent_data
        
        # Crear respuesta
        response = AgentResponse(
            success=True,
            message="Agente creado exitosamente",
            agent_id=created_agent["agent_id"],
            tenant_id=created_agent["tenant_id"],
            name=created_agent["name"],
            description=created_agent["description"],
            agent_type=created_agent["agent_type"],
            llm_model=created_agent["llm_model"],
            tools=created_agent["tools"],
            system_prompt=created_agent["system_prompt"],
            memory_enabled=created_agent["memory_enabled"],
            memory_window=created_agent["memory_window"],
            is_active=created_agent.get("is_active", True),
            is_public=created_agent.get("is_public", False),
            metadata=created_agent.get("metadata", {}),
            rag_config=created_agent.get("rag_config"),
            created_at=created_agent.get("created_at"),
            updated_at=created_agent.get("updated_at")
        )
        
        # Invalidar caché de configuraciones para este tenant
        invalidate_settings_cache(tenant_id)
        
        return response
    
    except Exception as e:
        if "duplicate key" in str(e):
            raise ServiceError(
                message="Agent ya existe",
                error_code=ErrorCode.AGENT_ALREADY_EXISTS,
                status_code=409
            ) from e
        raise ServiceError(
            message="Error creando agente",
            error_code=ErrorCode.AGENT_SETUP_ERROR
        ) from e

@router.get("/{agent_id}", response_model=AgentResponse)
@handle_service_error_simple
@with_context(tenant=True, agent=True)
async def get_agent(
    agent_id: str, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentResponse:
    """Obtiene la configuración de un agente existente."""
    tenant_id = tenant_info.tenant_id
    
    # Obtener agente desde Supabase
    supabase = get_supabase_client()
    
    result = await supabase.table(get_table_name("agent_configs")) \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("agent_id", agent_id) \
        .single() \
        .execute()
        
    if not result.data:
        logger.warning(f"Intento de acceso a agente no existente: {agent_id} por tenant {tenant_id}")
        raise ServiceError(
            message=f"Agent with ID {agent_id} not found for this tenant",
            status_code=404,
            error_code="agent_not_found"
        )
    
    agent_data = result.data
    
    return AgentResponse(
        success=True,
        message="Agente obtenido exitosamente",
        agent_id=agent_data["agent_id"],
        tenant_id=agent_data["tenant_id"],
        name=agent_data["name"],
        description=agent_data.get("description"),
        agent_type=agent_data.get("agent_type", "conversational"),
        llm_model=agent_data.get("llm_model", settings.default_llm_model),
        tools=agent_data.get("tools", []),
        system_prompt=agent_data.get("system_prompt"),
        memory_enabled=agent_data.get("memory_enabled", True),
        memory_window=agent_data.get("memory_window", 10),
        is_active=agent_data.get("is_active", True),
        is_public=agent_data.get("is_public", False),
        metadata=agent_data.get("metadata", {}),
        rag_config=agent_data.get("rag_config"),
        created_at=agent_data.get("created_at"),
        updated_at=agent_data.get("updated_at")
    )

@router.get("", response_model=AgentListResponse)
@handle_service_error_simple
@with_context(tenant=True)
async def list_agents(
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentListResponse:
    """Lista todos los agentes disponibles para el tenant actual."""
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        result = await supabase.table(get_table_name("agent_configs")).select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
        
        agents_list = []
        for agent_data in result.data:
            agent_summary = {
                "agent_id": agent_data["agent_id"],
                "name": agent_data["name"],
                "description": agent_data.get("description", ""),
                "model": agent_data.get("llm_model", "gpt-3.5-turbo"),
                "is_public": agent_data.get("is_public", False),
                "created_at": agent_data.get("created_at"),
                "updated_at": agent_data.get("updated_at")
            }
            agents_list.append(agent_summary)
        
        return AgentListResponse(
            success=True,
            message="Agentes obtenidos exitosamente",
            agents=agents_list,
            count=len(agents_list)
        )
        
    except Exception as e:
        logger.error(f"Error listing agents: {str(e)}")
        raise ServiceError(
            message="Error al listar agentes",
            status_code=500,
            error_code="LIST_FAILED"
        )

@router.put("/{agent_id}", response_model=AgentResponse)
@handle_service_error_simple
@with_context(tenant=True, agent=True)
async def update_agent(
    agent_id: str, 
    request: AgentRequest, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentResponse:
    """Actualiza la configuración de un agente existente."""
    tenant_id = tenant_info.tenant_id
    
    supabase = get_supabase_client()
    
    # Verificar que el agente exista y pertenezca al tenant
    agent_check = await supabase.table(get_table_name("agent_configs")) \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("agent_id", agent_id) \
        .single() \
        .execute()
    
    if not agent_check.data:
        logger.warning(f"Intento de actualizar agente no existente: {agent_id} por tenant {tenant_id}")
        raise ServiceError(
            message=f"Agent with ID {agent_id} not found for this tenant",
            status_code=404,
            error_code="agent_not_found"
        )
    
    # Validar acceso al modelo si ha cambiado
    model_name = request.llm_model
    if model_name and model_name != agent_check.data["llm_model"]:
        try:
            model_name = await validate_model_access(tenant_info, model_name, "llm")
        except ServiceError as e:
            # Si el modelo no está permitido, usar el modelo por defecto para su tier
            logger.info(f"Cambiando al modelo por defecto: {e.message}", extra=e.context)
            allowed_models = get_allowed_models_for_tier(tenant_info.subscription_tier, "llm")
            model_name = allowed_models[0] if allowed_models else settings.default_llm_model
            # Guardar información sobre el downgrade para incluirla en la respuesta
            request.metadata = request.metadata or {}
            request.metadata["model_downgraded"] = True
        else:
            model_name = agent_check.data["llm_model"]
    
    # Preparar datos para actualizar
    update_data = {
        "name": request.name,
        "description": request.description,
        "agent_type": request.agent_type,
        "llm_model": model_name,
        "tools": request.tools,
        "system_prompt": request.system_prompt,
        "memory_enabled": request.memory_enabled,
        "memory_window": request.memory_window,
        "is_public": request.is_public,
        "metadata": request.metadata or agent_check.data.get("metadata", {}),
        "rag_config": request.rag_config.dict() if request.rag_config else agent_check.data.get("rag_config", {}),
        "updated_at": "NOW()"
    }
    
    try:
        # Actualizar el agente en la base de datos
        result = await supabase.table(get_table_name("agent_configs")) \
            .update(update_data) \
            .eq("tenant_id", tenant_id) \
            .eq("agent_id", agent_id) \
            .execute()
        
        if result.error:
            logger.error(f"Error actualizando agente para tenant '{tenant_id}': {result.error}")
            raise ServiceError(f"Error updating agent: {result.error}")
        
        # Preparar respuesta
        updated_agent = result.data[0] if result.data else {**agent_check.data, **update_data}
        
        # Invalidar caché del agente
        await invalidate_agent_cache(tenant_id, agent_id)
        
        # También invalidar caché de configuraciones para este tenant
        invalidate_settings_cache(tenant_id)
        
        return AgentResponse(
            success=True,
            message="Agente actualizado exitosamente",
            agent_id=updated_agent["agent_id"],
            tenant_id=updated_agent["tenant_id"],
            name=updated_agent["name"],
            description=updated_agent.get("description"),
            agent_type=updated_agent.get("agent_type", "conversational"),
            llm_model=updated_agent.get("llm_model"),
            tools=updated_agent.get("tools", []),
            system_prompt=updated_agent.get("system_prompt"),
            memory_enabled=updated_agent.get("memory_enabled", True),
            memory_window=updated_agent.get("memory_window", 10),
            is_active=updated_agent.get("is_active", True),
            is_public=updated_agent.get("is_public", False),
            metadata=updated_agent.get("metadata", {}),
            rag_config=updated_agent.get("rag_config"),
            created_at=updated_agent.get("created_at"),
            updated_at=updated_agent.get("updated_at")
        )
    
    except Exception as e:
        raise ServiceError(
            message="Error actualizando agente",
            error_code=ErrorCode.AGENT_UPDATE_ERROR
        ) from e

@router.delete("/{agent_id}", response_model=DeleteAgentResponse)
@handle_service_error_simple
@with_context(tenant=True, agent=True)
async def delete_agent(
    agent_id: str, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> DeleteAgentResponse:
    """Elimina un agente específico y sus conversaciones asociadas."""
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Verificar que el agente exista y pertenezca al tenant
        agent_result = await supabase.table(get_table_name("agent_configs")).select("*").eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
        
        if not agent_result.data:
            raise ServiceError(
                message=f"Agent {agent_id} not found or not accessible",
                status_code=404,
                error_code="AGENT_NOT_FOUND"
            )
        
        # Eliminar conversaciones asociadas al agente
        # Primero contamos cuántas conversaciones hay
        count_result = await supabase.table(get_table_name("conversations")).select("count", count="exact").eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
        conversations_count = count_result.count if hasattr(count_result, "count") else 0
        
        # Eliminar las conversaciones
        if conversations_count > 0:
            delete_conversations = await supabase.table(get_table_name("conversations")).delete().eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
        
        # Eliminar el agente
        delete_result = await supabase.table(get_table_name("agent_configs")).delete().eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
        
        if delete_result.error:
            raise ServiceError(
                message="Error al eliminar el agente",
                status_code=500,
                error_code="DELETE_FAILED"
            )
        
        # Invalidar toda la caché relacionada con este agente
        await invalidate_agent_cache(tenant_id, agent_id)
        
        # Invalidar caché de configuraciones para este tenant
        invalidate_settings_cache(tenant_id)
        
        return DeleteAgentResponse(
            success=True,
            message=f"Agente {agent_id} eliminado exitosamente",
            agent_id=agent_id,
            deleted=True,
            conversations_deleted=conversations_count
        )
        
    except ServiceError:
        # Re-lanzar ServiceError para que sea manejado por el decorador
        raise
    except Exception as e:
        logger.error(f"Error deleting agent: {str(e)}")
        raise ServiceError(
            message="Error al eliminar el agente",
            status_code=500,
            error_code="DELETE_FAILED"
        )