"""
Sistema de gestión de contexto de ejecución para servicios multi-tenant.

Proporciona funcionalidades para gestionar y propagar información de contexto
como tenant_id, agent_id, conversation_id a través de operaciones asíncronas.
"""

from .vars import (
    get_current_tenant_id, get_required_tenant_id, get_current_agent_id,
    get_current_conversation_id, get_current_collection_id, get_full_context,
    debug_context, set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id, reset_context
)

from .decorators import (
    Context, ContextTokens, with_context
)

from .propagation import (
    extract_context_from_headers, add_context_to_headers, setup_context_from_headers,
    run_public_context
)

from .memory import ContextManager

from .validator import validate_tenant_id, validate_current_tenant

# Re-exportar asynccontextmanager para conveniencia
from contextlib import asynccontextmanager

# Exportar todos los símbolos importantes
__all__ = [
    # Variables y funciones de acceso
    'get_current_tenant_id', 'get_required_tenant_id', 'get_current_agent_id',
    'get_current_conversation_id', 'get_current_collection_id', 'get_full_context',
    'debug_context', 'set_current_tenant_id', 'set_current_agent_id',
    'set_current_conversation_id', 'set_current_collection_id', 'reset_context',
    
    # Clases y administradores de contexto
    'Context', 'ContextTokens',
    
    # Decoradores
    'with_context',
    
    # Propagación
    'extract_context_from_headers', 'add_context_to_headers', 'setup_context_from_headers',
    'run_public_context',
    
    # Gestión de memoria y contexto
    'ContextManager',
    
    # Validaciones explícitas
    'validate_tenant_id', 'validate_current_tenant',
    
    # Para compatibilidad
    'asynccontextmanager'
]