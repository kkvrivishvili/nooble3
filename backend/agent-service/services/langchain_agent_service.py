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
from common.cache.helpers import standardize_llama_metadata

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
        # Esta verificación se implementará con el sistema de tiers centralizado
        tier = await self.service_registry.get_tenant_tier(tenant_id)
        tier_limits = get_tier_limits(tier, tenant_id)
        
        # Contar agentes existentes y verificar límite
        supabase = await get_supabase_client()
        existing_agents = await supabase.table(TABLE_AGENTS)\
            .select("id")\
            .eq("tenant_id", tenant_id)\
            .eq("state", "ne", AGENT_STATE_DELETED)\
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
        config_key = f"agent_config:{agent_id}"
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
            ctx: Contexto de la operación con tenant_id
            
        Returns:
            AgentConfig: Configuración del agente
        """
        tenant_id = ctx.get_tenant_id()
        
        # Definir función para obtener la configuración desde la base de datos
        async def fetch_from_db(agent_id):
            supabase = await get_supabase_client()
            result = await supabase.table(TABLE_AGENTS)\
                .select("configuration")\
                .eq("id", agent_id)\
                .eq("tenant_id", tenant_id)\
                .single()\
                .execute()
                
            if not result.data:
                return None
                
            return result.data.get("configuration")
        
        # Utilizar el patrón Cache-Aside según los estándares
        config_data, metrics = await get_with_cache_aside(
            data_type="agent_config",
            resource_id=agent_id,
            tenant_id=tenant_id,
            fetch_from_db_func=lambda: fetch_from_db(agent_id),
            generate_func=None,  # No hay función de generación, solo lectura
            agent_id=agent_id  # Para generar correctamente las claves jerárquicas
        )
        
        if not config_data:
            raise ServiceError(
                f"Agent not found: {agent_id}",
                error_code="AGENT_NOT_FOUND",
                status_code=404,
                context={"tenant_id": tenant_id, "agent_id": agent_id}
            )
        
        # Convertir el diccionario a modelo AgentConfig
        return AgentConfig.model_validate(config_data)
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True, agent=True, conversation=True)
    async def execute_agent(self, agent_id: str, chat_request: ChatRequest, ctx: Context = None) -> AgentResponse:
        """
        Ejecuta un agente con memoria de conversación y herramientas configuradas.
        
        Args:
            agent_id: ID del agente a ejecutar
            chat_request: Solicitud de chat que contiene el mensaje del usuario
            ctx: Contexto con tenant_id, agent_id y conversation_id
            
        Returns:
            AgentResponse: Respuesta del agente con contenido y metadatos
        """
        tenant_id = ctx.get_tenant_id()
        conversation_id = ctx.get_conversation_id()
        start_time = time.time()
        
        # Paso 1: Obtener configuración del agente
        agent_config = await self.get_agent_config(agent_id, ctx)
        
        # Paso 2: Verificar si se trata de un workflow y ejecutarlo si es así
        if agent_config.workflow_enabled and agent_config.workflow_definition:
            return await self.workflow_manager.execute_workflow(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                user_input=chat_request.message,
                workflow_definition=agent_config.workflow_definition,
                ctx=ctx
            )
        
        # Paso 3: Obtener memoria de conversación
        conversation_memory = await self.memory_manager.get_memory(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            ctx=ctx
        )
        
        # Paso 4: Configurar herramientas del agente
        tools = await self._get_tools_for_agent(agent_config, tenant_id, conversation_id, ctx)
        
        # Paso 5: Preparar el modelo LLM con la configuración adecuada
        llm_model = agent_config.llm_config.get("model", self.settings.DEFAULT_LLM_MODEL)
        llm = get_langchain_chat_model(
            model=llm_model,
            temperature=agent_config.llm_config.get("temperature", 0.7),
            api_key=self.settings.OPENAI_API_KEY
        )
        
        # Paso 6: Crear el agente con la configuración y herramientas
        langchain_memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="chat_history"
        )
        
        # Cargar mensajes previos en la memoria de LangChain
        if conversation_memory and "messages" in conversation_memory:
            for msg in conversation_memory["messages"]:
                if msg["role"] == "user":
                    langchain_memory.chat_memory.add_user_message(msg["content"])
                elif msg["role"] == "assistant":
                    langchain_memory.chat_memory.add_ai_message(msg["content"])
        
        # Crear el agente con LangChain
        agent_executor = create_langchain_agent(
            llm=llm,
            tools=tools,
            memory=langchain_memory,
            agent_type=agent_config.agent_type or "CONVERSATIONAL_REACT",
            system_message=agent_config.system_message
        )
        
        # Paso 7: Ejecutar el agente y capturar su respuesta
        request_id = str(uuid.uuid4())
        logger.info(
            f"Executing agent {agent_id}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "request_id": request_id
            }
        )
        
        try:
            # Ejecutar el agente
            response = await agent_executor.ainvoke({"input": chat_request.message})
            
            # Extraer la respuesta y metadatos
            response_content = response.get("output", "")
            response_metadata = {
                "tool_calls": [],
                "execution_time": time.time() - start_time
            }
            
            # Extraer llamadas a herramientas si están disponibles
            if "intermediate_steps" in response:
                for step in response["intermediate_steps"]:
                    if len(step) >= 2:
                        tool_action = step[0]
                        tool_output = step[1]
                        response_metadata["tool_calls"].append({
                            "tool": tool_action.tool,
                            "tool_input": tool_action.tool_input,
                            "output": str(tool_output)
                        })
            
            # Paso 8: Registrar el mensaje en la memoria de conversación
            new_messages = [
                {"role": "user", "content": chat_request.message, "timestamp": datetime.now().isoformat()},
                {"role": "assistant", "content": response_content, "timestamp": datetime.now().isoformat()}
            ]
            
            # Actualizar la memoria con los nuevos mensajes
            if conversation_memory is None:
                conversation_memory = {"messages": []}
            
            conversation_memory["messages"].extend(new_messages)
            await self.memory_manager.save_memory(tenant_id, conversation_id, conversation_memory, ctx)
            
            # Paso 9: Registrar tokens usados para el tracking de uso
            idempotency_key = f"{tenant_id}:{agent_id}:{conversation_id}:{hashlib.md5(chat_request.message.encode()).hexdigest()}"
            model_details = self._get_model_details(llm_model)
            
            # Estimar tokens (entrada + salida)
            input_tokens = len(chat_request.message.split()) * 1.3  # Estimación simple
            output_tokens = len(response_content.split()) * 1.3
            
            await track_token_usage(
                tenant_id=tenant_id,
                operation=OPERATION_AGENT_CHAT,
                token_type=TOKEN_TYPE_LLM,
                token_count=int(input_tokens + output_tokens),
                model=llm_model,
                metadata={
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens)
                },
                idempotency_key=idempotency_key
            )
            
            # Paso 10: Crear y devolver la respuesta
            return AgentResponse(
                content=response_content,
                metadata=response_metadata
            )
            
        except Exception as e:
            # Registrar el error y devolver una respuesta de error
            error_msg = f"Error executing agent: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )
            
            # Aún registrar el mensaje de error en la conversación
            error_messages = [
                {"role": "user", "content": chat_request.message, "timestamp": datetime.now().isoformat()},
                {"role": "system", "content": "Error en la generación de respuesta", "timestamp": datetime.now().isoformat()}
            ]
            
            if conversation_memory is None:
                conversation_memory = {"messages": []}
                
            conversation_memory["messages"].extend(error_messages)
            await self.memory_manager.save_memory(tenant_id, conversation_id, conversation_memory, ctx)
            
            # Propagar el error
            raise ServiceError(
                message=f"Error al ejecutar el agente: {str(e)}",
                error_code="AGENT_EXECUTION_ERROR",
                status_code=500,
                context={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "original_error": str(e)
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
        
        # Verificar los límites de herramientas según el tier
        tier = await self.service_registry.get_tenant_tier(tenant_id)
        tier_limits = get_tier_limits(tier, tenant_id)
        max_tools = tier_limits.get("max_tools_per_agent", 3)
        
        # Agregar herramientas configuradas (limitadas por el tier)
        for tool_config in agent_config.tools[:max_tools]:
            tool_type = tool_config.get("type")
            
            if tool_type == "retrieval":
                # Herramienta de recuperación RAG
                collection_ids = tool_config.get("collection_ids", [])
                if collection_ids:
                    retrieval_tool = await self.tool_registry.get_tool(
                        "retrieval",
                        tenant_id=tenant_id,
                        collection_ids=collection_ids,
                        top_k=tier_limits.get("similarity_top_k", 4)
                    )
                    if retrieval_tool:
                        tools.append(retrieval_tool)
            
            elif tool_type == "external_api":
                # Herramienta de API externa
                api_config = tool_config.get("config", {})
                if api_config and "base_url" in api_config:
                    api_tool = ExternalAPITool(
                        name=tool_config.get("name", "external_api"),
                        description=tool_config.get("description", "Access an external API"),
                        base_url=api_config.get("base_url"),
                        auth_type=api_config.get("auth_type"),
                        auth_config=api_config.get("auth_config", {}),
                        tenant_id=tenant_id
                    )
                    tools.append(api_tool)
            
            elif tool_type in self.tool_registry.available_tools:
                # Cualquier otra herramienta en el registro
                tool = await self.tool_registry.get_tool(
                    tool_type,
                    tenant_id=tenant_id,
                    **tool_config.get("config", {})
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

# Fin de la clase LangChainAgentService
    collection_ids = chat_request.collection_ids or agent.collection_ids
    
    # Obtener historial de conversación
    conversation_history = []
    if agent.config.context_window > 0:
        history = await self._get_conversation_history(
            conversation_id=conversation_id,
            limit=agent.config.context_window
        )
        conversation_history.extend(history)
    
    # Añadir mensaje actual al historial
    conversation_history.append(user_message)
    
    # Convertir historial a formato LangChain
    lc_messages = []
    for msg in conversation_history:
        if msg.role == MessageRole.USER:
            lc_messages.append({
                "role": "user",
                "content": msg.content
            })
        elif msg.role == MessageRole.ASSISTANT:
            lc_messages.append({
                "role": "assistant",
                "content": msg.content
            })
    
    # Convertir a objetos de mensaje LangChain
    langchain_messages = convert_to_langchain_messages(lc_messages)
    
    # Obtener herramientas disponibles
    tools = []
    if agent.config.functions_enabled:
            tenant_id: ID del tenant
            
        Returns:
            List[Dict[str, Any]]: Lista de herramientas
        """
        # Obtener agente
        agent = await self.get_agent_by_id(agent_id, tenant_id)
        
        if not agent:
            raise ServiceError(f"Agent with ID {agent_id} not found")
        
        # Obtener herramientas desde los metadatos del agente o usar valores por defecto
        available_tools = agent.metadata.get("available_tools", [])
        if not available_tools and hasattr(agent, "available_tools"):
            available_tools = agent.available_tools or []
        
        # Obtener detalles de las herramientas desde el registro
        tools = []
        for tool_name in available_tools:
            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                tools.append(tool.to_dict())
        
        # Si el agente tiene collection_ids, añadir herramientas RAG específicas para cada colección
        if agent.collection_ids:
            for collection_id in agent.collection_ids:
                rag_tools = await self.tool_registry.get_tools_for_collection(
                    collection_id=collection_id,
                    tenant_id=tenant_id
                )
                for tool in rag_tools:
                    tools.append(tool.to_dict())
        
        return tools
    
    @with_context(tenant=True, agent=True)
    @handle_errors(error_type="service", log_traceback=True)
    async def process_chat(
        self,
        agent: Agent,
        chat_request: ChatRequest,
        tenant_id: str,
        ctx: Optional[Context] = None
    ) -> ChatResponse:
        """
        Procesa una solicitud de chat con un agente.
        
        Args:
            agent: Agente para procesar el chat
            chat_request: Solicitud de chat
            tenant_id: ID del tenant
            ctx: Contexto de la operación
            
        Returns:
            ChatResponse: Respuesta del chat
        """
        # Asegurar que estamos inicializados
        await self.initialize()
        
        # Obtener ID de conversación o crear uno nuevo
        conversation_id = chat_request.conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # Almacenar mensaje del usuario
        user_message = ConversationMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            agent_id=agent.agent_id,
            tenant_id=tenant_id,
            role=MessageRole.USER,
            content=chat_request.message,
            timestamp=datetime.utcnow(),
            metadata=chat_request.metadata
        )
        
        # Almacenar en la base de datos si está configurado
        if self.settings.store_conversations:
            await self._store_message(user_message)
        
        # Obtener configuración del modelo LLM
        model_name = agent.config.model
        temperature = agent.config.temperature
        max_tokens = agent.config.max_tokens or 800
        
        # Determinar collection_ids
        collection_ids = chat_request.collection_ids or agent.collection_ids
        
        # Obtener historial de conversación
        conversation_history = []
        if agent.config.context_window > 0:
            history = await self._get_conversation_history(
                conversation_id=conversation_id,
                limit=agent.config.context_window
            )
            conversation_history.extend(history)
        
        # Añadir mensaje actual al historial
        conversation_history.append(user_message)
        
        # Convertir historial a formato LangChain
        lc_messages = []
        for msg in conversation_history:
            if msg.role == MessageRole.USER:
                lc_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append({
                    "role": "assistant",
                    "content": msg.content
                })
        
        # Convertir a objetos de mensaje LangChain
        langchain_messages = convert_to_langchain_messages(lc_messages)
        
        # Obtener herramientas disponibles
        tools = []
        if agent.config.functions_enabled:
            # Obtener herramientas desde los metadatos del agente o usar valores por defecto
            available_tools = agent.metadata.get("available_tools", [])
            if not available_tools and hasattr(agent, "available_tools"):
                available_tools = agent.available_tools or []
            
            # Obtener detalles de las herramientas desde el registro
            tools = self.tool_registry.get_tools_for_agent(available_tools)
            
            # Si el agente tiene collection_ids, añadir herramientas RAG específicas para cada colección
            if collection_ids:
                for collection_id in collection_ids:
                    rag_tools = await self.tool_registry.get_tools_for_collection(
                        collection_id=collection_id,
                        tenant_id=tenant_id
                    )
                    tools.extend(rag_tools)
        
        # Procesar mensaje a través de LangChain
        try:
            # Obtener el modelo LLM
            llm = get_langchain_chat_model(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Si no hay herramientas disponibles o no están habilitadas
            if not tools or not agent.config.functions_enabled:
                # Crear prompt con sistema y mensajes
                prompt = agent.config.system_prompt + "\n\n"
                
                # Preparar mensajes para el LLM
                messages = [{"role": "system", "content": agent.config.system_prompt}]
                
                # Añadir historial de conversación
                for msg in conversation_history:
                    role = "user" if msg.role == MessageRole.USER else "assistant"
                    messages.append({"role": role, "content": msg.content})
                
                # Generar respuesta
                start_time = time.time()
                llm_response = await llm.ainvoke(messages)
                response_text = llm_response.content
                
                # Obtener uso de tokens desde la respuesta si está disponible
                tokens = 0
                if hasattr(llm_response, "usage") and llm_response.usage:
                    tokens = llm_response.usage.total_tokens
                
                # Preparar metadatos
                metadata = {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "execution_time": time.time() - start_time,
                    "total_tokens": tokens,
                }
            else:
                # Crear un agente con las herramientas
                agent_executor = create_langchain_agent(
                    llm=llm,
                    tools=tools,
                    system_prompt=agent.config.system_prompt
                )
                
                # Configurar cada herramienta con el contexto
                for tool in tools:
                    if hasattr(tool, "tenant_id"):
                        tool.tenant_id = tenant_id
                    if hasattr(tool, "agent_id"):
                        tool.agent_id = agent.agent_id
                    if hasattr(tool, "conversation_id"):
                        tool.conversation_id = conversation_id
                    if hasattr(tool, "ctx"):
                        tool.ctx = ctx
                
                # Ejecutar el agente
                start_time = time.time()
                result = await run_agent_with_tools(
                    agent_executor=agent_executor,
                    user_input=chat_request.message,
                    chat_history=langchain_messages,
                    tenant_id=tenant_id,
                    agent_id=agent.agent_id,
                    conversation_id=conversation_id,
                    ctx=ctx
                )
                
                # Extraer respuesta y metadatos
                response_text = result["output"]
                execution_time = time.time() - start_time
                
                # Convertir las llamadas a herramientas a un formato más detallado
                tool_calls = []
                for tool_call in result.get("tool_calls", []):
                    tool_calls.append({
                        "tool": tool_call.get("tool", ""),
                        "input": tool_call.get("tool_input", {}),
                        "output": tool_call.get("output", "")
                    })
                
                # Estimar tokens utilizados basado en la longitud del contenido
                # Esto es una aproximación, el conteo real dependerá del tokenizador
                input_tokens = len(chat_request.message) // 4
                output_tokens = len(response_text) // 4
                tool_tokens = sum(len(str(call)) // 4 for call in tool_calls)
                total_tokens = input_tokens + output_tokens + tool_tokens
                
                # Preparar metadatos
                metadata = {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "execution_time": execution_time,
                    "total_tokens": total_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tool_tokens": tool_tokens,
                    "tool_calls": tool_calls,
                    "tools_used": len(tool_calls)
                }
            
            # Tracking de tokens
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("total_tokens", 0),
                model=model_name,
                agent_id=agent.agent_id,
                conversation_id=conversation_id,
                token_type=TOKEN_TYPE_LLM,
                operation=OPERATION_AGENT_CHAT,
                metadata={
                    "agent_type": agent.type,
                    "collection_ids": collection_ids,
                    "tools_used": metadata.get("tools_used", 0)
                }
            )
            
            # Crear mensaje de respuesta
            assistant_message = ConversationMessage(
                message_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                agent_id=agent.agent_id,
                tenant_id=tenant_id,
                role=MessageRole.ASSISTANT,
                content=response_text,
                timestamp=datetime.utcnow(),
                metadata=metadata
            )
            
            # Almacenar en la base de datos si está configurado
            if self.settings.store_conversations:
                await self._store_message(assistant_message)
            
            # Extraer fuentes si están disponibles
            sources = []
            if "tool_calls" in metadata:
                for call in metadata["tool_calls"]:
                    if call["tool"].startswith("rag_query"):
                        # Buscar fuentes en la salida de rag_query
                        output = call["output"]
                        if isinstance(output, str) and "Fuentes:" in output:
                            sources_section = output.split("Fuentes:")[1].strip()
                            # Procesar fuentes (formato simplificado)
                            for line in sources_section.split("\n"):
                                if line.strip() and "." in line:
                                    sources.append({"document_name": line.strip()})
            
            # Retornar ChatResponse
            return ChatResponse(
                message=response_text,
                conversation_id=conversation_id,
                agent_id=agent.agent_id,
                metadata=metadata,
                sources=sources,
                tools_used=metadata.get("tool_calls")
            )
            
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}", exc_info=True)
            raise ServiceError(f"Error processing chat: {str(e)}")
    
    @with_context(tenant=True, agent=True)
    @handle_errors(error_type="service", log_traceback=True)
    async def process_internal_query(
        self,
        agent: Agent,
        operation: str,
        parameters: Dict[str, Any],
        tenant_id: str,
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        Procesa una consulta interna desde otro servicio.
        
        Args:
            agent: Agente para procesar la consulta
            operation: Operación a realizar
            parameters: Parámetros de operación
            tenant_id: ID del tenant
            ctx: Contexto de la operación
            
        Returns:
            Dict[str, Any]: Resultado de la operación
        """
        # Manejar diferentes operaciones
        if operation == "query":
            # Crear un mensaje de consulta
            query = parameters.get("query", "")
            if not query:
                raise ServiceError("Query parameter is required")
                
            # Procesar como una solicitud de chat
            chat_request = ChatRequest(
                message=query,
                agent_id=agent.agent_id,
                collection_ids=parameters.get("collection_ids", agent.collection_ids),
                metadata={"internal": True, "operation": "query"}
            )
            
            # Procesar el chat
            response = await self.process_chat(
                agent=agent,
                chat_request=chat_request,
                tenant_id=tenant_id,
                ctx=ctx
            )
            
            return {
                "response": response.message,
                "sources": response.sources,
                "metadata": response.metadata
            }
        
        elif operation == "execute_tool":
            # Ejecución directa de herramienta
            tool_name = parameters.get("tool", "")
            tool_params = parameters.get("parameters", {})
            
            if not tool_name:
                raise ServiceError("Tool parameter is required")
                
            # Ejecutar herramienta
            result = await self.tool_registry.execute_tool(
                tool_id=tool_name,
                parameters=tool_params,
                tenant_id=tenant_id,
                agent_id=agent.agent_id,
                ctx=ctx
            )
            
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "execution_time": result.execution_time,
                "metadata": result.metadata
            }
        
        else:
            raise ServiceError(f"Unknown operation: {operation}")
    
    async def _store_message(self, message: ConversationMessage) -> bool:
        """
        Almacena un mensaje en la base de datos.
        
        Args:
            message: Mensaje para almacenar
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            supabase = get_supabase_client()
            
            # Convertir mensaje a dict
            message_dict = message.dict()
            
            # Insertar mensaje
            result = await supabase.table(TABLE_CONVERSATION_MESSAGES).insert(message_dict).execute()
            
            if not result.data:
                logger.warning(f"Failed to store message: {message.message_id}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error storing message: {str(e)}")
            return False
    
    async def _get_conversation_history(
        self, 
        conversation_id: str, 
        limit: int = 10
    ) -> List[ConversationMessage]:
        """
        Obtiene el historial de conversación de la base de datos.
        
        Args:
            conversation_id: ID de la conversación
            limit: Máximo número de mensajes a recuperar
            
        Returns:
            List[ConversationMessage]: Mensajes de la conversación
        """
        try:
            supabase = get_supabase_client()
            
            # Consultar mensajes
            result = await supabase.table(TABLE_CONVERSATION_MESSAGES) \
                .select("*") \
                .eq("conversation_id", conversation_id) \
                .order("timestamp", desc=False) \
                .limit(limit) \
                .execute()
                
            if not result.data:
                return []
                
            # Convertir a objetos ConversationMessage
            messages = [ConversationMessage(**msg) for msg in result.data]
            
            return messages
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {str(e)}")
            return []
