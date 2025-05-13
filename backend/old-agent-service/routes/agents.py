import logging
from typing import Optional, List
import re
import uuid

from fastapi import APIRouter, Depends, Path, Query, HTTPException

from common.models import TenantInfo, AgentConfig, AgentRequest, AgentResponse, AgentListResponse, DeleteAgentResponse
from common.errors import handle_errors, InvalidAgentIdError, AgentNotFoundError, AgentAlreadyExistsError, AgentSetupError, ErrorCode, AgentExecutionError, ServiceError
from common.context import with_context
from common.config import get_settings, invalidate_settings_cache
from common.config.tiers import get_available_llm_models
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.auth import verify_tenant, validate_model_access

from services.agent_executor import (
    get_agent_config, 
    create_agent_config, 
    update_agent_config, 
    delete_agent_config, 
    invalidate_agent_config_cache,
    list_agent_configs
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

@router.post("", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
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
            model_name = await validate_model_access(tenant_info, model_name, "llm", tenant_id=tenant_info.tenant_id)
        except ServiceError as e:
            # Si el modelo no está permitido, usar el modelo por defecto para su tier
            logger.info(f"Cambiando al modelo por defecto: {e.message}", extra=e.context)
            allowed_models = get_available_llm_models(tenant_info.subscription_tier, tenant_id=tenant_info.tenant_id)
            model_name = allowed_models[0] if allowed_models else settings.default_llm_model
            # Guardar información sobre el downgrade para incluirla en la respuesta
            request.metadata = request.metadata or {}
            request.metadata["model_downgraded"] = True
    
    # Generar ID para el nuevo agente con formato correcto
    agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    
    # Validar formato de ID
    if not re.match(r"^agent_[a-z0-9]{8}$", agent_id):
        raise InvalidAgentIdError(
            message=f"Invalid agent ID format: {agent_id}",
            details={"agent_id": agent_id, "pattern": "agent_[a-z0-9]{8}"}
        )
    
    # Preparar datos del agente
    agent_data = {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "name": request.name,
        "description": request.description,
        "agent_type": request.agent_type,
        "llm_model": model_name,
        "tools": request.tools,
        "system_prompt": request.system_prompt,
        "memory_enabled": request.memory_enabled,
        "memory_window": request.memory_window,
        "is_active": True,
        "is_public": request.is_public,
        "metadata": request.metadata,
        "rag_config": request.rag_config.dict() if request.rag_config else {},
        "created_at": "NOW()",
        "updated_at": "NOW()"
    }
    
    try:
        # Crear el nuevo agente
        created_agent = await create_agent_config(agent_data, tenant_id)
        
        # Invalidar cache de lista de agentes para este tenant
        await invalidate_agent_config_cache(tenant_id, agent_id)
        
        # Invalidar cache de configuraciones
        invalidate_settings_cache(tenant_id)
        
        return AgentResponse(
            success=True,
            message="Agente creado exitosamente",
            agent_id=created_agent["agent_id"],
            tenant_id=created_agent["tenant_id"],
            name=created_agent["name"],
            description=created_agent.get("description"),
            agent_type=created_agent.get("agent_type", "conversational"),
            llm_model=created_agent.get("llm_model"),
            tools=created_agent.get("tools", []),
            system_prompt=created_agent.get("system_prompt"),
            memory_enabled=created_agent.get("memory_enabled", True),
            memory_window=created_agent.get("memory_window", 10),
            is_active=created_agent.get("is_active", True),
            is_public=created_agent.get("is_public", False),
            metadata=created_agent.get("metadata", {}),
            rag_config=created_agent.get("rag_config"),
            created_at=created_agent.get("created_at"),
            updated_at=created_agent.get("updated_at")
        )
    
    except Exception as e:
        if isinstance(e, (AgentAlreadyExistsError, AgentSetupError)):
            raise
            
        error_context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "create_agent", "error_type": type(e).__name__}
        logger.error(f"Error creando agente: {str(e)}", extra=error_context, exc_info=True)
        raise AgentSetupError(
            message="Error al crear agente",
            details=error_context
        ) from e

@router.get("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True, agent=True)
@handle_errors(error_type="simple", log_traceback=False)
async def get_agent(
    agent_id: str, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentResponse:
    """Obtiene la configuración de un agente existente."""
    tenant_id = tenant_info.tenant_id
    
    # Utilizar la función centralizada get_agent_config para implementar el patrón Cache-Aside
    try:
        agent_data = await get_agent_config(agent_id, tenant_id)
        
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
    except ServiceError as e:
        # La función get_agent_config ya maneja los errores específicos
        raise e

@router.get("", response_model=AgentListResponse)
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def list_agents(
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentListResponse:
    """Lista todos los agentes disponibles para el tenant actual."""
    tenant_id = tenant_info.tenant_id
    
    try:
        # Utilizar la función centralizada para listar agentes
        agents = await list_agent_configs(tenant_id)
        
        # Convertir cada agente a formato de respuesta
        agent_list = []
        for agent in agents:
            agent_list.append({
                "agent_id": agent["agent_id"],
                "tenant_id": agent["tenant_id"],
                "name": agent["name"],
                "description": agent.get("description"),
                "agent_type": agent.get("agent_type", "conversational"),
                "llm_model": agent.get("llm_model"),
                "is_active": agent.get("is_active", True),
                "is_public": agent.get("is_public", False),
                "created_at": agent.get("created_at"),
                "updated_at": agent.get("updated_at")
            })
        
        return AgentListResponse(
            success=True,
            message=f"Se encontraron {len(agent_list)} agentes",
            agents=agent_list
        )
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
            
        error_context = {"tenant_id": tenant_id, "operation": "list_agents", "error_type": type(e).__name__}
        logger.error(f"Error listando agentes: {str(e)}", extra=error_context, exc_info=True)
        raise ServiceError(
            message="Error listando agentes",
            error_code=ErrorCode.SERVICE_ERROR,
            details=error_context
        ) from e

@router.put("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True, agent=True)
@handle_errors(error_type="simple", log_traceback=False)
async def update_agent(
    agent_id: str, 
    request: AgentRequest, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> AgentResponse:
    """Actualiza la configuración de un agente existente."""
    tenant_id = tenant_info.tenant_id
    
    # Verificar que el agente exista usando la función centralizada
    try:
        existing_agent = await get_agent_config(agent_id, tenant_id)
    except ServiceError as e:
        # Convertir errores de servicio en el tipo correcto para la API
        if e.error_code == ErrorCode.NOT_FOUND:
            raise AgentNotFoundError(
                message=f"Agent with ID {agent_id} not found for this tenant",
                details={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        raise e
    
    # Validar acceso al modelo si ha cambiado
    model_name = request.llm_model
    if model_name and model_name != existing_agent.get("llm_model"):
        try:
            validated_model_name = await validate_model_access(tenant_info, model_name, "llm", tenant_id=tenant_info.tenant_id)
            model_name = validated_model_name  # Usar el modelo validado
        except ServiceError as e:
            # Si el modelo no está permitido, usar el modelo por defecto para su tier
            logger.info(f"Cambiando al modelo por defecto: {e.message}")
            allowed_models = get_available_llm_models(tenant_info.subscription_tier, tenant_id=tenant_info.tenant_id)
            model_name = allowed_models[0] if allowed_models else settings.default_llm_model
            # Guardar información sobre el downgrade para incluirla en la respuesta
            request.metadata = request.metadata or {}
            request.metadata["model_downgraded"] = True
    else:
        # Mantener el modelo existente si no se proporciona uno nuevo
        model_name = existing_agent.get("llm_model")
    
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
        "metadata": request.metadata or existing_agent.get("metadata", {}),
        "rag_config": request.rag_config.dict() if request.rag_config else existing_agent.get("rag_config", {}),
        "updated_at": "NOW()"
    }
    
    try:
        # Actualizar el agente usando la función centralizada
        updated_agent = await update_agent_config(agent_id, update_data, tenant_id)
        
        # Invalidar caché del agente usando la función centralizada
        await invalidate_agent_config_cache(tenant_id, agent_id)
        
        # Invalidar caché de configuraciones para este tenant
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
        error_context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "update_agent", "error_type": type(e).__name__}
        logger.error(f"Error actualizando agente: {str(e)}", extra=error_context, exc_info=True)
        raise ServiceError(
            message="Error actualizando agente",
            error_code=ErrorCode.AGENT_UPDATE_ERROR,
            details=error_context
        ) from e

@router.delete("/{agent_id}", response_model=DeleteAgentResponse)
@with_context(tenant=True, agent=True)
@handle_errors(error_type="simple", log_traceback=False)
async def delete_agent(
    agent_id: str, 
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> DeleteAgentResponse:
    """Elimina un agente específico y sus conversaciones asociadas."""
    tenant_id = tenant_info.tenant_id
    
    # Verificar que el agente exista usando la función centralizada
    try:
        existing_agent = await get_agent_config(agent_id, tenant_id)
    except ServiceError as e:
        # Convertir errores de servicio en el tipo correcto para la API
        if e.error_code == ErrorCode.NOT_FOUND:
            raise AgentNotFoundError(
                message=f"Agent with ID {agent_id} not found for this tenant",
                details={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        raise e
    
    try:
        # Eliminar el agente usando la función centralizada
        await delete_agent_config(agent_id, tenant_id)
        
        # También eliminar las conversaciones asociadas (esto podría moverse a delete_agent_config)
        supabase = get_supabase_client()
        conv_result = await supabase.table(get_table_name("agent_conversations")) \
            .delete() \
            .eq("tenant_id", tenant_id) \
            .eq("agent_id", agent_id) \
            .execute()
        
        deleted_conversations = len(conv_result.data) if conv_result.data else 0
        
        # Invalidar cachés relacionadas con este agente usando la función centralizada
        await invalidate_agent_config_cache(tenant_id, agent_id)
        
        return DeleteAgentResponse(
            success=True,
            message="Agente eliminado exitosamente",
            agent_id=agent_id,
            tenant_id=tenant_id,
            deleted_conversations=deleted_conversations
        )
    
    except Exception as e:
        error_context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "delete_agent", "error_type": type(e).__name__}
        logger.error(f"Error eliminando agente: {str(e)}", extra=error_context, exc_info=True)
        raise ServiceError(
            message="Error eliminando agente",
            error_code=ErrorCode.AGENT_DELETION_ERROR,
            details=error_context
        ) from e