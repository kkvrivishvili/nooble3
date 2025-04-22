"""
Servicio para ejecución de agentes.

Este módulo proporciona funciones para obtener, configurar y ejecutar agentes de conversación.
"""

import logging
import time
import json
import traceback
import uuid
from typing import Dict, Any, List, Optional, Tuple, AsyncIterator
from pydantic import BaseModel

import openai
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import MessagesPlaceholder
from langchain.prompts.chat import ChatPromptTemplate
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.chat_models import ChatOpenAI

# Importaciones de contexto centralizadas
from common.context import Context, with_context
from common.context.memory import ContextManager
from common.errors import handle_errors, ServiceError, ErrorCode, AgentExecutionError, AgentInactiveError
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.config.settings import get_settings
from common.tracking import track_operation, track_token_usage, track_embedding_usage
from common.llm.utils import count_tokens
from common.utils.stream import stream_llm_response
from common.llm.callbacks import TokenCountingHandler
from common.cache import (
    CacheManager,
    get_with_cache_aside,
    invalidate_coordinated,
    generate_resource_id_hash,
    serialize_for_cache,
    deserialize_from_cache,
    SOURCE_CACHE,
    SOURCE_SUPABASE,
    METRIC_CACHE_HIT,
    METRIC_CACHE_INVALIDATION,
    track_cache_metrics
)
from services.chat_history import add_chat_history
from services.tools import create_agent_tools

logger = logging.getLogger(__name__)
settings = get_settings()

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="get_agent_config", operation_type="agent")
async def get_agent_config(agent_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Obtiene la configuración de un agente implementando el patrón Cache-Aside.
    
    Utiliza la implementación centralizada para verificar primero en caché,
    luego en Supabase, asegurando la consistencia entre servicios.
    
    Args:
        agent_id: ID del agente a consultar
        tenant_id: ID del tenant al que pertenece el agente
        
    Returns:
        Configuración del agente solicitado
        
    Raises:
        ServiceError: Si no se encuentra el agente o hay un error de acceso
    """
    # Validar parámetros
    if not agent_id or not tenant_id:
        raise ServiceError(
            message="Se requieren agent_id y tenant_id para obtener la configuración",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    # Generar identificador consistente para este recurso
    resource_id = f"agent:{agent_id}"
    
    # Función para buscar la configuración en Supabase si no está en caché
    async def fetch_agent_config_from_db(resource_id, tenant_id, ctx=None):
        """Busca la configuración del agente en Supabase"""
        try:
            # Obtener cliente y tabla
            supabase = get_supabase_client()
            table_name = get_table_name("agents")
            
            # Buscar agente
            query_result = (supabase.table(table_name)
                         .select("*")
                         .eq("id", agent_id)
                         .eq("tenant_id", tenant_id)
                         .limit(1)
                         .execute())
            
            if not query_result.data or len(query_result.data) == 0:
                logger.warning(f"Agente no encontrado: {agent_id} para tenant {tenant_id}")
                return None
            
            agent_config = query_result.data[0]
            
            # Verificar estado del agente
            if agent_config.get("status") != "active":
                logger.warning(f"Agente {agent_id} no está activo. Estado: {agent_config.get('status')}")
                return None
            
            return agent_config
        except Exception as e:
            logger.error(f"Error buscando agente en Supabase: {str(e)}")
            return None
    
    # No necesitamos generar configuraciones, sólo las recuperamos
    async def generate_agent_config(resource_id, tenant_id, ctx=None):
        return None
    
    # Usar la implementación centralizada del patrón Cache-Aside
    agent_config, metrics = await get_with_cache_aside(
        data_type="agent_config",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_agent_config_from_db,
        generate_func=generate_agent_config,
        # TTL se determina automáticamente por tipo de dato
    )
    
    # Verificar resultado y manejar caso de no encontrado
    if not agent_config:
        raise ServiceError(
            message=f"Agente no encontrado o no está activo: {agent_id}",
            error_code=ErrorCode.NOT_FOUND,
            details={
                "agent_id": agent_id,
                "tenant_id": tenant_id
            }
        )
    
    # Agregar métricas de rendimiento
    agent_config["_metrics"] = {
        "source": metrics.get("source", "unknown"),
        "latency_ms": metrics.get("latency_ms", 0)
    }
    
    return agent_config

@handle_errors(error_type="service")
async def invalidate_agent_config_cache(tenant_id: str, agent_id: str) -> bool:
    """
    Invalida la caché para un agente específico utilizando el patrón de invalidación coordinada.
    
    Esta función debe llamarse cuando se actualiza la configuración de un agente
    para asegurar que las solicitudes posteriores obtengan la configuración más reciente.
    También invalida recursos relacionados que podrían depender de esta configuración.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        
    Returns:
        bool: True si se invalidó correctamente, False en caso contrario
    """
    resource_id = f"agent:{agent_id}"
    
    # Definir las invalidaciones relacionadas
    related_invalidations = [
        {"data_type": "agent_response", "resource_id": "*", "agent_id": agent_id}
    ]
    
    # Usar el patrón de invalidación coordinada para invalidar configuración y recursos relacionados
    invalidation_result = await invalidate_coordinated(
        tenant_id=tenant_id,
        primary_data_type="agent_config",
        primary_resource_id=resource_id,
        related_invalidations=related_invalidations
    )
    
    # Registrar métrica de invalidación
    await track_cache_metrics(
        data_type="agent_config",
        tenant_id=tenant_id,
        agent_id=agent_id,
        metric_type=METRIC_CACHE_INVALIDATION,
        value=sum(invalidation_result.values()),
        metadata={"operation": "invalidate_agent_config"}
    )
    
    success = sum(invalidation_result.values()) > 0
    
    if success:
        logger.info(f"Caché invalidada para agente: {agent_id} (tenant: {tenant_id}) - {sum(invalidation_result.values())} entradas removidas")
    else:
        logger.warning(f"No se pudo invalidar caché para agente: {agent_id} (tenant: {tenant_id})")
    
    return success

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="create_agent", operation_type="agent")
async def create_agent_config(agent_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Crea una nueva configuración de agente en la base de datos.
    
    Args:
        agent_data: Datos del agente a crear
        tenant_id: ID del tenant al que pertenecerá el agente
        
    Returns:
        Dict[str, Any]: Configuración del agente creado
        
    Raises:
        ServiceError: Si hay un error al crear el agente
    """
    if not agent_data or not tenant_id:
        raise ServiceError(
            message="Se requieren datos del agente y tenant_id para crear la configuración",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    try:
        # Obtener cliente y tabla
        supabase = get_supabase_client()
        table_name = get_table_name("agents")
        
        # Crear agente
        result = await supabase.table(table_name).insert(agent_data).execute()
        
        if result.error:
            logger.error(f"Error creando agente: {result.error}")
            raise ServiceError(
                message=f"Error creando agente: {result.error}",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # Obtener configuración creada
        created_agent = result.data[0] if result.data else None
        
        if not created_agent:
            raise ServiceError(
                message="Agente creado pero no se pudo recuperar la configuración",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # No es necesario invalidar caché porque es un recurso nuevo
        return created_agent
        
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        
        logger.error(f"Error creando agente: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado creando agente: {str(e)}",
            error_code=ErrorCode.AGENT_CREATION_ERROR
        )

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="update_agent", operation_type="agent")
async def update_agent_config(agent_id: str, agent_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Actualiza la configuración de un agente existente.
    
    Args:
        agent_id: ID del agente a actualizar
        agent_data: Nuevos datos del agente
        tenant_id: ID del tenant al que pertenece el agente
        
    Returns:
        Dict[str, Any]: Configuración actualizada del agente
        
    Raises:
        ServiceError: Si no se encuentra el agente o hay un error al actualizarlo
    """
    if not agent_id or not agent_data or not tenant_id:
        raise ServiceError(
            message="Se requieren agent_id, datos del agente y tenant_id para actualizar la configuración",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    try:
        # Obtener cliente y tabla
        supabase = get_supabase_client()
        table_name = get_table_name("agents")
        
        # Actualizar agente
        result = await supabase.table(table_name) \
            .update(agent_data) \
            .eq("id", agent_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if result.error:
            logger.error(f"Error actualizando agente {agent_id}: {result.error}")
            raise ServiceError(
                message=f"Error actualizando agente: {result.error}",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # Verificar si se actualizó algún registro
        if not result.data or len(result.data) == 0:
            raise ServiceError(
                message=f"Agente no encontrado o sin cambios: {agent_id}",
                error_code=ErrorCode.NOT_FOUND
            )
        
        # Obtener configuración actualizada
        updated_agent = result.data[0]
        
        # Invalidar caché usando la función centralizada
        await invalidate_agent_config_cache(tenant_id, agent_id)
        
        return updated_agent
        
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        
        logger.error(f"Error actualizando agente {agent_id}: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado actualizando agente: {str(e)}",
            error_code=ErrorCode.AGENT_UPDATE_ERROR
        )

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="delete_agent", operation_type="agent")
async def delete_agent_config(agent_id: str, tenant_id: str) -> bool:
    """
    Elimina la configuración de un agente.
    
    Args:
        agent_id: ID del agente a eliminar
        tenant_id: ID del tenant al que pertenece el agente
        
    Returns:
        bool: True si se eliminó correctamente
        
    Raises:
        ServiceError: Si no se encuentra el agente o hay un error al eliminarlo
    """
    if not agent_id or not tenant_id:
        raise ServiceError(
            message="Se requieren agent_id y tenant_id para eliminar la configuración",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    try:
        # Obtener cliente y tabla
        supabase = get_supabase_client()
        table_name = get_table_name("agents")
        
        # Eliminar agente
        result = await supabase.table(table_name) \
            .delete() \
            .eq("id", agent_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if result.error:
            logger.error(f"Error eliminando agente {agent_id}: {result.error}")
            raise ServiceError(
                message=f"Error eliminando agente: {result.error}",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # Verificar si se eliminó algún registro
        if not result.data or len(result.data) == 0:
            raise ServiceError(
                message=f"Agente no encontrado: {agent_id}",
                error_code=ErrorCode.NOT_FOUND
            )
        
        # Invalidar caché usando la función centralizada
        await invalidate_agent_config_cache(tenant_id, agent_id)
        
        return True
        
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        
        logger.error(f"Error eliminando agente {agent_id}: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado eliminando agente: {str(e)}",
            error_code=ErrorCode.AGENT_DELETION_ERROR
        )

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="list_agents", operation_type="agent")
async def list_agent_configs(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lista todas las configuraciones de agentes para un tenant.
    
    Args:
        tenant_id: ID del tenant
        
    Returns:
        List[Dict[str, Any]]: Lista de configuraciones de agentes
        
    Raises:
        ServiceError: Si hay un error al listar los agentes
    """
    if not tenant_id:
        raise ServiceError(
            message="Se requiere tenant_id para listar las configuraciones",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    try:
        # Obtener cliente y tabla
        supabase = get_supabase_client()
        table_name = get_table_name("agents")
        
        # Listar agentes
        result = await supabase.table(table_name) \
            .select("*") \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if result.error:
            logger.error(f"Error listando agentes para tenant {tenant_id}: {result.error}")
            raise ServiceError(
                message=f"Error listing agents: {result.error}",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # Extraer lista de agentes
        agents = result.data if result.data else []
        
        return agents
        
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        
        logger.error(f"Error listando agentes para tenant {tenant_id}: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado listando agentes: {str(e)}",
            error_code=ErrorCode.SERVICE_ERROR
        )

@with_context(tenant=True, agent=True)
@handle_errors(error_type="service", log_traceback=True)
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
    
    # Obtener o crear ContextManager único para este contexto
    context_manager = ContextManager.get_or_create(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id
    )
    
    # Registrar mensaje del usuario
    await context_manager.add_user_message(query, metadata=context)
    
    # Verificar caché para esta consulta específica
    query_hash = generate_resource_id_hash(query)
    resource_id = f"query:{query_hash}"
    
    # Definir función para obtener respuesta desde Supabase (no aplica aquí)
    async def fetch_response_from_db(resource_id, tenant_id, ctx):
        # No almacenamos respuestas en DB, sólo en caché
        return None
        
    # Función para generar la respuesta (se ejecutará si no está en caché)
    async def generate_agent_response(resource_id, tenant_id, ctx):
        # Esta función efectivamente ejecuta el agente
        # La implementación está más abajo y se llamará si no hay caché
        return None  # No ejecutamos aquí, sólo indicamos que no hay en caché
    
    # Usar implementación centralizada de Cache-Aside
    cached_response, metrics = await get_with_cache_aside(
        data_type="agent_response",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_response_from_db,
        generate_func=generate_agent_response,
        agent_id=agent_id,
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
        
        # Registrar métrica de caché hit
        await track_cache_metrics(
            data_type="agent_response",
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            metric_type=METRIC_CACHE_HIT,
            value=1,
            metadata={
                "agent_id": agent_id,
                "conversation_id": conversation_id
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
        callback_handler = AgentCallbackHandler()
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
        
        # Tracking de tokens usando la función estandarizada
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            token_type="llm",
            agent_id=agent_id,
            conversation_id=conversation_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            service="agent-service",
            streaming=streaming
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
        if not streaming and "error" not in agent_response:
            try:
                # Serializar respuesta para caché usando el estándar
                serialized_response = serialize_for_cache(agent_response)
                
                # Registrar métrica de almacenamiento en caché
                await track_cache_metrics(
                    data_type="agent_response",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    metric_type="cache_set",
                    value=1,
                    metadata={
                        "query_length": len(query),
                        "response_length": len(answer) if answer else 0,
                        "tools_used": len(tools_used)
                    }
                )
                
                # Usar el mismo identificador de recurso que usamos para verificar caché
                await CacheManager.set(
                    data_type="agent_response",
                    resource_id=resource_id,  # Usamos el mismo resource_id generado anteriormente
                    value=serialized_response,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id
                    # TTL se determina automáticamente por el tipo de datos "agent_response"
                )
            except Exception as cache_set_err:
                logger.debug(f"Error guardando respuesta en caché: {str(cache_set_err)}")
                # Registrar métrica de error en caché
                await track_cache_metrics(
                    data_type="agent_response",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    metric_type="cache_error",
                    value=1,
                    metadata={"error_type": "set_error", "error": str(cache_set_err)}
                )    
    except ServiceError as service_error:
        # Manejo específico para errores de servicio estandarizados
        context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "execute_agent"}
        logger.error(f"ServiceError en ejecución de agente: {service_error.message}", extra=context, exc_info=True)
        processing_time = time.time() - start_time
        agent_response = {
            "error": service_error.message,
            "error_code": service_error.error_code,
            "processing_time": processing_time
        }
        return agent_response
    except Exception as e:
        # Convertir excepciones generales a AgentExecutionError
        context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "execute_agent"}
        logger.error(f"Error en ejecución de agente: {str(e)}", extra=context, exc_info=True)
        processing_time = time.time() - start_time
        
        # Usar la clase específica para errores de ejecución de agente
        error_context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "execute_agent", "error_type": type(e).__name__}
        error = AgentExecutionError(
            message=f"Error al ejecutar el agente: {str(e)}",
            details=error_context
        )
        
        agent_response = {
            "error": error.message,
            "error_code": error.error_code,
            "processing_time": processing_time
        }
        return agent_response
    
    logger.info(f"Ejecución de agente completada en {processing_time:.2f}s")
    return agent_response

@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="service", log_traceback=True)
async def stream_agent_response(
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context_manager: ContextManager = None
) -> AsyncIterator[str]:
    """Genera una respuesta en streaming para un agente."""
    # Reutilizar instancia existente o crear nueva única
    if context_manager is None:
        context_manager = ContextManager.get_or_create(
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
        agent_config = await get_agent_config(agent_id, tenant_id)
        
        # Crear un TokenCountingHandler para conteo preciso
        token_handler = TokenCountingHandler()
        # Inicializar conteo de tokens de entrada
        if hasattr(token_handler, 'on_llm_start'):
            token_handler.on_llm_start(None, [query, agent_config.get("system_prompt", "")])
        # Modelo para conteo de tokens
        model_name = agent_config.get("llm_model", settings.default_llm_model)
        
        # Variables para acumular la respuesta completa
        full_response = ""
        message_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Streaming de la respuesta usando la implementación centralizada
        async for token in stream_llm_response(
            prompt=query,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            model_name=model_name,
            system_message=agent_config.get("system_prompt"),
            use_cache=True
        ):
            try:
                # Acumular respuesta completa
                full_response += token
                # Contar token en el contador personalizado
                if hasattr(token_handler, 'on_llm_new_token'):
                    token_handler.on_llm_new_token(token)
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
        
        # Persistir en Supabase
        processing_time = time.time() - start_time
        await add_chat_history(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            user_message=query,
            assistant_message=full_response,
            thinking="",  # No hay thinking en streaming
            tools_used=[],
            processing_time=processing_time
        )
        
        # Contabilizar tokens usando el sistema centralizado de tracking
        input_tokens = count_tokens(query, model_name=model_name)
        output_tokens = count_tokens(full_response, model_name=model_name)
        total_tokens = input_tokens + output_tokens
        
        # Usar contador de tokens preciso si está disponible
        if token_handler and hasattr(token_handler, 'get_total_tokens'):
            total_tokens = token_handler.get_total_tokens()
        
        # Usar track_token_usage en lugar de track_usage para seguir estándares
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            token_type="llm",
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    except ServiceError as service_error:
        # Errores de servicio estandarizados
        error_message = f"Error: {service_error.message}"
        context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "stream_agent_response"}
        logger.error(f"ServiceError en streaming: {service_error.message}", extra=context, exc_info=True)
        
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
        context = {"agent_id": agent_id, "tenant_id": tenant_id, "operation": "stream_agent_response"}
        logger.error(f"Error en streaming de agente: {str(e)}", extra=context, exc_info=True)
        
        # Registrar error en la memoria del agente
        try:
            await context_manager.add_assistant_message(
                error_message,
                metadata={"error": str(e), "streaming": True}
            )
        except Exception:
            pass
        
        yield error_message