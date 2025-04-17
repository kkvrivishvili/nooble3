"""
Variables y funciones de contexto para gestión de contexto multi-tenant.

Este módulo proporciona las variables contextuales y funciones básicas
para acceder a información de contexto. Para validación, utilizar el decorador
@with_context que proporciona validación centralizada y gestión de errores.
"""

import logging
from contextvars import ContextVar
from typing import Optional, Dict

from common.errors import ServiceError, ErrorCode

logger = logging.getLogger(__name__)

# Variables de contexto principales
current_tenant_id: ContextVar[Optional[str]] = ContextVar('current_tenant_id', default=None)
current_agent_id: ContextVar[Optional[str]] = ContextVar('current_agent_id', default=None)
current_conversation_id: ContextVar[Optional[str]] = ContextVar('current_conversation_id', default=None)
current_collection_id: ContextVar[Optional[str]] = ContextVar('current_collection_id', default=None)

# Funciones básicas de acceso a contexto (sin validación)
def get_current_tenant_id() -> Optional[str]:
    """
    Obtiene el tenant_id del contexto actual sin validación.
    
    Para validación, utilizar el decorador @with_context con validate_tenant=True
    o acceder a través de ctx.get_tenant_id() dentro de una función decorada.
    
    Returns:
        Optional[str]: ID del tenant actual o None si no está definido
    """
    return current_tenant_id.get()

def get_current_agent_id() -> Optional[str]:
    """
    Obtiene el agent_id del contexto actual.
    
    Returns:
        Optional[str]: ID del agente actual o None si no está definido
    """
    return current_agent_id.get()

def get_current_conversation_id() -> Optional[str]:
    """
    Obtiene el conversation_id del contexto actual.
    
    Returns:
        Optional[str]: ID de la conversación actual o None si no está definido
    """
    return current_conversation_id.get()

def get_current_collection_id() -> Optional[str]:
    """
    Obtiene el collection_id del contexto actual.
    
    Returns:
        Optional[str]: ID de la colección actual o None si no está definido
    """
    return current_collection_id.get()

def set_current_tenant_id(tenant_id: Optional[str]) -> None:
    """
    Establece el tenant_id en el contexto actual.
    
    Args:
        tenant_id: ID del tenant a establecer o None para limpiar
    """
    if tenant_id is None:
        current_tenant_id.set(None)
    else:
        current_tenant_id.set(str(tenant_id))

def set_current_agent_id(agent_id: Optional[str]) -> None:
    """
    Establece el agent_id en el contexto actual.
    
    Args:
        agent_id: ID del agente a establecer o None para limpiar
    """
    if agent_id is None:
        current_agent_id.set(None)
    else:
        current_agent_id.set(str(agent_id))

def set_current_conversation_id(conversation_id: Optional[str]) -> None:
    """
    Establece el conversation_id en el contexto actual.
    
    Args:
        conversation_id: ID de la conversación a establecer o None para limpiar
    """
    if conversation_id is None:
        current_conversation_id.set(None)
    else:
        current_conversation_id.set(str(conversation_id))

def set_current_collection_id(collection_id: Optional[str]) -> None:
    """
    Establece el collection_id en el contexto actual.
    
    Args:
        collection_id: ID de la colección a establecer o None para limpiar
    """
    if collection_id is None:
        current_collection_id.set(None)
    else:
        current_collection_id.set(str(collection_id))

def get_full_context() -> Dict[str, Optional[str]]:
    """
    Obtiene un diccionario con todas las variables de contexto actuales.
    """
    return {
        "tenant_id": get_current_tenant_id(),
        "agent_id": get_current_agent_id(),
        "conversation_id": get_current_conversation_id(),
        "collection_id": get_current_collection_id(),
    }

# Alias para compatibilidad (NOTA: Estas funciones están obsoletas, usar @with_context)
def get_required_tenant_id() -> str:
    """
    FUNCIÓN OBSOLETA: Utilizar el decorador @with_context(tenant=True) y ctx.get_tenant_id() en su lugar.
    
    Esta función está mantenida por compatibilidad y redirige a Context para validación.
    """
    from .decorators import Context
    return Context.validate_tenant_id(current_tenant_id.get())

def validate_tenant_context(tenant_id: str) -> str:
    """
    FUNCIÓN OBSOLETA: Utilizar el decorador @with_context(tenant=True) y ctx.get_tenant_id() en su lugar.
    
    Esta función está mantenida por compatibilidad y redirige a Context para validación.
    """
    from .decorators import Context
    return Context.validate_tenant_id(tenant_id)