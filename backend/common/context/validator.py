from typing import Optional
from common.errors import ServiceError, ErrorCode
from .vars import get_current_tenant_id, get_full_context

def validate_tenant_id(tenant_id: Optional[str]) -> str:
    """Valida que el tenant_id no sea None ni 'default'."""
    if not tenant_id or tenant_id == "default":
        context = get_full_context()
        raise ServiceError(
            message="Se requiere un tenant válido para esta operación",
            error_code=ErrorCode.TENANT_REQUIRED,
            status_code=403,
            context=context
        )
    return tenant_id

def validate_current_tenant() -> str:
    """Valida y retorna el tenant_id del contexto actual."""
    tenant_id = get_current_tenant_id()
    return validate_tenant_id(tenant_id)
