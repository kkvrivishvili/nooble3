"""
Funciones para propagar el contexto entre servicios y procesar el contexto
desde y hacia headers HTTP.
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, TypeVar, Callable, Awaitable

from .vars import (
    get_current_tenant_id, get_current_agent_id, get_current_conversation_id, 
    get_current_collection_id, set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id, reset_context,
    get_full_context
)
from .decorators import Context, ContextTokens

logger = logging.getLogger(__name__)

# Tipo para retorno de corrutinas
T = TypeVar('T')

# Claves de encabezado para propagación de contexto
TENANT_ID_HEADER = "X-Tenant-ID"
AGENT_ID_HEADER = "X-Agent-ID"
CONVERSATION_ID_HEADER = "X-Conversation-ID"
COLLECTION_ID_HEADER = "X-Collection-ID"

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
        new_headers[TENANT_ID_HEADER] = tenant_id
    
    # Otros valores de contexto solo si include_all=True o tienen valor
    agent_id = get_current_agent_id()
    if include_all or agent_id:
        new_headers[AGENT_ID_HEADER] = str(agent_id) if agent_id else ""
    
    conversation_id = get_current_conversation_id()
    if include_all or conversation_id:
        new_headers[CONVERSATION_ID_HEADER] = str(conversation_id) if conversation_id else ""
    
    collection_id = get_current_collection_id()
    if include_all or collection_id:
        new_headers[COLLECTION_ID_HEADER] = str(collection_id) if collection_id else ""
    
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

# === UTILIDADES PARA LOGGING CON CONTEXTO ===

def get_context_log_prefix() -> str:
    """
    Genera un prefijo para logs que incluye el contexto actual.
    
    Returns:
        str: Prefijo con información de contexto para logs
    """
    ctx = get_full_context()
    parts = []
    
    tenant_id = ctx.get("tenant_id")
    if tenant_id and tenant_id != "default":
        parts.append(f"t:{tenant_id[:8]}")
    
    agent_id = ctx.get("agent_id")
    if agent_id:
        parts.append(f"a:{agent_id[:8]}")
    
    conversation_id = ctx.get("conversation_id")
    if conversation_id:
        parts.append(f"c:{conversation_id[:8]}")
    
    collection_id = ctx.get("collection_id")
    if collection_id:
        parts.append(f"col:{collection_id[:8]}")
    
    if parts:
        return f"[{' '.join(parts)}] "
    return ""

def add_context_to_log_record():
    """
    Configura el sistema de logging para incluir el contexto en todos los logs.
    Debe llamarse durante la inicialización de la aplicación.
    """
    class ContextFilter(logging.Filter):
        def filter(self, record):
            # Añadir context info a cada log
            ctx = get_full_context()
            record.tenant_id = ctx.get("tenant_id", "default")
            record.agent_id = ctx.get("agent_id", "none")
            record.conversation_id = ctx.get("conversation_id", "none")
            record.collection_id = ctx.get("collection_id", "none")
            
            # Añadir prefijo de contexto si no existe
            if not hasattr(record, 'context_prefix'):
                record.context_prefix = get_context_log_prefix()
            
            return True
    
    # Añadir el filtro al logger raíz para que aplique a todos los loggers
    logging.getLogger().addFilter(ContextFilter())

class ContextAwareLogger:
    """
    Wrapper para logger que incluye automáticamente el contexto en los mensajes.
    
    Ejemplo:
        ```python
        logger = ContextAwareLogger(__name__)
        logger.info("Mensaje con contexto")  # [t:1234 a:5678] Mensaje con contexto
        ```
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _format_message(self, msg: str) -> str:
        return f"{get_context_log_prefix()}{msg}"
    
    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(self._format_message(msg), *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self.logger.info(self._format_message(msg), *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(self._format_message(msg), *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self.logger.error(self._format_message(msg), *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self.logger.critical(self._format_message(msg), *args, **kwargs)
    
    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        self.logger.exception(self._format_message(msg), *args, exc_info=exc_info, **kwargs)

# === UTILIDADES PARA SERIALIZACIÓN DE CONTEXTO ===

def serialize_context() -> str:
    """
    Serializa el contexto actual a JSON para transferirlo entre procesos o servicios.
    
    Returns:
        str: Contexto serializado en formato JSON
    """
    return json.dumps(get_full_context())

def deserialize_context(context_json: str) -> Dict[str, Any]:
    """
    Deserializa un contexto en formato JSON.
    
    Args:
        context_json: Contexto serializado en formato JSON
        
    Returns:
        Dict[str, Any]: Diccionario con el contexto deserializado
    """
    try:
        return json.loads(context_json)
    except:
        logger.warning("Error deserializando contexto JSON", exc_info=True)
        return {}