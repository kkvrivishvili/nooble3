"""
Funciones helper para operaciones RPC críticas en Supabase.

Este módulo centraliza las llamadas a procedimientos almacenados (RPC) 
que realizan operaciones críticas que requieren transaccionalidad o 
manipulan múltiples tablas.

Principios para usar RPC vs acceso directo a tablas:
1. Usar RPC para:
   - Operaciones que deben ser atómicas (contadores, estadísticas)
   - Operaciones que afectan múltiples tablas (crear conversación + mensajes)
   - Operaciones con validaciones complejas (verificar cuotas, límites)

2. Usar acceso directo a tablas para:
   - Operaciones CRUD simples en una sola tabla
   - Consultas con filtros sencillos
   - Operaciones sin requisitos transaccionales
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from uuid import UUID

from .supabase import get_supabase_client
from ..errors.exceptions import ServiceError

logger = logging.getLogger(__name__)

async def create_conversation(
    tenant_id: str, 
    agent_id: str, 
    title: str, 
    context: Optional[Dict[str, Any]] = None,
    client_reference_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Crea una nueva conversación utilizando el procedimiento almacenado.
    
    Esta operación es transaccional y crea el registro en la tabla conversations
    con todas las validaciones necesarias.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente asociado a la conversación
        title: Título de la conversación
        context: Contexto adicional para la conversación (opcional)
        client_reference_id: ID de referencia del cliente (opcional)
        metadata: Metadatos adicionales (opcional)
        
    Returns:
        Dict con los datos de la conversación creada, incluyendo conversation_id
        
    Raises:
        ServiceError: Si hay un error al crear la conversación
    """
    supabase = get_supabase_client()
    
    try:
        result = await supabase.rpc(
            "create_conversation",
            {
                "p_tenant_id": tenant_id,
                "p_agent_id": agent_id,
                "p_title": title,
                "p_context": json.dumps(context) if context else "{}",
                "p_client_reference_id": client_reference_id,
                "p_metadata": json.dumps(metadata) if metadata else "{}"
            }
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error creating conversation: {result.error.message}",
                error_code="CONVERSATION_CREATION_ERROR"
            )
        
        return result.data
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error creating conversation: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error creating conversation: {str(e)}",
                error_code="CONVERSATION_CREATION_ERROR"
            )
        raise


async def add_chat_message(
    conversation_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Agrega un nuevo mensaje a una conversación existente.
    
    Esta operación es transaccional y garantiza que el mensaje se añada correctamente
    con todas las validaciones necesarias.
    
    Args:
        conversation_id: ID de la conversación
        role: Rol del mensaje ('user', 'assistant', 'system')
        content: Contenido del mensaje
        metadata: Metadatos adicionales (opcional)
        
    Returns:
        Dict con los datos del mensaje creado
        
    Raises:
        ServiceError: Si hay un error al añadir el mensaje
    """
    supabase = get_supabase_client()
    
    try:
        result = await supabase.rpc(
            "add_chat_message",
            {
                "p_conversation_id": conversation_id,
                "p_role": role,
                "p_content": content,
                "p_metadata": json.dumps(metadata) if metadata else "{}"
            }
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error adding chat message: {result.error.message}",
                error_code="MESSAGE_CREATION_ERROR"
            )
        
        return result.data
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error adding chat message: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error adding chat message: {str(e)}",
                error_code="MESSAGE_CREATION_ERROR"
            )
        raise


async def add_chat_history(
    conversation_id: str,
    tenant_id: str,
    agent_id: str,
    user_message: str,
    assistant_message: str,
    thinking: str = "",
    tools_used: Optional[List[Dict[str, Any]]] = None,
    processing_time: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Agrega un intercambio completo (usuario + asistente) al historial de chat.
    
    Esta función es específica para el servicio de agentes donde se registra tanto
    el mensaje del usuario como la respuesta del asistente en una sola operación.
    
    Args:
        conversation_id: ID de la conversación
        tenant_id: ID del tenant
        agent_id: ID del agente
        user_message: Mensaje del usuario
        assistant_message: Respuesta del asistente
        thinking: Proceso de razonamiento del asistente (opcional)
        tools_used: Lista de herramientas utilizadas (opcional)
        processing_time: Tiempo de procesamiento en segundos (opcional)
        metadata: Metadatos adicionales (opcional)
        
    Returns:
        Dict con los datos del registro creado
        
    Raises:
        ServiceError: Si hay un error al añadir el historial
    """
    supabase = get_supabase_client()
    
    try:
        result = await supabase.rpc(
            "add_chat_history",  
            {
                "p_conversation_id": conversation_id,
                "p_tenant_id": tenant_id,
                "p_agent_id": agent_id,
                "p_user_message": user_message,
                "p_assistant_message": assistant_message,
                "p_thinking": thinking or "",
                "p_tools_used": json.dumps(tools_used or []),
                "p_processing_time": processing_time,
                "p_metadata": json.dumps(metadata) if metadata else "{}"
            }
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error adding chat history: {result.error.message}",
                error_code="CHAT_HISTORY_CREATION_ERROR" 
            )
        
        return result.data
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error adding chat history: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error adding chat history: {str(e)}",
                error_code="CHAT_HISTORY_CREATION_ERROR"
            )
        raise


async def check_conversation_exists(conversation_id: str) -> bool:
    """
    Verifica si una conversación existe en la base de datos.
    
    Args:
        conversation_id: ID de la conversación a verificar
        
    Returns:
        bool: True si la conversación existe, False en caso contrario
    """
    from common.db.tables import get_table_name
    
    supabase = get_supabase_client()
    
    result = await supabase.table(get_table_name("conversations")) \
        .select("id") \
        .eq("id", conversation_id) \
        .execute()
    
    return bool(result.data)


from ..errors import handle_errors, ErrorCode

@handle_errors(error_type="service", log_traceback=True)
async def ensure_conversation_exists(
    tenant_id: str,
    agent_id: str,
    conversation_id: str,
    title: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    client_reference_id: Optional[str] = None
) -> str:
    """
    Asegura que una conversación exista o la crea.
    
    Esta función verifica si existe una conversación con el ID proporcionado.
    Si no existe, la crea utilizando los parámetros proporcionados.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        conversation_id: ID de la conversación
        title: Título de la conversación (opcional)
        context: Contexto adicional (opcional)
        client_reference_id: ID de referencia del cliente (opcional)
        
    Returns:
        str: ID de la conversación (la existente o la recién creada)
        
    Raises:
        ServiceError: Si hay un error al verificar o crear la conversación
    """
    # Verificar si existe
    if await check_conversation_exists(conversation_id):
        return conversation_id
    
    # Crear si no existe
    result = await create_conversation(
        tenant_id=tenant_id,
        agent_id=agent_id,
        title=title or f"Conversación {conversation_id[:8]}",
        context=context or {},
        client_reference_id=client_reference_id
    )
    
    return result.get("conversation_id", conversation_id)


async def increment_token_usage(
    tenant_id: str, 
    tokens: int,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    token_type: str = "llm"
) -> bool:
    """
    Incrementa el contador de tokens usados por un tenant de forma atómica.
    
    AVISO DE OBSOLESCENCIA:
    Esta función está obsoleta y será eliminada en futuras versiones.
    Por favor, use common.tracking.track_token_usage() en su lugar.
    
    Esta función ahora utiliza internamente TokenAttributionService para mantener
    consistencia con el resto del sistema.
    
    Args:
        tenant_id: ID del tenant que realiza la solicitud
        tokens: Número de tokens a incrementar
        agent_id: ID del agente con el que se interactúa (opcional)
        conversation_id: ID de la conversación (opcional)
        token_type: Tipo de tokens a contabilizar ('llm' o 'embedding')
        
    Returns:
        True si se incrementó correctamente
        
    Raises:
        ServiceError: Si hay un error al incrementar los tokens
    """
    # Importación tardía para evitar ciclo circular con tracking.attribution
    from ..tracking.attribution import TokenAttributionService
    
    # Determinar el tenant efectivo (propietario) usando el mismo servicio
    # que usa track_token_usage para mantener consistencia
    effective_tenant_id = await TokenAttributionService.determine_token_owner(
        requester_tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Llamar a la implementación simplificada
    return await increment_token_usage_raw(
        tenant_id=effective_tenant_id,
        tokens=tokens,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type=token_type
    )


async def increment_token_usage_raw(
    tenant_id: str, 
    tokens: int,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    token_type: str = "llm"
) -> bool:
    """
    Función RPC pura que incrementa el contador de tokens en la base de datos.
    
    Esta función NO contiene lógica de negocio, solo la llamada al procedimiento RPC.
    La lógica de atribución de tokens se maneja en las capas superiores (TokenAttributionService).
    
    Args:
        tenant_id: ID del tenant (ya debe ser el correcto)
        tokens: Número de tokens a incrementar
        agent_id: ID del agente (solo para fines de registro)
        conversation_id: ID de la conversación (solo para fines de registro)
        token_type: Tipo de tokens ('llm' o 'embedding')
        
    Returns:
        bool: True si se incrementó correctamente
    """
    supabase = get_supabase_client()
    
    try:
        # Usar el procedimiento almacenado específico según el tipo de token
        if token_type == "embedding":
            rpc_name = "increment_embedding_token_usage"
        else:  # Por defecto usar llm
            rpc_name = "increment_token_usage"
            
        result = await supabase.rpc(
            rpc_name,
            {
                "p_tenant_id": tenant_id,
                "p_tokens": tokens
            }
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error incrementing {token_type} token usage: {result.error.message}",
                error_code="TOKEN_TRACKING_ERROR"
            )
            
        return True
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error incrementing {token_type} token usage: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error incrementing {token_type} token usage: {str(e)}",
                error_code="TOKEN_TRACKING_ERROR"
            )
        raise


async def increment_document_count(
    tenant_id: str, 
    count: int = 1,
    collection_id: Optional[str] = None
) -> bool:
    """
    Incrementa el contador de documentos para un tenant de forma atómica.
    
    Esta operación debe ser atómica para mantener consistencia en los contadores
    de documentos por tenant y colección.
    
    Args:
        tenant_id: ID del tenant
        count: Número de documentos a incrementar (por defecto 1)
        collection_id: ID de la colección (opcional, si no se proporciona, solo se incrementa el contador global)
        
    Returns:
        True si se incrementó correctamente
        
    Raises:
        ServiceError: Si hay un error al incrementar el contador
    """
    supabase = get_supabase_client()
    
    try:
        params = {
            "p_tenant_id": tenant_id,
            "p_count": count
        }
        
        # Si se proporciona collection_id, añadirlo a los parámetros
        if collection_id:
            params["p_collection_id"] = collection_id
            
        result = await supabase.rpc(
            "increment_document_count",
            params
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error incrementing document count: {result.error.message}",
                error_code="DOCUMENT_TRACKING_ERROR"
            )
        
        return True
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error incrementing document count: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error incrementing document count: {str(e)}",
                error_code="DOCUMENT_TRACKING_ERROR"
            )
        raise


async def decrement_document_count(
    tenant_id: str, 
    count: int = 1,
    collection_id: Optional[str] = None
) -> bool:
    """
    Decrementa el contador de documentos para un tenant de forma atómica.
    
    Esta operación debe ser atómica para mantener consistencia en los contadores
    de documentos por tenant y colección.
    
    Args:
        tenant_id: ID del tenant
        count: Número de documentos a decrementar (por defecto 1)
        collection_id: ID de la colección (opcional, si no se proporciona, solo se decrementa el contador global)
        
    Returns:
        True si se decrementó correctamente
        
    Raises:
        ServiceError: Si hay un error al decrementar el contador
    """
    supabase = get_supabase_client()
    
    try:
        params = {
            "p_tenant_id": tenant_id,
            "p_count": count
        }
        
        # Si se proporciona collection_id, añadirlo a los parámetros
        if collection_id:
            params["p_collection_id"] = collection_id
            
        result = await supabase.rpc(
            "decrement_document_count",
            params
        ).execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error decrementing document count: {result.error.message}",
                error_code="DOCUMENT_TRACKING_ERROR"
            )
        
        return True
    except Exception as e:
        if not isinstance(e, ServiceError):
            logger.error(f"Unexpected error decrementing document count: {str(e)}")
            raise ServiceError(
                message=f"Unexpected error decrementing document count: {str(e)}",
                error_code="DOCUMENT_TRACKING_ERROR"
            )
        raise