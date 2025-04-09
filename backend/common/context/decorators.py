"""
Decoradores y clases para gestionar el contexto en diferentes ámbitos de ejecución.

Proporciona decoradores para funciones asíncronas y administradores de contexto
para bloques de código que necesitan mantener información de contexto.
"""

import logging
import contextvars
from typing import Dict, Any, List, Optional, TypeVar, Callable, Awaitable, NamedTuple
import asyncio

from .vars import (
    get_current_tenant_id, get_current_agent_id, get_current_conversation_id, 
    get_current_collection_id, set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id, reset_context
)

logger = logging.getLogger(__name__)

# Tipo para funciones asíncronas para decoradores
T = TypeVar('T')
AsyncFunc = Callable[..., Awaitable[T]]

# === CLASES PARA GESTIÓN DE CONTEXTO ===

class ContextTokens(NamedTuple):
    """
    Contenedor para tokens de contexto que facilita su gestión.
    """
    tenant_token: Optional[contextvars.Token] = None
    agent_token: Optional[contextvars.Token] = None
    conversation_token: Optional[contextvars.Token] = None
    collection_token: Optional[contextvars.Token] = None

class Context:
    """
    Administrador de contexto unificado para establecer cualquier combinación de
    valores de contexto durante la ejecución de un bloque de código.
    
    Ejemplo:
        ```python
        with Context(tenant_id="t123", agent_id="a456", conversation_id="c789"):
            # Código que ejecutará con estos valores de contexto
            result = await function_that_needs_context()
        ```
    """
    
    def __init__(
        self, 
        tenant_id: Optional[str] = None, 
        agent_id: Optional[str] = None, 
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.collection_id = collection_id
        self.tokens = ContextTokens()
    
    def __enter__(self):
        # Guardar tokens para restaurar después
        tokens = []
        
        if self.tenant_id is not None:
            tokens.append((set_current_tenant_id(self.tenant_id), "tenant_id"))
        
        if self.agent_id is not None:
            tokens.append((set_current_agent_id(self.agent_id), "agent_id"))
        
        if self.conversation_id is not None:
            tokens.append((set_current_conversation_id(self.conversation_id), "conversation_id"))
        
        if self.collection_id is not None:
            tokens.append((set_current_collection_id(self.collection_id), "collection_id"))
        
        # Guardar todos los tokens para restaurar en el exit
        self.tokens_with_names = tokens
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restaurar contexto previo (en orden inverso para mejor encadenamiento)
        for token, name in reversed(self.tokens_with_names):
            reset_context(token, name)

    async def __aenter__(self):
        """
        Entra en el contexto asincrónico y establece los valores especificados.
        """
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Sale del contexto asincrónico y restaura los valores anteriores.
        """
        self.__exit__(exc_type, exc_val, exc_tb)

# === DECORADORES PARA FUNCIONES ASÍNCRONAS ===

def with_context(
    tenant: bool = True,
    agent: bool = False,
    conversation: bool = False,
    collection: bool = False
) -> Callable[[AsyncFunc], AsyncFunc]:
    """
    Decorador configurable para propagar el contexto a funciones asíncronas.
    
    Este decorador único reemplaza los múltiples decoradores específicos,
    permitiendo elegir exactamente qué partes del contexto se propagan.
    
    Args:
        tenant: Si debe propagar tenant_id
        agent: Si debe propagar agent_id
        conversation: Si debe propagar conversation_id
        collection: Si debe propagar collection_id
        
    Returns:
        Decorador configurado
    
    Ejemplo:
        ```python
        @with_context(tenant=True, agent=True)
        async def my_function():
            # tenant_id y agent_id estarán disponibles
            pass
        ```
    """
    def decorator(func: AsyncFunc) -> AsyncFunc:
        async def wrapper(*args, **kwargs) -> Any:
            # Extrae parámetros de contexto a propagar
            context_params = {}
            
            if tenant:
                context_params["tenant_id"] = get_current_tenant_id()
            if agent:
                context_params["agent_id"] = get_current_agent_id()
            if conversation:
                context_params["conversation_id"] = get_current_conversation_id()
            if collection:
                context_params["collection_id"] = get_current_collection_id()
            
            # Ejecuta la función con el contexto
            ctx = Context(**context_params)
            async with ctx:
                return await func(*args, **kwargs)
        return wrapper
    return decorator

# Nota: Los decoradores específicos (with_tenant_context, with_agent_context, with_full_context)
# han sido eliminados. Usar with_context con los parámetros correspondientes.