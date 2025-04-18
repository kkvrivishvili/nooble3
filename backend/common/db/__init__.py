"""
Módulo para acceso a bases de datos y almacenamiento.
"""

from .supabase import (
    get_supabase_client, get_supabase_client_with_token, init_supabase
)

from .tables import (
    get_table_name, get_tenant_vector_store, get_tenant_documents,
    get_tenant_collections
)

from .rpc import (
    create_conversation, add_chat_message, add_chat_history,
    increment_token_usage, increment_document_count, decrement_document_count
)

__all__ = [
    # Cliente Supabase
    'get_supabase_client', 'get_supabase_client_with_token', 'init_supabase',
    
    # Funciones de acceso a tablas
    'get_table_name', 'get_tenant_vector_store', 'get_tenant_documents',
    'get_tenant_collections',
    
    # Funciones RPC
    'create_conversation', 'add_chat_message', 'add_chat_history',
    'increment_token_usage', 'increment_document_count', 'decrement_document_count'
]