"""
Sistema de gestión de contexto de ejecución para servicios multi-tenant.

Proporciona funcionalidades para gestionar y propagar información de contexto
como tenant_id, agent_id, conversation_id a través de operaciones asíncronas.
"""

from .decorators import with_context, Context, ContextManager
from .vars import (
    get_current_tenant_id, get_current_agent_id,
    get_current_conversation_id, get_current_collection_id,
    set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id,
    get_full_context, reset_context, debug_context
)

from .propagation import (
    extract_context_from_headers, add_context_to_headers, setup_context_from_headers,
    run_public_context
)

from .validator import validate_current_tenant

# Re-exportar asynccontextmanager para conveniencia
from contextlib import asynccontextmanager

# Exportar todos los símbolos importantes
__all__ = [
    # Decoradores y clases principales
    'with_context', 'Context', 'ContextManager',
    
    # Getters de contexto
    'get_current_tenant_id', 'get_current_agent_id',
    'get_current_conversation_id', 'get_current_collection_id',
    
    # Setters de contexto
    'set_current_tenant_id', 'set_current_agent_id',
    'set_current_conversation_id', 'set_current_collection_id',
    
    # Utilidades
    'get_full_context', 'reset_context', 'debug_context',
    
    # Propagación
    'extract_context_from_headers', 'add_context_to_headers', 'setup_context_from_headers',
    'run_public_context',
    
    # Validaciones explícitas
    'validate_current_tenant',
    
    # Para compatibilidad
    'asynccontextmanager'
]