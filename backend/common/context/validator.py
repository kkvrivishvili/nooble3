from typing import Optional
# Importamos la constante de error desde config
from ..config import ERROR_TENANT_REQUIRED
from .vars import get_current_tenant_id, get_full_context

def validate_tenant_id(tenant_id: Optional[str]) -> str:
    """Valida que el tenant_id no sea None ni 'default'."""
    if not tenant_id or tenant_id == "default":
        context = get_full_context()
        # Importación tardía para evitar ciclo circular
        from common.errors import ServiceError
        raise ServiceError(
            message="Se requiere un tenant válido para esta operación",
            error_code=ERROR_TENANT_REQUIRED,  # Usamos la constante de config
            status_code=403,
            context=context
        )
    return tenant_id

def validate_current_tenant() -> str:
    """Valida y retorna el tenant_id del contexto actual."""
    tenant_id = get_current_tenant_id()
    return validate_tenant_id(tenant_id)
