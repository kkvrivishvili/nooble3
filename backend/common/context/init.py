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
    Context, ContextTokens, TenantContext, AgentContext, FullContext,
    with_context, with_tenant_context, with_agent_context, with_full_context
)

from .propagation import (
    extract_context_from_headers, add_context_to_headers, setup_context_from_headers,
    run_public_context, run_with_tenant, run_with_agent_context, run_with_full_context
)

from .memory import ContextManager

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
    'Context', 'ContextTokens', 'TenantContext', 'AgentContext', 'FullContext',
    
    # Decoradores
    'with_context', 'with_tenant_context', 'with_agent_context', 'with_full_context',
    
    # Propagación
    'extract_context_from_headers', 'add_context_to_headers', 'setup_context_from_headers',
    'run_public_context', 'run_with_tenant', 'run_with_agent_context', 'run_with_full_context',
    
    # Gestión de memoria y contexto
    'ContextManager',
    
    # Para compatibilidad
    'asynccontextmanager'
]