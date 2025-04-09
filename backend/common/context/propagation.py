"""
Funciones para propagar el contexto entre servicios y procesar el contexto
desde y hacia headers HTTP.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, TypeVar, Callable, Awaitable

from .vars import (
    get_current_tenant_id, get_current_agent_id, get_current_conversation_id, 
    get_current_collection_id, set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id, reset_context
)
from .decorators import Context, ContextTokens

logger = logging.getLogger(__name__)

# Tipo para retorno de corrutinas
T = TypeVar('T')

async def run_public_context(
    coro: Awaitable[T],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None
) -> T:
    """
    Ejecuta una corrutina en un contexto público específico.
    
    Esta función centraliza la ejecución de corrutinas en contextos públicos,
    principalmente utilizada para endpoints no autenticados donde es necesario
    establecer manualmente el contexto.
    
    Args:
        coro: Corrutina a ejecutar
        tenant_id: ID del tenant (opcional)
        agent_id: ID del agente (opcional)
        conversation_id: ID de la conversación (opcional)
        collection_id: ID de la colección (opcional)
        
    Returns:
        Resultado de la corrutina
    """
    with Context(tenant_id, agent_id, conversation_id, collection_id):
        return await coro

# Nota: Las siguientes funciones de compatibilidad han sido eliminadas:
# - run_with_tenant
# - run_with_agent_context
# - run_with_full_context
# Usar run_public_context con los parámetros correspondientes.

# === UTILIDADES DE PROPAGACIÓN PARA HTTP HEADERS ===

def extract_context_from_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Extrae información de contexto de los headers HTTP.
    
    Args:
        headers: Diccionario de headers HTTP
        
    Returns:
        Dict[str, str]: Contexto extraído de los headers
    """
    context = {}
    
    # Normalizar claves de header a minúsculas
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    
    # Extraer valores relevantes
    if "x-tenant-id" in normalized_headers:
        context["tenant_id"] = normalized_headers["x-tenant-id"]
    
    if "x-agent-id" in normalized_headers:
        context["agent_id"] = normalized_headers["x-agent-id"]
    
    if "x-conversation-id" in normalized_headers:
        context["conversation_id"] = normalized_headers["x-conversation-id"]
    
    if "x-collection-id" in normalized_headers:
        context["collection_id"] = normalized_headers["x-collection-id"]
    
    return context

def add_context_to_headers(headers: Dict[str, str], include_all: bool = False) -> Dict[str, str]:
    """
    Añade la información de contexto actual a un diccionario de headers HTTP.
    
    Args:
        headers: Diccionario de headers existente
        include_all: Si es True, incluye todos los valores de contexto incluso si son None
        
    Returns:
        Dict[str, str]: Headers con contexto añadido
    """
    # Copiar headers originales para no modificarlos
    new_headers = headers.copy()
    
    # Tenant ID siempre se incluye si está disponible
    tenant_id = get_current_tenant_id()
    if tenant_id and tenant_id != "default":
        new_headers["X-Tenant-ID"] = tenant_id
    
    # Otros valores de contexto solo si include_all=True o tienen valor
    agent_id = get_current_agent_id()
    if include_all or agent_id:
        new_headers["X-Agent-ID"] = str(agent_id) if agent_id else ""
    
    conversation_id = get_current_conversation_id()
    if include_all or conversation_id:
        new_headers["X-Conversation-ID"] = str(conversation_id) if conversation_id else ""
    
    collection_id = get_current_collection_id()
    if include_all or collection_id:
        new_headers["X-Collection-ID"] = str(collection_id) if collection_id else ""
    
    return new_headers

def setup_context_from_headers(headers: Dict[str, str]) -> ContextTokens:
    """
    Configura el contexto actual a partir de headers HTTP.
    
    Args:
        headers: Diccionario de headers HTTP
        
    Returns:
        ContextTokens: Tokens para restaurar el contexto anterior
    """
    context_data = extract_context_from_headers(headers)
    tokens = []
    
    # Establecer valores de contexto y guardar tokens
    if "tenant_id" in context_data:
        tokens.append((set_current_tenant_id(context_data["tenant_id"]), "tenant_id"))
    
    if "agent_id" in context_data:
        tokens.append((set_current_agent_id(context_data["agent_id"]), "agent_id"))
    
    if "conversation_id" in context_data:
        tokens.append((set_current_conversation_id(context_data["conversation_id"]), "conversation_id"))
    
    if "collection_id" in context_data:
        tokens.append((set_current_collection_id(context_data["collection_id"]), "collection_id"))
    
    return tokens