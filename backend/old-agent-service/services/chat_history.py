"""
Funciones para gestionar el historial de chat de agentes.
Implementa el patrón Cache-Aside estandarizado para el acceso a datos.
"""

import logging
import uuid
import time
from typing import Dict, Any, List, Optional

from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.errors import handle_errors, ServiceError, ErrorCode
from common.tracking import track_operation
from common.cache import (
    CacheManager,
    get_with_cache_aside,
    generate_resource_id_hash,
    serialize_for_cache,
    deserialize_from_cache
)

logger = logging.getLogger(__name__)

@handle_errors(error_type="service", log_traceback=True)
@track_operation(operation_name="add_chat_history", operation_type="chat")
async def add_chat_history(
    conversation_id: str,
    tenant_id: str,
    agent_id: str,
    user_message: str,
    assistant_message: str,
    thinking: Optional[str] = "",
    tools_used: Optional[List[Dict[str, Any]]] = None,
    processing_time: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Guarda una interacción de chat en la base de datos y actualiza la caché.
    
    Args:
        conversation_id: ID de la conversación
        tenant_id: ID del tenant
        agent_id: ID del agente
        user_message: Mensaje del usuario
        assistant_message: Respuesta del asistente
        thinking: Pasos de pensamiento (opcional)
        tools_used: Lista de herramientas utilizadas (opcional)
        processing_time: Tiempo de procesamiento en segundos (opcional)
        metadata: Metadata adicional (opcional)
        
    Returns:
        Dict[str, Any]: Entrada de historial creada
    """
    # Validar parámetros
    if not conversation_id or not tenant_id or not agent_id:
        raise ServiceError(
            message="Se requieren conversation_id, tenant_id y agent_id para guardar historial",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    try:
        # Generar ID único para el mensaje
        message_id = str(uuid.uuid4())
        timestamp = int(time.time())
        
        # Preparar datos para Supabase
        chat_entry = {
            "id": message_id,
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "thinking": thinking if thinking else "",
            "tools_used": tools_used if tools_used else [],
            "timestamp": timestamp,
            "processing_time": processing_time if processing_time else 0.0,
            "metadata": metadata if metadata else {}
        }
        
        # Guardar en Supabase
        supabase = get_supabase_client()
        table_name = get_table_name("chat_history")
        
        result = await supabase.table(table_name).insert(chat_entry).execute()
        
        if result.error:
            logger.error(f"Error guardando historial en Supabase: {result.error}")
            raise ServiceError(
                message=f"Error guardando historial: {result.error}",
                error_code=ErrorCode.DATABASE_ERROR
            )
        
        # Actualizar caché de conversación
        resource_id = f"conversation:{conversation_id}"
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="conversation_history",
            resource_id=resource_id,
            agent_id=agent_id
        )
        
        logger.info(f"Historial guardado para conversación {conversation_id}")
        return chat_entry
        
    except Exception as e:
        if isinstance(e, ServiceError):
            raise
        
        logger.error(f"Error inesperado guardando historial: {str(e)}")
        raise ServiceError(
            message=f"Error inesperado guardando historial: {str(e)}",
            error_code=ErrorCode.DATABASE_ERROR
        )

@handle_errors(error_type="service")
@track_operation(operation_name="get_chat_history", operation_type="chat")
async def get_chat_history(
    conversation_id: str,
    tenant_id: str,
    agent_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Obtiene el historial de chat para una conversación implementando el patrón Cache-Aside.
    
    Args:
        conversation_id: ID de la conversación
        tenant_id: ID del tenant
        agent_id: ID del agente (opcional)
        limit: Límite de mensajes a retornar
        offset: Desplazamiento para paginación
        
    Returns:
        List[Dict[str, Any]]: Lista de mensajes en la conversación
    """
    # Validar parámetros
    if not conversation_id or not tenant_id:
        raise ServiceError(
            message="Se requieren conversation_id y tenant_id para obtener historial",
            error_code=ErrorCode.INVALID_ARGUMENT
        )
    
    # Generar identificador de recurso para caché
    resource_id = f"conversation:{conversation_id}:limit={limit}:offset={offset}"
    
    # Función para buscar historial en Supabase si no está en caché
    async def fetch_history_from_db(resource_id, tenant_id, ctx=None):
        """Busca historial de conversación en Supabase"""
        try:
            # Obtener cliente y tabla
            supabase = get_supabase_client()
            table_name = get_table_name("chat_history")
            
            # Iniciar consulta
            query = (supabase.table(table_name)
                    .select("*")
                    .eq("conversation_id", conversation_id)
                    .eq("tenant_id", tenant_id)
                    .order("timestamp", desc=False))
            
            # Filtrar por agente si se proporciona
            if agent_id:
                query = query.eq("agent_id", agent_id)
            
            # Aplicar paginación
            query = query.range(offset, offset + limit - 1)
            
            # Ejecutar consulta
            result = await query.execute()
            
            if result.error:
                logger.error(f"Error buscando historial en Supabase: {result.error}")
                return []
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error buscando historial en Supabase: {str(e)}")
            return []
    
    # No necesitamos generar historial, sólo recuperarlo
    async def generate_history(resource_id, tenant_id, ctx=None):
        return None
    
    # Usar la implementación centralizada del patrón Cache-Aside
    history, metrics = await get_with_cache_aside(
        data_type="conversation_history",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_history_from_db,
        generate_func=generate_history,
        agent_id=agent_id
        # TTL se determina automáticamente por tipo de dato
    )
    
    # Si no hay historial, devolver lista vacía
    if not history:
        return []
    
    return history
