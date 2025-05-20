"""
Implementación del servicio de agentes utilizando LangChain.
"""

import logging
import time
import uuid
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage

from common.context import Context, with_context
from common.db import get_supabase_client
from common.errors.handlers import handle_errors, ServiceError
from common.cache import CacheManager, get_with_cache_aside
from common.tracking import track_token_usage, track_performance_metric
from common.config import get_settings
from common.config.tiers import get_tier_limits, get_available_llm_models, get_available_embedding_models
from common.langchain import standardize_langchain_metadata

from config import (
    TABLE_AGENTS, TABLE_CONVERSATIONS, TABLE_CONVERSATION_MESSAGES,
    AGENT_STATE_CREATED, AGENT_STATE_ACTIVE, AGENT_STATE_PAUSED, AGENT_STATE_DELETED,
    OPERATION_AGENT_CHAT, OPERATION_AGENT_RAG, TOKEN_TYPE_LLM
)

from models import (
    Agent, AgentCreate, AgentUpdate, AgentState, AgentType,
    ChatRequest, ChatResponse, ConversationMessage, MessageRole,
    AgentConfig, AgentResponse
)

from services.service_registry import ServiceRegistry
from services.memory_manager import ConversationMemoryManager
from services.configuration_service import AgentConfigurationService
from services.workflow_manager import AgentWorkflowManager
from tools.registry import ToolRegistry
from tools.utils import get_langchain_chat_model, convert_to_langchain_messages, create_langchain_agent
from tools.external_api import ExternalAPITool

logger = logging.getLogger(__name__)

class LangChainAgentService:
    """
    Servicio para gestionar agentes utilizando LangChain.

    Implementa funcionalidades para creación y ejecución de agentes,
    gestión de memoria de conversación, workflows complejos, y soporte
    para un editor visual en el frontend.
    """

    def __init__(self):
        """Inicializa el servicio de agentes con componentes necesarios."""
        self.settings = get_settings()
        self.service_registry = ServiceRegistry()
        self.tool_registry = ToolRegistry()

        # Inicializar gestores especializados
        self.memory_manager = ConversationMemoryManager(self.service_registry)
        self.config_service = AgentConfigurationService(self.service_registry)
        self.workflow_manager = AgentWorkflowManager(self.service_registry)

        # Tracking y optimización
        self.use_cache = True  # Flag para control de caché

    async def initialize(self):
        """Inicializa los componentes del servicio."""
        await self.tool_registry.initialize()

        # Log de inicialización
        logger.info(
            "LangChainAgentService inicializado",
            extra={
                "components": [
                    "memory_manager", 
                    "config_service", 
                    "workflow_manager",
                    "tool_registry"
                ]
            }
        )
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def create_agent(self, agent_config: AgentConfig, ctx: Context = None) -> str:
        """
        Crea un nuevo agente basado en la configuración proporcionada.
        
        Args:
            agent_config: Configuración detallada del agente
            ctx: Contexto de la operación con tenant_id
            
        Returns:
            str: ID del agente creado
        """
        tenant_id = ctx.get_tenant_id()
        start_time = time.time()
        
        # Verificar límites según el tier del tenant
        tier = await self.service_registry.get_tenant_tier(tenant_id)
        tier_limits = get_tier_limits(tier, tenant_id)
        
        # Contar agentes existentes y verificar límite
        supabase = await get_supabase_client()
        existing_agents = await supabase.table(TABLE_AGENTS)\
            .select("id")\
            .eq("tenant_id", tenant_id)\
            .neq("state", AGENT_STATE_DELETED)\
            .execute()
        
        if len(existing_agents.data) >= tier_limits.get("max_agents", 1):
            raise ServiceError(
                "Maximum number of agents reached for this tier",
                error_code="MAX_AGENTS_REACHED",
                status_code=429,
                context={"tenant_id": tenant_id, "tier": tier, "limit": tier_limits.get("max_agents", 1)}
            )
        
        # Validar configuración del agente
        if not agent_config.name or not agent_config.description:
            raise ServiceError(
                "Agent name and description are required",
                error_code="INVALID_AGENT_CONFIG",
                status_code=400
            )
        
        # Validar acceso al modelo según el tier
        llm_model = agent_config.llm_config.get("model", self.settings.DEFAULT_LLM_MODEL)
        available_models = get_available_llm_models(tier, tenant_id)
        if llm_model not in available_models:
            raise ServiceError(
                f"Model {llm_model} not available for tier {tier}",
                error_code="MODEL_NOT_AVAILABLE",
                status_code=403,
                context={"tenant_id": tenant_id, "model": llm_model, "tier": tier}
            )
        
        # Generar agent_id único
        agent_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        # Preparar configuración del agente para almacenar
        agent_data = {
            "id": agent_id,
            "tenant_id": tenant_id,
            "name": agent_config.name,
            "description": agent_config.description,
            "type": agent_config.type or "RAG",
            "state": AGENT_STATE_CREATED,
            "configuration": agent_config.model_dump(),
            "created_at": now,
            "updated_at": now
        }
        
        # Guardar el agente en la base de datos
        await supabase.table(TABLE_AGENTS).insert(agent_data).execute()
        
        # Guardar configuración en caché para acceso rápido
        await CacheManager.set(
            data_type="agent_config",
            resource_id=agent_id,
            value=agent_config.model_dump(),
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard  # Usar TTL estándar según las guías
        )
        
        # Registrar métricas de rendimiento
        execution_time = time.time() - start_time
        await track_performance_metric(
            operation="create_agent",
            execution_time=execution_time,
            metadata={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "agent_type": agent_config.type
            }
        )
        
        logger.info(
            f"Agent created: {agent_id}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "execution_time": execution_time
            }
        )
        
        return agent_id
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_agent_config(self, agent_id: str, ctx: Context = None) -> AgentConfig:
        """
        Obtiene la configuración de un agente utilizando el patrón Cache-Aside.
        
        Args:
            agent_id: ID del agente
            ctx: Contexto de la operación
            
        Returns:
            AgentConfig: Configuración del agente
        """
        tenant_id = ctx.get_tenant_id()
        start_time = time.time()
        
        # Utilizar el patrón Cache-Aside mediante el helper centralizado
        config_data, metrics = await get_with_cache_aside(
            data_type="agent_config",
            resource_id=agent_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_agent_config_from_db,
            generate_func=None,  # No generación automática
            agent_id=agent_id
        )
        
        if not config_data:
            raise ServiceError(
                f"Agent config not found: {agent_id}",
                error_code="AGENT_CONFIG_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Registrar métricas
        execution_time = time.time() - start_time
        logger.info(
            f"Agent config retrieved: {agent_id}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "execution_time": execution_time,
                **metrics
            }
        )
        
        # Convertir el diccionario a modelo AgentConfig
        return AgentConfig.model_validate(config_data)
    
    async def _fetch_agent_config_from_db(self, tenant_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Función auxiliar para obtener la configuración de un agente desde la base de datos.
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID del agente
            
        Returns:
            Dict[str, Any]: Configuración del agente o None si no existe
        """
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_AGENTS)\
            .select("configuration")\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .neq("state", AGENT_STATE_DELETED)\
            .single()\
            .execute()
        
        if not result.data:
            return None
            
        return result.data.get("configuration")
    
@handle_errors(error_type="service", log_traceback=True)
@with_context(tenant=True)
async def get_agent_config(self, agent_id: str, ctx: Context = None) -> AgentConfig:
    """
    Obtiene la configuración de un agente utilizando el patrón Cache-Aside.
        
    Args:
        agent_id: ID del agente
        ctx: Contexto de la operación
            
    Returns:
        AgentConfig: Configuración del agente
    """
    tenant_id = ctx.get_tenant_id()
    start_time = time.time()
        
    # Utilizar el patrón Cache-Aside mediante el helper centralizado
    config_data, metrics = await get_with_cache_aside(
        data_type="agent_config",
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=self._fetch_agent_config_from_db,
        generate_func=None,  # No generación automática
        agent_id=agent_id
    )
        
    if not config_data:
        raise ServiceError(
            f"Agent config not found: {agent_id}",
            error_code="AGENT_CONFIG_NOT_FOUND",
            status_code=404,
            context={"tenant_id": tenant_id, "agent_id": agent_id}
        )
        
    # Registrar métricas
    execution_time = time.time() - start_time
    logger.info(
        f"Agent config retrieved: {agent_id}",
        extra={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "execution_time": execution_time,
            **metrics
        }
    )
        
    # Convertir el diccionario a modelo AgentConfig
    return AgentConfig.model_validate(config_data)
    
async def _fetch_agent_config_from_db(self, tenant_id: str, agent_id: str) -> Dict[str, Any]:
    """
    Función auxiliar para obtener la configuración de un agente desde la base de datos.
        
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
            
    Returns:
        Dict[str, Any]: Configuración del agente o None si no existe
    """
    supabase = await get_supabase_client()
    result = await supabase.table(TABLE_AGENTS)\
        .select("configuration")\
        .eq("id", agent_id)\
        .eq("tenant_id", tenant_id)\
        .neq("state", AGENT_STATE_DELETED)\
        .single()\
        .execute()
        
    if not result.data:
        return None
            
    return result.data.get("configuration")
    
@handle_errors(error_type="service", log_traceback=True)
@with_context(tenant=True, agent=True, conversation=True)
async def execute_agent(self, agent_id: str, chat_request: ChatRequest, ctx: Context = None) -> AgentResponse:
    """
    Ejecuta un agente con una petición de chat y devuelve su respuesta.
        
    Args:
        agent_id: ID del agente a ejecutar
        chat_request: Petición del usuario
        ctx: Contexto de ejecución
            
    Returns:
        Respuesta del agente con el mensaje, metadatos y referencias utilizadas
            
    Raises:
        ServiceError: Si ocurre un error durante la ejecución del agente
    """
    start_time = time.time()
    tenant_id = ctx.get_tenant_id()
    conversation_id = chat_request.conversation_id
        
    # Establecer valores en contexto
    ctx.set_agent_id(agent_id)
    ctx.set_conversation_id(conversation_id)
        
    # Metadatos básicos para seguimiento
    base_metadata = {
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "user_message": chat_request.message[:100] + "..." if len(chat_request.message) > 100 else chat_request.message,
        "tenant_id": tenant_id
    }
    standardized_metadata = standardize_langchain_metadata(
        metadata=base_metadata,
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        ctx=ctx
    )
        
    # Paso 1: Obtener configuración del agente (con caché)
    logger.info(f"Obteniendo configuración del agente: {agent_id}", extra=standardized_metadata)
    agent_config = await self.config_service.get_agent_config(agent_id, tenant_id, ctx=ctx)
        
    # Paso 2: Obtener memoria de conversación
    logger.info(f"Obteniendo memoria de conversación: {conversation_id}", extra=standardized_metadata)
    conversation_memory = await self.memory_manager.get_memory(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        ctx=ctx
    )
        
    # Cargar mensajes específicos usando el nuevo método
    logger.debug(f"Cargando mensajes de conversación: {conversation_id}", extra=standardized_metadata)
    conversation_messages = await self.memory_manager.get_messages(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        ctx=ctx
    )
        
    # Inicializar memoria de LangChain
    langchain_memory = ConversationBufferMemory(
        return_messages=True,
        memory_key="chat_history"
    )
        
    # Cargar mensajes previos en la memoria de LangChain (si existen)
    if conversation_messages:
        logger.debug(f"Cargando {len(conversation_messages)} mensajes previos en LangChain", 
                   extra=standardized_metadata)
        for msg in conversation_messages:
            if msg["role"] == "user":
                langchain_memory.chat_memory.add_user_message(msg["content"])
            elif msg["role"] == "assistant":
                langchain_memory.chat_memory.add_ai_message(msg["content"])
            elif msg["role"] == "system" and hasattr(langchain_memory.chat_memory, "add_system_message"):
                # Solo si el modelo de memoria soporta mensajes de sistema
                langchain_memory.chat_memory.add_system_message(msg["content"])
        
    # Paso 3: Preparar herramientas para el agente
    logger.info(f"Preparando herramientas para el agente: {agent_id}", extra=standardized_metadata)
    tools = await self._get_tools_for_agent(agent_config, tenant_id, standardized_metadata, ctx=ctx)
        
    # Paso 4: Preparar LLM para el agente
    logger.info(f"Preparando LLM para el agente: {agent_id}", extra=standardized_metadata)
    llm = self._get_llm_for_agent(agent_config)
        
    # Paso 5: Crear agente de LangChain
    logger.info(f"Creando agente de LangChain: {agent_id}", extra=standardized_metadata)
    agent = self._create_agent(
        llm=llm,
        tools=tools,
        agent_type=agent_config.agent_type,
        context=agent_config.context,
        memory=conversation_memory,  # Mantener compatibilidad con el dict de memoria global
        tenant_id=tenant_id
    )
        
    # Establecer la memoria de mensajes individuales en el agente si es posible
    if hasattr(agent, "memory") and langchain_memory.chat_memory.messages:
        agent.memory = langchain_memory
        
    # Añadir el mensaje del usuario a la caché antes de ejecutar
    # (permite ver el historial completo incluso antes de la respuesta)
    user_message_id = await self.memory_manager.add_message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role="user",
        content=chat_request.message,
        metadata={
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat()
        },
        ctx=ctx
    )
        
    # Paso 6: Ejecutar agente con mensaje del usuario
    logger.info(f"Ejecutando agente LangChain: {agent_id}", extra=standardized_metadata)
    try:
        agent_response = await agent.arun(
            input=chat_request.message,
            callbacks=self._create_callbacks(tenant_id, agent_id, conversation_id)
        )
        execution_time = time.time() - start_time
            
        # Agregar metadatos de respuesta
        response_metadata = {
            **standardized_metadata,
            "execution_time": execution_time,
            "token_usage": {"prompt": 0, "completion": 0, "total": 0},  # Actualizar con datos reales
            "llm_model": agent_config.llm_config.model,
            "references": []  # Actualizar si hay referencias
        }
            
        # Almacenar la respuesta del asistente en caché como mensaje individual
        assistant_message_id = await self.memory_manager.add_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content=agent_response,
            metadata={
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
                "execution_time": execution_time,
                "user_message_id": user_message_id  # Referencia al mensaje del usuario
            },
            ctx=ctx
        )
            
        # Paso 7: Guardar memoria actualizada (compatibilidad con memoria global)
        logger.info(f"Guardando memoria actualizada: {conversation_id}", extra=standardized_metadata)
        await self.memory_manager.save_memory(
            tenant_id=tenant_id, 
            conversation_id=conversation_id, 
            memory_dict=agent.memory.dict(), 
            ctx=ctx
        )
            
        # Construir respuesta final
        response = AgentResponse(
            message=agent_response,
            metadata=response_metadata,
            references=[]
        )
            
        logger.info(f"Agente ejecutado correctamente: {agent_id}", 
                    extra={**standardized_metadata, "execution_time": execution_time})
            
        return response
            
    except Exception as e:
        error_message = f"Error al ejecutar agente: {str(e)}"
        logger.error(error_message, extra={**standardized_metadata, "error": str(e)})
            
        # Intentar agregar un mensaje de error al historial
        try:
            await self.memory_manager.add_message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                role="system",
                content="Se produjo un error al procesar esta solicitud.",
                metadata={
                    "agent_id": agent_id,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                    "user_message_id": user_message_id
                },
                ctx=ctx
            )
        except Exception as mem_error:
            logger.warning(f"No se pudo agregar mensaje de error: {str(mem_error)}", 
                         extra=standardized_metadata)
        
        # Propagar la excepción original para manejo de errores consistente
        raise ServiceError(
            message=error_message,
            context={
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "error": str(e)
            }
        )
    
    async def _get_tools_for_agent(self, agent_config: AgentConfig, tenant_id: str, conversation_id: str, ctx: Context = None) -> List[BaseTool]:
        """
        Configura las herramientas para el agente basado en su configuración.
        
        Args:
            agent_config: Configuración del agente
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            ctx: Contexto de la operación
            
        Returns:
            List[BaseTool]: Lista de herramientas LangChain configuradas
        """
        tools = []
        agent_id = ctx.get_agent_id() if ctx else None
        
        # Verificar los límites de herramientas según el tier
        tier = await self.service_registry.get_tenant_tier(tenant_id, ctx=ctx)
        tier_limits = get_tier_limits(tier, tenant_id)
        max_tools = tier_limits.get("max_tools_per_agent", 3)
        
        # Agregar herramientas configuradas (limitadas por el tier)
        for tool_config in agent_config.tools[:max_tools]:
            tool_type = tool_config.get("type")
            
            # Estandarizar metadatos base para todas las herramientas
            base_metadata = standardize_langchain_metadata(
                metadata=tool_config.get("metadata", {}),
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                ctx=ctx
            )
            
            if tool_type == "retrieval":
                # Herramienta de recuperación RAG
                collection_ids = tool_config.get("collection_ids", [])
                if collection_ids:
                    # Añadir ID de colecciones a los metadatos estandarizados
                    collection_id = collection_ids[0] if collection_ids else None
                    rag_metadata = standardize_langchain_metadata(
                        metadata=base_metadata,
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        collection_id=collection_id,
                        ctx=ctx
                    )
                    
                    retrieval_tool = await self.tool_registry.get_tool(
                        "retrieval",
                        tenant_id=tenant_id,
                        collection_ids=collection_ids,
                        top_k=tier_limits.get("similarity_top_k", 4),
                        metadata=rag_metadata
                    )
                    if retrieval_tool:
                        tools.append(retrieval_tool)
            
            elif tool_type == "external_api":
                # Herramienta de API externa
                api_config = tool_config.get("config", {})
                if api_config and "base_url" in api_config:
                    # Estandarizar metadatos para la API externa
                    api_metadata = standardize_langchain_metadata(
                        metadata=base_metadata,
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        ctx=ctx
                    )
                    
                    # Incluir información adicional relevante para la API
                    api_metadata["api_endpoint"] = api_config.get("base_url")
                    api_metadata["api_auth_type"] = api_config.get("auth_type")
                    
                    api_tool = ExternalAPITool(
                        name=tool_config.get("name", "external_api"),
                        description=tool_config.get("description", "Access an external API"),
                        base_url=api_config.get("base_url"),
                        auth_type=api_config.get("auth_type"),
                        auth_config=api_config.get("auth_config", {}),
                        tenant_id=tenant_id,
                        metadata=api_metadata
                    )
                    tools.append(api_tool)
            
            elif tool_type in self.tool_registry.available_tools:
                # Cualquier otra herramienta en el registro
                # Preparar configuración con metadatos estandarizados
                tool_config_with_metadata = tool_config.get("config", {}).copy()
                tool_config_with_metadata["metadata"] = standardize_langchain_metadata(
                    metadata=base_metadata,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    ctx=ctx
                )
                
                tool = await self.tool_registry.get_tool(
                    tool_type,
                    tenant_id=tenant_id,
                    **tool_config_with_metadata
                )
                if tool:
                    tools.append(tool)
        
        return tools
    
    def _get_model_details(self, model_name: str) -> Dict[str, Any]:
        """
        Obtiene detalles del modelo para tracking adecuado de tokens.
        
        Args:
            model_name: Nombre del modelo LLM
            
        Returns:
            Dict[str, Any]: Detalles del modelo como proveedor y contexto máximo
        """
        # Por ahora, detalles básicos
        # En el futuro, usar common.config.tiers.get_llm_model_details
        if "gpt-4" in model_name:
            return {
                "provider": "openai",
                "context_size": 8192 if "8k" in model_name else 32768
            }
        elif "gpt-3.5" in model_name:
            return {
                "provider": "openai",
                "context_size": 16384
            }
        # Añadir más modelos según sea necesario
        return {
            "provider": "unknown",
            "context_size": 4096
        }
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True)
    async def update_agent_config(self, agent_id: str, agent_config: AgentConfig, ctx: Context = None) -> bool:
        """
        Actualiza la configuración de un agente existente.
        
        Args:
            agent_id: ID del agente a actualizar
            agent_config: Nueva configuración del agente
            ctx: Contexto con tenant_id y agent_id
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        tenant_id = ctx.get_tenant_id()
        start_time = time.time()
        
        # Verificar que el agente existe
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_AGENTS)\
            .select("id, state")\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise ServiceError(
                f"Agent not found: {agent_id}",
                error_code="AGENT_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Verificar que el agente no está eliminado
        if result.data.get("state") == AGENT_STATE_DELETED:
            raise ServiceError(
                f"Cannot update deleted agent: {agent_id}",
                error_code="AGENT_DELETED",
                status_code=400,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Validar acceso al modelo según el tier
        tier = await self.service_registry.get_tenant_tier(tenant_id)
        llm_model = agent_config.llm_config.get("model", self.settings.DEFAULT_LLM_MODEL)
        available_models = get_available_llm_models(tier, tenant_id)
        
        if llm_model not in available_models:
            raise ServiceError(
                f"Model {llm_model} not available for tier {tier}",
                error_code="MODEL_NOT_AVAILABLE",
                status_code=403,
                context={"tenant_id": tenant_id, "model": llm_model, "tier": tier}
            )
        
        # Validar configuración del agente
        if not agent_config.name or not agent_config.description:
            raise ServiceError(
                "Agent name and description are required",
                error_code="INVALID_AGENT_CONFIG",
                status_code=400
            )
            
        # Preparar datos actualizados
        now = datetime.now().isoformat()
        update_data = {
            "name": agent_config.name,
            "description": agent_config.description,
            "type": agent_config.type or "RAG",
            "configuration": agent_config.model_dump(),
            "updated_at": now
        }
        
        # Actualizar en base de datos
        await supabase.table(TABLE_AGENTS)\
            .update(update_data)\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .execute()
        
        # Actualizar en caché
        await CacheManager.set(
            data_type="agent_config",
            resource_id=agent_id,
            value=agent_config.model_dump(),
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
        
        # Registrar métricas de rendimiento
        execution_time = time.time() - start_time
        await track_performance_metric(
            operation="update_agent_config",
            execution_time=execution_time,
            metadata={
                "tenant_id": tenant_id,
                "agent_id": agent_id
            }
        )
        
        logger.info(
            f"Agent config updated: {agent_id}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "execution_time": execution_time
            }
        )
        
        return True
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True)
    async def delete_agent(self, agent_id: str, ctx: Context = None) -> bool:
        """
        Marca un agente como eliminado (soft delete).
        
        Args:
            agent_id: ID del agente a eliminar
            ctx: Contexto con tenant_id y agent_id
            
        Returns:
            bool: True si la eliminación fue exitosa
        """
        tenant_id = ctx.get_tenant_id()
        
        # Verificar que el agente existe
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_AGENTS)\
            .select("id, state")\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise ServiceError(
                f"Agent not found: {agent_id}",
                error_code="AGENT_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Marcar como eliminado
        now = datetime.now().isoformat()
        await supabase.table(TABLE_AGENTS)\
            .update({"state": AGENT_STATE_DELETED, "updated_at": now})\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .execute()
        
        # Invalidar caché
        await CacheManager.delete(
            data_type="agent_config",
            resource_id=agent_id,
            tenant_id=tenant_id
        )
        
        logger.info(
            f"Agent deleted: {agent_id}",
            extra={"tenant_id": tenant_id, "agent_id": agent_id}
        )
        
        return True
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def list_agents(self, ctx: Context = None) -> List[Dict[str, Any]]:
        """
        Lista todos los agentes activos para un tenant.
        
        Args:
            ctx: Contexto con tenant_id
            
        Returns:
            List[Dict[str, Any]]: Lista de agentes
        """
        tenant_id = ctx.get_tenant_id()
        
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_AGENTS)\
            .select("id, name, description, type, state, created_at, updated_at")\
            .eq("tenant_id", tenant_id)\
            .neq("state", AGENT_STATE_DELETED)\
            .order("created_at", desc=True)\
            .execute()
        
        return result.data or []
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True, conversation=True)
    async def get_conversation_history(self, conversation_id: str, ctx: Context = None) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de una conversación.
        
        Args:
            conversation_id: ID de la conversación
            ctx: Contexto con tenant_id, agent_id y conversation_id
            
        Returns:
            List[Dict[str, Any]]: Mensajes de la conversación
        """
        tenant_id = ctx.get_tenant_id()
        agent_id = ctx.get_agent_id()
        
        # Utilizar el memory manager para obtener los mensajes
        conversation_memory = await self.memory_manager.get_memory(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            ctx=ctx
        )
        
        if not conversation_memory or "messages" not in conversation_memory:
            return []
            
        return conversation_memory["messages"]
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, conversation=True)
    async def create_conversation(self, agent_id: str, ctx: Context = None) -> str:
        """
        Crea una nueva conversación para un agente.
        
        Args:
            agent_id: ID del agente
            ctx: Contexto con tenant_id
            
        Returns:
            str: ID de la conversación creada
        """
        tenant_id = ctx.get_tenant_id()
        
        # Verificar que el agente existe
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_AGENTS)\
            .select("id")\
            .eq("id", agent_id)\
            .eq("tenant_id", tenant_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise ServiceError(
                f"Agent not found: {agent_id}",
                error_code="AGENT_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Crear conversación
        conversation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        conversation_data = {
            "id": conversation_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "created_at": now,
            "updated_at": now
        }
        
        await supabase.table(TABLE_CONVERSATIONS).insert(conversation_data).execute()
        
        # Inicializar memoria vacía
        await self.memory_manager.save_memory(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            memory_data={"messages": []},
            ctx=ctx
        )
        
        logger.info(
            f"Conversation created: {conversation_id}",
            extra={"tenant_id": tenant_id, "agent_id": agent_id, "conversation_id": conversation_id}
        )
        
        return conversation_id
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_agent_conversations(self, agent_id: str, ctx: Context = None) -> List[Dict[str, Any]]:
        """
        Obtiene las conversaciones asociadas a un agente.
        
        Args:
            agent_id: ID del agente
            ctx: Contexto con tenant_id
            
        Returns:
            List[Dict[str, Any]]: Lista de conversaciones
        """
        tenant_id = ctx.get_tenant_id()
        
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_CONVERSATIONS)\
            .select("id, created_at, updated_at")\
            .eq("tenant_id", tenant_id)\
            .eq("agent_id", agent_id)\
            .order("created_at", desc=True)\
            .execute()
        
        return result.data or []
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True, conversation=True)
    async def clear_conversation_history(self, conversation_id: str, ctx: Context = None) -> bool:
        """
        Limpia el historial de una conversación (mantiene la conversación pero elimina mensajes).
        
        Args:
            conversation_id: ID de la conversación
            ctx: Contexto con tenant_id y agent_id
            
        Returns:
            bool: True si se limpió correctamente
        """
        tenant_id = ctx.get_tenant_id()
        agent_id = ctx.get_agent_id()
        
        # Verificar que la conversación existe y pertenece al tenant y agente
        supabase = await get_supabase_client()
        result = await supabase.table(TABLE_CONVERSATIONS)\
            .select("id")\
            .eq("id", conversation_id)\
            .eq("tenant_id", tenant_id)\
            .eq("agent_id", agent_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise ServiceError(
                f"Conversation not found: {conversation_id}",
                error_code="CONVERSATION_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id, "conversation_id": conversation_id}
            )
        
        # Reiniciar la memoria
        await self.memory_manager.save_memory(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            memory_data={"messages": []},
            ctx=ctx
        )
        
        logger.info(
            f"Conversation history cleared: {conversation_id}",
            extra={"tenant_id": tenant_id, "agent_id": agent_id, "conversation_id": conversation_id}
        )
        
        return True
        
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True)
    async def get_agent_metrics(self, agent_id: str, period: str = "day", ctx: Context = None) -> Dict[str, Any]:
        """
        Obtiene métricas de uso para un agente.
        
        Args:
            agent_id: ID del agente
            period: Período de tiempo (day, week, month)
            ctx: Contexto con tenant_id y agent_id
            
        Returns:
            Dict[str, Any]: Métricas del agente
        """
        tenant_id = ctx.get_tenant_id()
        
        # Construir una clave para la caché de métricas
        cache_key = f"metrics:{agent_id}:{period}"
        
        # Intentar obtener métricas de la caché
        cached_metrics = await CacheManager.get(
            data_type="agent_metrics",
            resource_id=cache_key,
            tenant_id=tenant_id,
            agent_id=agent_id
        )
        
        if cached_metrics:
            return cached_metrics
        
        # Calcular métricas desde la base de datos si no están en caché
        metrics = {
            "total_conversations": 0,
            "total_messages": 0,
            "token_usage": 0,
            "average_response_time": 0,
            "period": period
        }
        
        # Obtener conversaciones
        supabase = await get_supabase_client()
        conversations = await supabase.table(TABLE_CONVERSATIONS)\
            .select("id")\
            .eq("tenant_id", tenant_id)\
            .eq("agent_id", agent_id)\
            .execute()
        
        metrics["total_conversations"] = len(conversations.data or [])
        
        # En una implementación real, aquí habría más lógica para calcular las métricas
        # a partir de la base de datos y los sistemas de tracking
        
        # Guardar métricas en caché
        ttl = 300  # 5 minutos para métricas
        await CacheManager.set(
            data_type="agent_metrics",
            resource_id=cache_key,
            value=metrics,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ttl=ttl
        )
        
        return metrics
