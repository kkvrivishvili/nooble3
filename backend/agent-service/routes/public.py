import logging
import time
from typing import Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Path
from fastapi.responses import StreamingResponse

from common.models import PublicChatRequest, ChatResponse, ChatMessage
from common.errors import ServiceError, handle_service_error_simple
from common.context import with_context, Context, ContextManager
from common.db.rpc import create_conversation, add_chat_history
from common.tracking import track_query
from common.config import get_settings
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

from services.agent_executor import execute_agent, stream_agent_response
from services.public import verify_public_tenant, register_public_session

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

@router.post("/public/{tenant_slug}/chat/{agent_id}", response_model=ChatResponse, tags=["Chat"])
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True, validate_tenant=False)
async def public_chat_with_agent(
    tenant_slug: str,
    agent_id: str,
    request: PublicChatRequest,
    background_tasks: BackgroundTasks,
    ctx: Context = None
) -> ChatResponse:
    """Procesa una solicitud de chat pública sin requerir autenticación."""
    # Verificar tenant público
    try:
        tenant_info = await verify_public_tenant(tenant_slug)
        
        if not tenant_info.has_quota:
            raise ServiceError(
                message="This tenant has reached its token quota",
                status_code=402,  # Payment Required
                error_code="quota_exceeded"
            )
    except ServiceError:
        raise
    except Exception as e:
        logger.error(f"Error verifying public tenant: {str(e)}")
        raise ServiceError(
            message="Error verifying tenant",
            status_code=500,
            error_code="tenant_verification_error"
        )
    
    # Generar session_id si no se proporcionó
    session_id = request.session_id or str(uuid.uuid4())
    
    # Para endpoints públicos, usar run_public_context
    async def _process_public_chat():
        start_time = time.time()
        
        # Verificar que el agente existe, es público y pertenece al tenant
        supabase = get_supabase_client()
        agent_data = await supabase.table(get_table_name("agent_configs")) \
            .select("*") \
            .eq("agent_id", agent_id) \
            .eq("tenant_id", tenant_info.tenant_id) \
            .eq("is_public", True) \
            .single() \
            .execute()
        
        if not agent_data.data:
            raise ServiceError(
                message="Agent not found or not available for public access",
                status_code=404,
                error_code="agent_not_found"
            )
        
        # Usar el session_id como ID de conversación para sesiones públicas
        conversation_id = session_id
        
        # Registrar sesión pública
        await register_public_session(
            tenant_id=tenant_info.tenant_id,
            session_id=session_id,
            agent_id=agent_id
        )
        
        # Crear un ContextManager para esta sesión
        context_manager = ContextManager.get_or_create(
            tenant_id=tenant_info.tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            session_id=session_id
        )
        
        # Registrar mensaje del usuario
        await context_manager.add_user_message(request.message)
        
        # Ejecutar agente (usar stream o no según request)
        if request.stream:
            return StreamingResponse(
                stream_agent_response(
                    tenant_id=tenant_info.tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    query=request.message,
                    session_id=session_id,
                    context_manager=context_manager
                ),
                media_type="text/event-stream"
            )
        
        # Ejecución normal (no streaming)
        agent_response = await execute_agent(
            tenant_id=tenant_info.tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            query=request.message,
            streaming=False,
            session_id=session_id,
            context=request.context
        )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Tracking de uso en segundo plano
        background_tasks.add_task(
            track_query,
            tenant_id=tenant_info.tenant_id,
            operation_type="public_chat",
            model=agent_response.get("model", "gpt-3.5-turbo"),
            tokens_in=agent_response.get("tokens", 0) // 3,
            tokens_out=agent_response.get("tokens", 0) * 2 // 3,
            agent_id=agent_id,
            conversation_id=conversation_id,
            service="agent-service",
            metadata={
                "streaming": request.stream,
                "session_id": session_id,
                "public_access": True,
                "tenant_slug": tenant_slug
            }
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
    
    # Ejecutar lógica con contexto proporcionado por el decorador
    return await _process_public_chat()