"""
Variables de contexto y funciones de acceso para gestión del contexto de ejecución.

Define las variables contextvars utilizadas para almacenar información como tenant_id, 
agent_id, conversation_id, etc. y proporciona funciones para acceder y modificar estos valores.
"""

import logging
import contextvars
from typing import Dict, Any, Optional, TypeVar, Callable, Awaitable

logger = logging.getLogger(__name__)

# Variables contextvars para mantener el contexto a través de operaciones asíncronas
current_tenant_id = contextvars.ContextVar("current_tenant_id", default="default")
current_agent_id = contextvars.ContextVar("current_agent_id", default=None)
current_conversation_id = contextvars.ContextVar("current_conversation_id", default=None)
current_collection_id = contextvars.ContextVar("current_collection_id", default=None)

# === FUNCIONES PARA OBTENER VALORES DE CONTEXTO ===

def get_current_tenant_id() -> str:
    """
    Obtiene el ID del tenant del contexto de ejecución actual.
    """
    tenant_id = current_tenant_id.get()
    
    # Solo validar si se necesita explícitamente
    if tenant_id and tenant_id != "default" and should_validate_tenant():
        # Importación lazy para evitar ciclo de dependencias
        from ..auth.tenant import is_tenant_active
        if not is_tenant_active(tenant_id):
            from ..errors.exceptions import ServiceError
            logger.warning(f"Intento de acceso a tenant inactivo: {tenant_id}")
            raise ServiceError(
                message="Tenant inactivo o no autorizado",
                status_code=403,
                error_code="TENANT_ACCESS_DENIED"
            )
    
    return tenant_id

def should_validate_tenant() -> bool:
    """Verifica si se debe validar el tenant según configuración"""
    try:
        from ..config.settings import get_settings
        settings = get_settings()
        return getattr(settings, "validate_tenant_access", False)
    except ImportError:
        return False

def get_required_tenant_id() -> str:
    """
    Obtiene el ID del tenant actual, exigiendo que exista uno válido.
    
    Returns:
        str: ID del tenant
        
    Raises:
        ValueError: Si no hay un tenant_id válido en el contexto
    """
    tenant_id = get_current_tenant_id()
    if not tenant_id or tenant_id == "default":
        raise ValueError("No tenant_id disponible en el contexto actual")
    return tenant_id

def get_current_agent_id() -> Optional[str]:
    """
    Obtiene el ID del agente del contexto de ejecución actual.
    
    Returns:
        Optional[str]: ID del agente o None si no está definido
    """
    return current_agent_id.get()

def get_current_conversation_id() -> Optional[str]:
    """
    Obtiene el ID de la conversación del contexto de ejecución actual.
    
    Returns:
        Optional[str]: ID de la conversación o None si no está definido
    """
    return current_conversation_id.get()

def get_current_collection_id() -> Optional[str]:
    """
    Obtiene el ID de la colección del contexto de ejecución actual.
    
    Returns:
        Optional[str]: ID de la colección o None si no está definido
    """
    return current_collection_id.get()

def get_full_context() -> Dict[str, Any]:
    """
    Obtiene un diccionario con todos los valores del contexto actual.
    
    Returns:
        Dict[str, Any]: Contexto completo actual
    """
    return {
        "tenant_id": get_current_tenant_id(),
        "agent_id": get_current_agent_id(),
        "conversation_id": get_current_conversation_id(),
        "collection_id": get_current_collection_id()
    }

def debug_context() -> str:
    """
    Genera una representación del contexto actual para depuración.
    
    Returns:
        str: Representación legible del contexto actual
    """
    context = get_full_context()
    active_levels = [f"{k}='{v}'" for k, v in context.items() if v is not None and v != "default"]
    
    if active_levels:
        return f"Context active: {', '.join(active_levels)}"
    else:
        return "No active context levels"

# === FUNCIONES PARA ESTABLECER VALORES DE CONTEXTO ===

def set_current_tenant_id(tenant_id: str) -> contextvars.Token:
    """
    Establece el ID del tenant en el contexto actual.
    
    Args:
        tenant_id: ID del tenant a establecer
        
    Returns:
        Token: Token para restaurar el contexto anterior
    """
    if not tenant_id:
        tenant_id = "default"
    
    logger.debug(f"Estableciendo tenant_id: {tenant_id}")
    return current_tenant_id.set(tenant_id)

def set_current_agent_id(agent_id: Optional[str]) -> contextvars.Token:
    """
    Establece el ID del agente en el contexto actual.
    
    Args:
        agent_id: ID del agente a establecer
        
    Returns:
        Token: Token para restaurar el contexto anterior
    """
    logger.debug(f"Estableciendo agent_id: {agent_id}")
    return current_agent_id.set(agent_id)

def set_current_conversation_id(conversation_id: Optional[str]) -> contextvars.Token:
    """
    Establece el ID de la conversación en el contexto actual.
    
    Args:
        conversation_id: ID de la conversación a establecer
        
    Returns:
        Token: Token para restaurar el contexto anterior
    """
    logger.debug(f"Estableciendo conversation_id: {conversation_id}")
    return current_conversation_id.set(conversation_id)

def set_current_collection_id(collection_id: Optional[str]) -> contextvars.Token:
    """
    Establece el ID de la colección en el contexto actual.
    
    Args:
        collection_id: ID de la colección a establecer
        
    Returns:
        Token: Token para restaurar el contexto anterior
    """
    logger.debug(f"Estableciendo collection_id: {collection_id}")
    return current_collection_id.set(collection_id)

# === FUNCIONES PARA RESTABLECER VALORES DE CONTEXTO ===

def reset_context(token: contextvars.Token, context_name: str) -> None:
    """
    Restablece un valor de contexto usando su token.
    
    Args:
        token: Token devuelto por la función set_*
        context_name: Nombre del contexto para logging
    """
    logger.debug(f"Restableciendo {context_name}")
    if token:
        if context_name == "tenant_id":
            current_tenant_id.reset(token)
        elif context_name == "agent_id":
            current_agent_id.reset(token)
        elif context_name == "conversation_id":
            current_conversation_id.reset(token)
        elif context_name == "collection_id":
            current_collection_id.reset(token)