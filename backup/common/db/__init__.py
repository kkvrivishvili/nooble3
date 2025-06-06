"""
Módulo para acceso a bases de datos y almacenamiento.
"""

from .supabase import (
    get_supabase_client,
    get_supabase_client_with_token,
    init_supabase,
    get_tenant_configurations,
    set_tenant_configuration,
    get_effective_configurations,
)

from .tables import (
    get_table_name,
    get_table_description,
    get_tenant_vector_store,
    get_tenant_documents,
    get_tenant_collections,
)

from .rpc import (
    create_conversation,
    add_chat_message,
    add_chat_history,
    increment_document_count,
    decrement_document_count,
)

from .storage import (
    get_storage_client,
    upload_to_storage,
    get_file_from_storage,
    update_document_counters,
)

__all__ = [
    # supabase
    "get_supabase_client",
    "get_supabase_client_with_token",
    "init_supabase",
    "get_tenant_configurations",
    "set_tenant_configuration",
    "get_effective_configurations",
    # tables
    "get_table_name",
    "get_table_description",
    "get_tenant_vector_store",
    "get_tenant_documents",
    "get_tenant_collections",
    # rpc
    "create_conversation",
    "add_chat_message",
    "add_chat_history",
    "increment_document_count",
    "decrement_document_count",
    # storage
    "get_storage_client",
    "upload_to_storage",
    "get_file_from_storage",
    "update_document_counters",
]