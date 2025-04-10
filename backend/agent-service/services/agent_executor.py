import logging
import time
import uuid
from typing import Dict, List, Any, Optional, AsyncGenerator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool
from langchain_core.callbacks import CallbackManager
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent

from common.config import get_settings
from common.context import ContextManager, with_context
from common.errors import (
    ServiceError, handle_errors, ErrorCode,
    AgentNotFoundError, AgentInactiveError, AgentExecutionError, 
    AgentSetupError, AgentToolError
)
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.llm.token_counters import count_tokens
from common.tracking import track_token_usage
from common.llm.streaming import stream_llm_response
from common.cache.manager import CacheManager

from services.callbacks import AgentCallbackHandler, StreamingCallbackHandler
from services.tools import create_agent_tools

logger = logging.getLogger(__name__)
settings = get_settings()

@with_context(tenant=True, agent=True)
@handle_errors(error_type="service", log_traceback=True, error_map={
    AgentNotFoundError: ("AGENT_CONFIG_NOT_FOUND", 404),
    AgentInactiveError: ("AGENT_INACTIVE", 400)
})
async def get_agent_config(agent_id: str, tenant_id: str) -> Dict[str, Any]:
    """Obtiene la configuración de un agente desde Supabase."""
    
    # Verificar caché primero
    cached_config = await CacheManager.get_agent_config(
        agent_id=agent_id,
        tenant_id=tenant_id
    )
    
    if cached_config:
        logger.debug(f"Configuración de agente {agent_id} obtenida de caché")
        return cached_config
    
    # Si no está en caché, obtener de Supabase
    supabase = get_supabase_client()
    result = await supabase.table(get_table_name("agent_configs")) \
        .select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("agent_id", agent_id) \
        .single() \
        .execute()
    
    if not result.data:
        logger.warning(f"Agente {agent_id} no encontrado para tenant {tenant_id}")
        raise AgentNotFoundError(
            message=f"Agent with ID {agent_id} not found",
            details={"agent_id": agent_id, "tenant_id": tenant_id}
        )
    
    # Verificar propiedad del agente explícitamente 
    # CORREGIDO: Convertir ambos ids a string para evitar problemas con tipos diferentes
    if str(result.data["tenant_id"]) != str(tenant_id):
        logger.warning(f"Intento de acceso a agente de otro tenant: {agent_id}")
        raise ServiceError(
            message="Access denied: agent belongs to another tenant",
            status_code=403,
            error_code=ErrorCode.PERMISSION_DENIED
        )
    
    # Guardar en caché para futuros usos (TTL de 5 minutos)
    await CacheManager.set_agent_config(
        agent_id=agent_id,
        config=result.data,
        tenant_id=tenant_id,
        ttl=300
    )
    
    return result.data

@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="service", log_traceback=True, error_map={
    AgentExecutionError: ("AGENT_EXECUTION_ERROR", 500),
    AgentSetupError: ("AGENT_SETUP_ERROR", 500),
    AgentToolError: ("AGENT_TOOL_ERROR", 500)
})
async def execute_agent(
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    query: str,
    streaming: bool = False,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Ejecuta un agente con una consulta y devuelve la respuesta."""
    
    logger.info(f"Ejecutando agente {agent_id} con query: {query[:50]}...")
    start_time = time.time()
    
    # Crear contexto de memoria con ContextManager
    context_manager = ContextManager(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id
    )
    
    # Registrar mensaje del usuario
    await context_manager.add_user_message(query, metadata=context)
    
    # Verificar caché para esta consulta específica
    cached_response = await CacheManager.get_agent_response(
        agent_id=agent_id,
        query=query,  # La función se encarga de generar el hash
        tenant_id=tenant_id,
        conversation_id=conversation_id
    )
    
    if cached_response and not streaming:
        logger.info(f"Respuesta obtenida de caché para conversación {conversation_id}")
        
        # Registrar respuesta cacheada
        await context_manager.add_assistant_message(
            cached_response["answer"], 
            metadata={
                "from_cache": True,
                "tools_used": cached_response.get("tools_used", []),
                "processing_time": cached_response.get("processing_time", 0)
            }
        )
        
        return cached_response
    
    # Obtener configuración del agente
    agent_config = await get_agent_config(agent_id, tenant_id)
    
    # Verificar que el agente esté activo
    if not agent_config.get("is_active", False):
        raise AgentInactiveError(
            message="This agent is not active",
            details={"agent_id": agent_id, "tenant_id": tenant_id}
        )
    
    # Seleccionar callback handler según modo
    if streaming:
        callback_handler = StreamingCallbackHandler()
    else:
        callback_handler = AgentCallbackHandler()
    
    try:
        # Obtener herramientas del agente
        tools = await create_agent_tools(agent_config, tenant_id, agent_id)
        
        # Configurar LLM con los ajustes del agente
        model_name = agent_config.get("llm_model", settings.default_llm_model)
        temperature = agent_config.get("temperature", 0.0) or 0.0
        
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=settings.openai_api_key,
            streaming=streaming
        )
        
        # Obtener historial de conversación si está habilitado
        conversation_history = []
        if agent_config.get("memory_enabled", True):
            history = await context_manager.get_conversation_history(
                format_for_llm=False,
                max_messages=agent_config.get("memory_window", 10)
            )
            
            # Convertir historial al formato de mensajes de LangChain
            for msg in history:
                if msg.get("role") == "user":
                    conversation_history.append(HumanMessage(content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    conversation_history.append(AIMessage(content=msg.get("content", "")))
                elif msg.get("role") == "system":
                    conversation_history.append(SystemMessage(content=msg.get("content", "")))
        
        # Configurar el prompt con el historial
        system_prompt = agent_config.get("system_prompt", "Eres un asistente útil que responde preguntas y usa herramientas cuando es necesario.")
        
        # Si hay historial, usarlo en el prompt
        if conversation_history:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                *conversation_history,
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
        
        # Crear agente
        agent = create_tool_calling_agent(llm, tools, prompt)
        
        # Crear ejecutor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            callbacks=[callback_handler],
            verbose=agent_config.get("verbose", False),
            max_iterations=agent_config.get("max_iterations", 5),
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )
        
        # Ejecutar agente
        result = await agent_executor.ainvoke(
            {"input": query},
            config={"callbacks": [callback_handler]}
        )
        
        # Extraer respuesta
        answer = result.get("output", "")
        
        # Si la respuesta está vacía, proporcionar una predeterminada
        if not answer or answer.strip() == "":
            answer = "Lo siento, no pude generar una respuesta. Por favor, intenta reformular tu pregunta."
            
        # Calcular tokens aproximados
        input_tokens = count_tokens(query, model_name=model_name)
        output_tokens = count_tokens(answer, model_name=model_name)
        total_tokens = input_tokens + output_tokens
        
        # Tracking de tokens async
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type="llm"
        )
        
        # Extraer tools usadas
        tools_used = callback_handler.get_tools_used() if hasattr(callback_handler, "get_tools_used") else []
        thinking = callback_handler.get_thinking_steps() if hasattr(callback_handler, "get_thinking_steps") else ""
        
        # Registrar respuesta del asistente
        message_id = await context_manager.add_assistant_message(
            answer, 
            metadata={
                "tools_used": tools_used,
                "thinking": thinking,
                "tokens": total_tokens
            }
        )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Construir respuesta
        agent_response = {
            "answer": answer,
            "thinking": thinking,
            "tools_used": tools_used,
            "tokens": total_tokens,
            "processing_time": processing_time,
            "message_id": message_id
        }
        
        # Guardar en caché para futuras consultas idénticas
        # (solo si no es streaming y la respuesta no es un error)
        if not streaming and "error" not in agent_response:
            await CacheManager.set_agent_response(
                agent_id=agent_id,
                query=query,  # La función se encarga de generar el hash
                response=agent_response,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                ttl=1800
            )
    
    except ServiceError as service_error:
        # Manejo específico para errores de servicio estandarizados
        logger.error(f"ServiceError en ejecución de agente: {service_error.message}")
        processing_time = time.time() - start_time
        agent_response = {
            "error": service_error.message,
            "error_code": service_error.error_code,
            "processing_time": processing_time
        }
        return agent_response
    except Exception as e:
        # Convertir excepciones generales a AgentExecutionError
        logger.error(f"Error en ejecución de agente: {str(e)}")
        processing_time = time.time() - start_time
        
        # Usar la clase específica para errores de ejecución de agente
        error = AgentExecutionError(
            message=f"Error al ejecutar el agente: {str(e)}",
            details={"agent_id": agent_id, "tenant_id": tenant_id}
        )
        
        agent_response = {
            "error": error.message,
            "error_code": error.error_code,
            "processing_time": processing_time
        }
        return agent_response
    
    logger.info(f"Ejecución de agente completada en {processing_time:.2f}s")
    return agent_response

async def stream_agent_response(
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """Genera una respuesta en streaming para un agente."""
    # Crear ContextManager
    context_manager = ContextManager(
        tenant_id=tenant_id,
        agent_id=agent_id, 
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id
    )
    
    try:
        # Registrar mensaje del usuario
        await context_manager.add_user_message(query)
        
        # Obtener configuración del agente
        agent_config = await context_manager.get_agent_config()
        
        # Crear un StreamingCallbackHandler
        streaming_handler = StreamingCallbackHandler()
        
        # Variables para acumular la respuesta completa
        full_response = ""
        message_id = str(uuid.uuid4())
        
        # Streaming de la respuesta
        async for token in stream_llm_response(
            prompt=query,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            model_name=agent_config.get("llm_model", settings.default_llm_model),
            system_prompt=agent_config.get("system_prompt"),
            use_cache=True
        ):
            try:
                # Acumular respuesta completa
                full_response += token
                # Devolver el token
                yield token
            except Exception as stream_error:
                logger.error(f"Error en stream de tokens: {str(stream_error)}")
                # Continuar con el siguiente token
        
        # Registrar la respuesta completa en la memoria del agente
        await context_manager.add_assistant_message(
            full_response,
            metadata={"streaming": True, "message_id": message_id}
        )
        
        # Contabilizar tokens (en background)
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=len(full_response.split()) * 2,  # Estimación básica
            model=agent_config.get("llm_model", settings.default_llm_model),
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    except ServiceError as service_error:
        # Errores de servicio estandarizados
        error_message = f"Error: {service_error.message}"
        logger.error(f"ServiceError en streaming: {service_error.message}")
        
        # Registrar error en la memoria del agente
        try:
            await context_manager.add_assistant_message(
                error_message,
                metadata={"error": service_error.message, "streaming": True}
            )
        except Exception:
            pass
        
        yield error_message
    except Exception as e:
        # Cualquier otra excepción
        error_message = f"Error: {str(e)}"
        logger.error(f"Error en streaming de agente: {str(e)}")
        
        # Registrar error en la memoria del agente
        try:
            await context_manager.add_assistant_message(
                error_message,
                metadata={"error": str(e), "streaming": True}
            )
        except Exception:
            pass
        
        yield error_message