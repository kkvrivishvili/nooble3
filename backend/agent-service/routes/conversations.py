import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Path, Query

from common.models import TenantInfo, ConversationListResponse, MessageListResponse, DeleteConversationResponse, ChatMessage
from common.errors import handle_service_error_simple, AgentNotFoundError, ConversationError
from common.context import with_context
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.auth import verify_tenant
from common.cache.manager import CacheManager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("", response_model=ConversationListResponse)
@with_context(tenant=True)
@handle_service_error_simple
async def list_conversations(
    agent_id: Optional[str] = None,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> ConversationListResponse:
    """
    Lista todas las conversaciones del tenant, opcionalmente filtradas por agente.
    
    Args:
        agent_id: ID del agente para filtrar (opcional)
        tenant_info: Información del tenant (inyectada mediante verify_tenant)
        
    Returns:
        ConversationListResponse: Lista de conversaciones
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Preparar la consulta base
        query = supabase.table(get_table_name("conversations")).select("*").eq("tenant_id", tenant_id)
        
        # Aplicar filtro por agente si se proporciona
        if agent_id:
            query = query.eq("agent_id", agent_id)
            
            # Verificar que el agente exista y pertenezca al tenant
            agent_result = await supabase.table(get_table_name("agent_configs")).select("agent_id").eq("agent_id", agent_id).eq("tenant_id", tenant_id).execute()
            if not agent_result.data:
                raise AgentNotFoundError(
                    message=f"Agent {agent_id} not found or not accessible",
                    details={"tenant_id": tenant_id, "agent_id": agent_id}
                )
        
        # Ejecutar la consulta ordenando por fecha de actualización descendente
        result = await query.order("updated_at", desc=True).execute()
        
        # Procesar resultados
        conversations_list = []
        for conversation_data in result.data:
            # Obtener el último mensaje (opcional si lo guardamos en la tabla de conversaciones)
            last_message = conversation_data.get("last_message", "")
            if not last_message:
                try:
                    message_result = await supabase.table(get_table_name("chat_history")).select("*").eq("conversation_id", conversation_data["id"]).order("created_at", desc=True).limit(1).execute()
                    if message_result.data:
                        last_message = message_result.data[0].get("content", "")
                        if len(last_message) > 100:
                            last_message = last_message[:97] + "..."
                except Exception as e:
                    logger.warning(f"Error obteniendo último mensaje: {str(e)}")
            
            # Crear el resumen de conversación
            conversation_summary = {
                "conversation_id": conversation_data["id"],
                "agent_id": conversation_data["agent_id"],
                "title": conversation_data.get("title", "Nueva conversación"),
                "created_at": conversation_data.get("created_at"),
                "updated_at": conversation_data.get("updated_at"),
                "message_count": conversation_data.get("message_count", 0),
                "last_message": last_message
            }
            conversations_list.append(conversation_summary)
        
        return ConversationListResponse(
            success=True,
            message="Conversaciones obtenidas exitosamente",
            conversations=conversations_list,
            count=len(conversations_list)
        )
        
    except ConversationError:
        raise
    except Exception as e:
        logger.error(f"Error listando conversaciones: {str(e)}")
        raise ConversationError(
            message="Error al listar conversaciones",
            details={"tenant_id": tenant_id}
        )

@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
@with_context(tenant=True, conversation=True)
@handle_service_error_simple
async def get_conversation_messages(
    conversation_id: str,
    limit: Optional[int] = Query(None, description="Número máximo de mensajes a devolver"), 
    offset: int = Query(0, description="Desplazamiento para paginación"),
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> MessageListResponse:
    """
    Obtiene los mensajes de una conversación específica.
    
    Args:
        conversation_id: ID de la conversación
        limit: Número máximo de mensajes a devolver (por defecto: de settings)
        offset: Desplazamiento para paginación (por defecto 0)
        tenant_info: Información del tenant (inyectada mediante verify_tenant)
        
    Returns:
        MessageListResponse: Lista de mensajes de la conversación
    """
    from common.config import get_settings
    settings = get_settings()
    
    # El tenant_id y conversation_id ya están disponibles gracias al decorador
    tenant_id = tenant_info.tenant_id
    
    # Usar el límite de la configuración si no se proporciona uno específico
    effective_limit = limit if limit is not None else settings.agent_default_message_limit
    
    try:
        supabase = get_supabase_client()
        
        # Verificar que la conversación exista y pertenezca al tenant
        conversation_result = await supabase.table(get_table_name("conversations")).select("*").eq("id", conversation_id).eq("tenant_id", tenant_id).execute()
        
        if not conversation_result.data or len(conversation_result.data) == 0:
            raise ConversationError(
                message=f"Conversación {conversation_id} no encontrada o no pertenece al tenant",
                details={"tenant_id": tenant_id, "conversation_id": conversation_id}
            )
        
        # Obtener los mensajes de la conversación
        messages_result = await supabase.table(get_table_name("chat_history")).select("*").eq("conversation_id", conversation_id).order("created_at", desc=False).range(offset, offset + effective_limit - 1).execute()
        
        # Convertir a formato ChatMessage
        messages = []
        for message_data in messages_result.data:
            message = ChatMessage(
                role=message_data.get("role", "user"),
                content=message_data.get("content", ""),
                metadata={
                    "created_at": message_data.get("created_at"),
                    "id": message_data.get("id"),
                    "thinking": message_data.get("thinking", ""),
                    "tools_used": message_data.get("tools_used", [])
                }
            )
            messages.append(message)
        
        # Obtener el conteo total de mensajes
        count_result = await supabase.table(get_table_name("chat_history")).select("count", count="exact").eq("conversation_id", conversation_id).execute()
        total_count = count_result.count if hasattr(count_result, "count") else len(messages)
        
        return MessageListResponse(
            success=True,
            message="Mensajes obtenidos exitosamente",
            conversation_id=conversation_id,
            messages=messages,
            total=total_count,
            limit=effective_limit,
            offset=offset
        )
        
    except ConversationError:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo mensajes: {str(e)}")
        raise ConversationError(
            message="Error al obtener mensajes de la conversación",
            details={"tenant_id": tenant_id, "conversation_id": conversation_id}
        )

@router.delete("/{conversation_id}", response_model=DeleteConversationResponse)
@with_context(tenant=True, conversation=True)
@handle_service_error_simple
async def delete_conversation(
    conversation_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> DeleteConversationResponse:
    """Elimina una conversación específica y todos sus mensajes asociados."""
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Verificar que la conversación exista y pertenezca al tenant
        conversation_result = await supabase.table(get_table_name("conversations")) \
            .select("*") \
            .eq("id", conversation_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if not conversation_result.data:
            raise ServiceError(
                message=f"Conversación {conversation_id} no encontrada",
                error_code="conversation_not_found",
                status_code=404
            )
        
        agent_id = conversation_result.data[0].get("agent_id")
        
        # Contar mensajes asociados
        messages_count_result = await supabase.table(get_table_name("chat_history")) \
            .select("count", count="exact") \
            .eq("conversation_id", conversation_id) \
            .execute()
            
        messages_count = messages_count_result.count if hasattr(messages_count_result, "count") else 0
        
        # Eliminar mensajes
        if messages_count > 0:
            await supabase.table(get_table_name("chat_history")) \
                .delete() \
                .eq("conversation_id", conversation_id) \
                .execute()
        
        # Eliminar la conversación
        delete_result = await supabase.table(get_table_name("conversations")) \
            .delete() \
            .eq("id", conversation_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if delete_result.error:
            raise ServiceError(
                message="Error al eliminar la conversación",
                status_code=500,
                error_code="DELETE_FAILED"
            )
        
        # Invalidar caché para esta conversación
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="agent_response",
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="conversation_messages",
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        
        return DeleteConversationResponse(
            success=True,
            message=f"Conversación {conversation_id} eliminada exitosamente",
            conversation_id=conversation_id,
            deleted=True,
            messages_deleted=messages_count
        )
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        logger.error(f"Error eliminando conversación: {str(e)}")
        raise ServiceError(
            message="Error al eliminar la conversación",
            status_code=500,
            error_code="DELETE_FAILED"
        )

@router.post("/{conversation_id}/end", response_model=DeleteConversationResponse)
@with_context(tenant=True, conversation=True)
@handle_service_error_simple
async def end_conversation(
    conversation_id: str,
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> DeleteConversationResponse:
    """
    Finaliza una conversación guardando su historial y liberando recursos.
    
    Este endpoint marca la conversación como terminada, asegura que todos los
    mensajes estén guardados, e invalida la caché para liberar recursos.
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Verificar que la conversación exista y pertenezca al tenant
        conversation_result = await supabase.table(get_table_name("conversations")) \
            .select("*") \
            .eq("id", conversation_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if not conversation_result.data:
            raise ServiceError(
                message=f"Conversación {conversation_id} no encontrada",
                error_code="conversation_not_found",
                status_code=404
            )
        
        agent_id = conversation_result.data[0].get("agent_id")
        
        # Marcar conversación como terminada
        update_result = await supabase.table(get_table_name("conversations")) \
            .update({"is_active": False, "ended_at": "NOW()"}) \
            .eq("id", conversation_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if update_result.error:
            raise ServiceError(
                message="Error al finalizar la conversación",
                status_code=500,
                error_code="UPDATE_FAILED"
            )
        
        # Invalidar caché de respuestas y mensajes de esta conversación
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="agent_response",
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="conversation_messages",
            agent_id=agent_id,
            conversation_id=conversation_id
        )
        
        return DeleteConversationResponse(
            success=True,
            message=f"Conversación {conversation_id} finalizada exitosamente",
            conversation_id=conversation_id,
            deleted=False,
            messages_deleted=0
        )
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        logger.error(f"Error finalizando conversación: {str(e)}")
        raise ServiceError(
            message="Error al finalizar la conversación",
            status_code=500,
            error_code="UPDATE_FAILED"
        )