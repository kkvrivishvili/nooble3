"""
Funciones para autenticación, autorización y gestión de permisos.
"""

from .tenant import verify_tenant, is_tenant_active, TenantInfo
from .quotas import check_tenant_quotas
from .permissions import get_auth_info, get_auth_supabase_client, with_auth_client, AISchemaAccess
from .models import validate_model_access, get_allowed_models_for_tier

__all__ = [
    'verify_tenant',
    'is_tenant_active',
    'TenantInfo',
    'check_tenant_quotas',
    'get_auth_info',
    'get_auth_supabase_client',
    'with_auth_client',
    'AISchemaAccess',
    'validate_model_access',
    'get_allowed_models_for_tier'
]