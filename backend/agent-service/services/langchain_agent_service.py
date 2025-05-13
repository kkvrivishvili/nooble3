"""
Implementación del servicio de agentes utilizando LangChain.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor

from common.context import Context, with_context
from common.db import get_supabase_client
from common.errors import handle_errors, ServiceError
from common.cache import CacheManager, get_with_cache_aside
from common.tracking import track_token_usage

from config import get_settings, TABLE_AGENTS, TABLE_CONVERSATIONS, TABLE_CONVERSATION_MESSAGES
from config import AGENT_STATE_CREATED, AGENT_STATE_ACTIVE, AGENT_STATE_PAUSED, AGENT_STATE_DELETED
from config import OPERATION_AGENT_CHAT, OPERATION_AGENT_RAG, TOKEN_TYPE_LLM

from models import (
    Agent, AgentCreate, AgentUpdate, AgentState, AgentType,
    ChatRequest, ChatResponse, ConversationMessage, MessageRole
)

from services.service_registry import ServiceRegistry
from tools.registry import ToolRegistry
from tools.utils import get_langchain_chat_model, convert_to_langchain_messages, create_langchain_agent, run_agent_with_tools

logger = logging.getLogger(__name__)


class LangChainAgentService:
    """
    Servicio para gestionar agentes utilizando LangChain.
    """
    
    def __init__(self):
        """Inicializa el servicio de agentes."""
        self.settings = get_settings()
        self.service_registry = ServiceRegistry()
        self.tool_registry = ToolRegistry()
        
    async def initialize(self):
        """Initialize the service components."""
        await self.tool_registry.initialize()
    
    @handle_errors(error_type="service", log_traceback=True)
    async def create_agent(self, agent_data: AgentCreate) -> Agent:
        """
        Crea un nuevo agente.
        
        Args:
            agent_data: Datos del agente
            
        Returns:
            Agent: Agente creado
        """
        # Create agent object
        agent = Agent(
            agent_id=str(uuid.uuid4()),
            name=agent_data.name,
            description=agent_data.description,
            type=agent_data.type,
            config=agent_data.config,
            tenant_id=agent_data.tenant_id,
            collection_ids=agent_data.collection_ids,
            is_public=agent_data.is_public,
            state=AgentState.CREATED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata=agent_data.metadata or {}
        )
        
        # Prepare available tools based on agent type
        available_tools = []
        
        # Add default tools available to all agents
        available_tools.extend(["get_date_time", "calculator", "format_json"])
        
        # Add type-specific tools
        if agent.type == AgentType.RAG:
            available_tools.extend(["rag_query", "rag_search"])
        
        # Add tools to agent metadata
        if "available_tools" not in agent.metadata:
            agent.metadata["available_tools"] = available_tools
        
        # Convert to dict for database
        agent_dict = agent.dict()
        
        # Insert into database
        try:
            supabase = get_supabase_client()
            result = await supabase.table(TABLE_AGENTS).insert(agent_dict).execute()
            
            if not result.data:
                raise ServiceError("Failed to create agent in database")
                
            # Store in cache
            await CacheManager.set(
                data_type="agent",
                resource_id=agent.agent_id,
                value=agent,
                tenant_id=agent.tenant_id
            )
            
            return agent
            
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            raise ServiceError(f"Failed to create agent: {str(e)}")
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_agent_by_id(self, agent_id: str, tenant_id: str) -> Optional[Agent]:
        """
        Obtiene un agente por su ID.
        
        Args:
            agent_id: ID del agente
            tenant_id: ID del tenant
            
        Returns:
            Optional[Agent]: Agente encontrado o None si no existe
        """
        # Usar el patrón Cache-Aside para obtener el agente
        async def _fetch_from_db():
            supabase = get_supabase_client()
            result = await supabase.table(TABLE_AGENTS) \
                .select("*") \
                .eq("agent_id", agent_id) \
                .eq("tenant_id", tenant_id) \
                .neq("state", AGENT_STATE_DELETED) \
                .execute()
                
            if not result.data:
                return None
                
            return Agent(**result.data[0])
        
        # Usar get_with_cache_aside para implementar el patrón
        agent = await get_with_cache_aside(
            cache_key=agent_id,
            data_type="agent",
            tenant_id=tenant_id,
            fetch_function=_fetch_from_db
        )
        
        return agent
    
    @handle_errors(error_type="service", log_traceback=True)
    async def list_agents(
        self, 
        tenant_id: str, 
        limit: int = 10, 
        offset: int = 0, 
        is_public: Optional[bool] = None
    ) -> List[Agent]:
        """
        Lista los agentes disponibles para un tenant.
        
        Args:
            tenant_id: ID del tenant
            limit: Límite de agentes a retornar
            offset: Offset para paginación
            is_public: Filtrar por agentes públicos/privados
            
        Returns:
            List[Agent]: Lista de agentes
        """
        try:
            supabase = get_supabase_client()
            query = supabase.table(TABLE_AGENTS).select("*") \
                .eq("tenant_id", tenant_id) \
                .neq("state", AGENT_STATE_DELETED)
                
            if is_public is not None:
                query = query.eq("is_public", is_public)
                
            query = query.order("created_at", desc=True) \
                .limit(limit) \
                .offset(offset)
                
            result = await query.execute()
            
            if not result.data:
                return []
            
            return [Agent(**agent_data) for agent_data in result.data]
            
        except Exception as e:
            logger.error(f"Error listing agents: {str(e)}")
            return []
    
    @handle_errors(error_type="service", log_traceback=True)
    async def update_agent(self, agent_id: str, update_data: AgentUpdate, tenant_id: str) -> Agent:
        """
        Actualiza un agente existente.
        
        Args:
            agent_id: ID del agente
            update_data: Datos de actualización
            tenant_id: ID del tenant
            
        Returns:
            Agent: Agente actualizado
        """
        # Obtener agente existente
        existing_agent = await self.get_agent_by_id(agent_id, tenant_id)
        
        if not existing_agent:
            raise ServiceError(f"Agent with ID {agent_id} not found")
        
        # Actualizar objeto del agente
        update_dict = update_data.dict(exclude_unset=True)
        
        # Aplicar actualizaciones
        for key, value in update_dict.items():
            setattr(existing_agent, key, value)
        
        # Actualizar timestamp
        existing_agent.updated_at = datetime.utcnow()
        
        # Actualizar en la base de datos
        try:
            supabase = get_supabase_client()
            agent_dict = existing_agent.dict()
            result = await supabase.table(TABLE_AGENTS).update(agent_dict) \
                .eq("agent_id", agent_id) \
                .eq("tenant_id", tenant_id) \
                .execute()
            
            if not result.data:
                raise ServiceError(f"Failed to update agent with ID {agent_id}")
            
            # Invalidar caché
            await CacheManager.delete(
                data_type="agent",
                resource_id=agent_id,
                tenant_id=tenant_id
            )
            
            return existing_agent
            
        except Exception as e:
            logger.error(f"Error updating agent: {str(e)}")
            raise ServiceError(f"Failed to update agent: {str(e)}")
    
    @handle_errors(error_type="service", log_traceback=True)
    async def delete_agent(self, agent_id: str, tenant_id: str) -> bool:
        """
        Elimina un agente (marca como eliminado).
        
        Args:
            agent_id: ID del agente
            tenant_id: ID del tenant
            
        Returns:
            bool: True si se eliminó correctamente
        """
        # Actualizar estado del agente a eliminado
        try:
            supabase = get_supabase_client()
            result = await supabase.table(TABLE_AGENTS).update({"state": AGENT_STATE_DELETED}) \
                .eq("agent_id", agent_id) \
                .eq("tenant_id", tenant_id) \
                .execute()
            
            # Invalidar caché
            await CacheManager.delete(
                data_type="agent",
                resource_id=agent_id,
                tenant_id=tenant_id
            )
            
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error deleting agent: {str(e)}")
            return False
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_agent_tools(self, agent_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene las herramientas disponibles para un agente.
        
        Args:
            agent_id: ID del agente
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
