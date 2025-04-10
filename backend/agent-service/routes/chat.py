import logging
import time
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Path
from fastapi.responses import StreamingResponse

from common.models import TenantInfo, ChatRequest, ChatResponse, ChatMessage
from common.errors import ServiceError, handle_errors
from common.context import with_context, ContextManager, set_current_conversation_id
from common.auth import verify_tenant
from common.db.rpc import create_conversation, add_chat_history
from common.tracking import track_query
from common.cache.contextual import invalidate_cache_hierarchy
from common.cache.counters import invalidate_conversation_cache

from services.agent_executor import execute_agent, stream_agent_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/agents/{agent_id}/chat", response_model=ChatResponse)
@handle_errors(error_type="simple", log_traceback=False)
@with_context(tenant=True, agent=True, conversation=True)
async def chat_with_agent(
    agent_id: str,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> ChatResponse:
    """Procesa una solicitud de chat con un agente inteligente específico."""
    start_time = time.time()
    
    tenant_id = tenant_info.tenant_id
    conversation_id = request.conversation_id
    
    # Crear ContextManager para gestionar el ciclo de vida de la conversación
    context_manager = ContextManager(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_id=tenant_info.user_id,
        session_id=request.client_reference_id
    )
    
    # Si no hay ID de conversación, crear una nueva conversación
    if not conversation_id:
        try:
            # Obtener configuración del agente directamente desde context_manager
            agent_config = await context_manager.get_agent_config()
            agent_name = agent_config.get("name", "Agente")
            
            # Crear conversación en Supabase usando RPC
            conversation_data = await create_conversation(
                tenant_id=tenant_id,
                agent_id=agent_id,
                title=f"Conversación con {agent_name}",
                context=request.context,
                client_reference_id=request.client_reference_id
            )
            
            if not conversation_data:
                raise ServiceError(
                    message="Error creating conversation",
                    status_code=500,
                    error_code="conversation_creation_failed"
                )
            
            # Actualizar conversation_id en el contexto
            conversation_id = conversation_data.get("conversation_id") if isinstance(conversation_data, dict) else conversation_data
            context_manager.conversation_id = conversation_id
            
            # Actualizar el contexto global también
            set_current_conversation_id(conversation_id)
            
            logger.info(f"Creada nueva conversación {conversation_id} para tenant {tenant_id}, agent {agent_id}")
        except Exception as e:
            if isinstance(e, ServiceError):
                raise e
            logger.error(f"Error creating conversation: {str(e)}")
            raise ServiceError(
                message=f"Error creating conversation: {str(e)}",
                status_code=500,
                error_code="conversation_creation_failed"
            )
    
    # Procesar la solicitud según el modo (streaming o normal)
    if request.stream:
        return StreamingResponse(
            stream_agent_response(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                query=request.message,
                user_id=tenant_info.user_id,
                session_id=request.client_reference_id
            ),
            media_type="text/event-stream"
        )
    
    # Ejecutar el agente
    agent_response = await execute_agent(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        query=request.message,
        streaming=False,
        user_id=tenant_info.user_id,
        context=request.context
    )
    
    # Calcular tiempo de procesamiento
    processing_time = time.time() - start_time
    
    # Guardar el mensaje para persistencia
    message_result = await add_chat_history(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_message=request.message,
        assistant_message=agent_response["answer"],
        thinking=agent_response.get("thinking", ""),
        tools_used=agent_response.get("tools_used", []),
        processing_time=processing_time
    )
    
    if not message_result:
        logger.warning(f"Error guardando mensajes para conversación {conversation_id}")
    
    # Verificar si la conversación está terminando
    if request.metadata and request.metadata.get("end_conversation"):
        background_tasks.add_task(
            invalidate_conversation_cache,
            tenant_id=tenant_id,
            agent_id=agent_id, 
            conversation_id=conversation_id
        )
    
    # Tracking de uso en segundo plano
    background_tasks.add_task(
        track_query,
        tenant_id=tenant_id,
        operation_type="chat",
        model=agent_response.get("model", "gpt-3.5-turbo"),
        tokens_in=agent_response.get("tokens", 0) // 3,
        tokens_out=agent_response.get("tokens", 0) * 2 // 3,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Construir respuesta
    return ChatResponse(
        success=True,
        status_message="Consulta procesada exitosamente",
        conversation_id=conversation_id,
        message=ChatMessage(
            role="assistant",
            content=agent_response["answer"],
            metadata={"processing_time": processing_time}
        ),
        thinking=agent_response.get("thinking"),
        tools_used=agent_response.get("tools_used"),
        processing_time=processing_time,
        sources=agent_response.get("sources"),
        context=request.context
    )

@router.post("/conversations/{conversation_id}/end", response_model=ChatResponse)
@handle_errors(error_type="simple", log_traceback=False)
@with_context(tenant=True, conversation=True)
async def end_conversation(
    conversation_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> ChatResponse:
    """
    Finaliza explícitamente una conversación y persiste sus datos.
    
    Este endpoint:
    1. Marca la conversación como terminada en Supabase
    2. Asegura que todos los mensajes están guardados
    3. Invalida la caché relacionada con esta conversación
    """
    tenant_id = tenant_info.tenant_id
    
    # Obtener información de la conversación
    from common.db.supabase import get_supabase_client
    from common.db.tables import get_table_name
    
    supabase = get_supabase_client()
    result = await supabase.table(get_table_name("conversations")) \
        .select("*") \
        .eq("id", conversation_id) \
        .eq("tenant_id", tenant_id) \
        .execute()
    
    if not result.data:
        raise ServiceError(
            message=f"Conversation {conversation_id} not found",
            status_code=404,
            error_code="conversation_not_found"
        )
    
    conversation = result.data[0]
    agent_id = conversation.get("agent_id")
    
    # Marcar conversación como terminada
    await supabase.table(get_table_name("conversations")) \
        .update({"is_active": False, "ended_at": "NOW()"}) \
        .eq("id", conversation_id) \
        .execute()
    
    # Invalidar caché para esta conversación
    await invalidate_cache_hierarchy(
        tenant_id=tenant_id,
        agent_id=agent_id, 
        conversation_id=conversation_id
    )
    
    # También usar la función específica para invalidar caché de conversación
    await invalidate_conversation_cache(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    return ChatResponse(
        success=True,
        status_message="Conversación finalizada exitosamente",
        conversation_id=conversation_id,
        message=ChatMessage(
            role="system",
            content="La conversación ha sido finalizada. El historial se ha guardado permanentemente.",
            metadata={"conversation_ended": True}
        )
    )