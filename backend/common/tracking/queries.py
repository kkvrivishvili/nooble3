"""
Seguimiento de consultas para analíticas y facturación.
"""

import time
import logging
from typing import Dict, Any, Optional

from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
from ..config.settings import get_settings
from .tokens import track_token_usage

logger = logging.getLogger(__name__)

async def track_query(
    tenant_id: str, 
    operation_type: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """
    Registra una consulta para análisis y facturación.
    
    En caso de conversaciones públicas con agentes, detecta automáticamente si los tokens
    deben contabilizarse al propietario del agente en lugar del usuario que interactúa.
    
    Args:
        tenant_id: ID del tenant que realiza la solicitud (obtenido del JWT)
        operation_type: Tipo de operación (query, chat, etc)
        model: Modelo LLM utilizado
        tokens_in: Tokens de entrada
        tokens_out: Tokens de salida generados
        agent_id: ID del agente (opcional)
                  Si se proporciona, se verifica si los tokens deben contabilizarse al propietario.
        conversation_id: ID de la conversación (opcional)
        
    Returns:
        bool: True si se registró correctamente
    """
    # Verificar si el tracking está habilitado
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de uso deshabilitado, omitiendo registro de consulta para {tenant_id}")
        return True
        
    supabase = get_supabase_client()
    
    try:
        # Calcular total de tokens
        total_tokens = tokens_in + tokens_out
        
        # Metadatos básicos de la consulta
        metadata = {
            "tenant_id": tenant_id,
            "operation_type": operation_type,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": total_tokens,
            "timestamp": int(time.time())
        }
        
        # Agregar agent_id y conversation_id si están presentes
        if agent_id:
            metadata["agent_id"] = agent_id
        
        if conversation_id:
            metadata["conversation_id"] = conversation_id
        
        # Registrar uso de tokens primero (verificando automáticamente si debe contabilizarse al propietario)
        await track_token_usage(
            tenant_id=tenant_id, 
            tokens=total_tokens, 
            model=model,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type="llm"
        )
        
        # Registrar la consulta para analytics
        await supabase.table(get_table_name("query_logs")).insert(metadata).execute()
        
        return True
    except Exception as e:
        logger.error(f"Error tracking query: {str(e)}")
        return False

async def track_usage(tenant_id: str, operation: str, metadata: Dict[str, Any]) -> bool:
    """
    Registra el uso de servicios para un tenant.
    
    Args:
        tenant_id: ID del tenant
        operation: Tipo de operación (query, embedding, ingestion, etc.)
        metadata: Metadatos adicionales sobre la operación
        
    Returns:
        bool: True si se registró correctamente
    """
    try:
        if operation == "query":
            return await track_query(
                tenant_id=tenant_id,
                operation_type=metadata.get("operation_type", "query"),
                model=metadata.get("model", "unknown"),
                tokens_in=metadata.get("tokens_in", 0),
                tokens_out=metadata.get("tokens_out", 0),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id")
            )
        elif operation == "embedding":
            return await track_embedding_usage(
                tenant_id=tenant_id,
                texts=metadata.get("texts", []),
                model=metadata.get("model", "unknown"),
                cached_count=metadata.get("cached_count", 0),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id")
            )
        elif operation == "tokens":
            return await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("tokens", 0),
                model=metadata.get("model", None),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id"),
                token_type=metadata.get("token_type", "llm")
            )
        else:
            logger.warning(f"Tipo de operación desconocido para tracking: {operation}")
            return False
    except Exception as e:
        logger.error(f"Error al registrar uso: {str(e)}")
        return False