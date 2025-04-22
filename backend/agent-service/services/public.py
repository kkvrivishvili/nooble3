import logging
from typing import Optional

from common.models import PublicTenantInfo
from common.errors import ServiceError, handle_errors
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.context import with_context
from common.cache import CacheManager
from common.db.rpc import record_public_session

logger = logging.getLogger(__name__)

@handle_errors(error_type="service", log_traceback=True)
async def verify_public_tenant(tenant_slug: str) -> PublicTenantInfo:
    """
    Verifica que un tenant exista y sea público basado en su slug.
    
    Args:
        tenant_slug: Slug del tenant a verificar
        
    Returns:
        PublicTenantInfo: Información del tenant
        
    Raises:
        ServiceError: Si el tenant no existe o no es público
    """
    try:
        supabase = get_supabase_client()
        tenant_data = await supabase.table(get_table_name("tenants")).select("tenant_id, name, public_profile, token_quota, tokens_used").eq("slug", tenant_slug).single().execute()
        
        if not tenant_data.data:
            raise ServiceError(
                message=f"Tenant with slug '{tenant_slug}' not found",
                status_code=404,
                error_code="tenant_not_found"
            )
        
        tenant = tenant_data.data
        
        # Verificar que el tenant tenga perfil público
        if not tenant.get("public_profile", False):
            raise ServiceError(
                message=f"Tenant with slug '{tenant_slug}' does not have a public profile",
                status_code=403,
                error_code="tenant_not_public"
            )
        
        # Verificar cuota de tokens
        token_quota = tenant.get("token_quota", 0)
        tokens_used = tenant.get("tokens_used", 0)
        has_quota = token_quota > tokens_used
        
        return PublicTenantInfo(
            tenant_id=tenant["tenant_id"],
            name=tenant.get("name", "Unknown"),
            token_quota=token_quota,
            tokens_used=tokens_used,
            has_quota=has_quota
        )
    except Exception as e:
        if isinstance(e, ServiceError):
            raise e
        logger.error(f"Error verifying public tenant: {str(e)}")
        raise ServiceError(
            message="Error verifying tenant",
            status_code=500,
            error_code="tenant_verification_error",
            details={"error": str(e)}
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def register_public_session(tenant_id: str, session_id: str, agent_id: str, tokens_used: int = 0) -> str:
    """
    Registra o actualiza una sesión pública y contabiliza tokens utilizados.
    
    Args:
        tenant_id: ID del tenant
        session_id: ID de sesión proporcionado por el cliente o generado
        agent_id: ID del agente utilizado
        tokens_used: Cantidad de tokens utilizados en esta interacción
        
    Returns:
        str: ID de sesión (el proporcionado o uno nuevo si era None)
    """
    # Generar session_id si no se proporcionó
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
    
    try:
        # Llamar a la función de Supabase para registrar sesión
        result = await record_public_session(
            tenant_id=tenant_id,
            session_id=session_id,
            agent_id=agent_id,
            tokens_used=tokens_used
        )
        
        if not result:
            logger.error("Error registering public session: function returned None")
        
        # Cachear información de la sesión para futuras consultas
        try:
            await CacheManager.set(
                data_type="conversation", 
                resource_id=session_id,
                value={
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "is_public": True,
                    "session_id": session_id
                },
                tenant_id=tenant_id,
                agent_id=agent_id,
                ttl=CacheManager.ttl_extended  # Usar propiedad estándar
            )
        except Exception as cache_error:
            logger.warning(f"Error caching session info: {str(cache_error)}")
        
        return session_id
    except Exception as e:
        logger.error(f"Error registering public session: {str(e)}")
        # No lanzamos excepción para no interrumpir el flujo del chat
        return session_id