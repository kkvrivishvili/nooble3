import logging
from typing import Optional

from common.models import PublicTenantInfo
from common.errors import ServiceError, handle_errors
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.context import with_context
from common.cache import CacheManager, get_with_cache_aside, serialize_for_cache, track_cache_metrics
from common.db.rpc import record_public_session

logger = logging.getLogger(__name__)

@handle_errors(error_type="service", log_traceback=True)
async def verify_public_tenant(tenant_slug: str) -> PublicTenantInfo:
    """
    Verifica si un tenant existe y es público utilizando el patrón Cache-Aside.
    
    Args:
        tenant_slug: Slug del tenant a verificar
        
    Returns:
        PublicTenantInfo: Información del tenant público
    """
    # Definir el tipo de datos y resource_id
    data_type = "public_tenant_info"
    resource_id = f"tenant_slug:{tenant_slug}"
    
    # Función para buscar en Supabase
    async def fetch_tenant_from_db(resource_id, tenant_id_unused, ctx):
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
    
    # No es necesaria una función de generación para este caso
    async def generate_tenant_info(resource_id, tenant_id_unused, ctx):
        return None
    
    # Implementar el patrón Cache-Aside usando la función centralizada
    # Usamos el tenant_id del sistema ya que aún no conocemos el tenant_id real
    system_tenant_id = "system" 
    
    tenant_info, metrics = await get_with_cache_aside(
        data_type=data_type,
        resource_id=resource_id,
        tenant_id=system_tenant_id,  # Usamos un tenant_id genérico para la caché inicial
        fetch_from_db_func=fetch_tenant_from_db,
        generate_func=generate_tenant_info
        # TTL se determina automáticamente según el tipo de datos
    )
    
    # Una vez que tenemos la información del tenant, actualizamos la caché con el tenant_id correcto
    if tenant_info and tenant_info.tenant_id != system_tenant_id:
        # Creamos una clave adicional con el tenant_id real para facilitar invalidaciones
        serialized_info = serialize_for_cache(tenant_info)
        
        # Registramos la métrica de la operación de caché
        await track_cache_metrics(
            data_type=data_type,
            tenant_id=tenant_info.tenant_id,
            metric_type="cache_set",
            value=1,
            metadata={"operation": "verify_public_tenant"}
        )
        
        await CacheManager.set(
            data_type=data_type,
            resource_id=resource_id,
            value=serialized_info,
            tenant_id=tenant_info.tenant_id
        )
    
    return tenant_info

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
            session_info = {
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "is_public": True,
                "session_id": session_id
            }
            
            # Usamos set_with_metrics en lugar de CacheManager.set directo
            await track_cache_metrics(
                data_type="conversation",
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=session_id,
                metric_type="cache_set",
                value=1,
                metadata={"operation": "register_session"}
            )
            
            # Serializamos antes de almacenar
            serialized_session = serialize_for_cache(session_info)
            
            await CacheManager.set(
                data_type="conversation", 
                resource_id=session_id,
                value=serialized_session,
                tenant_id=tenant_id,
                agent_id=agent_id
                # TTL se determina automáticamente por el tipo de datos "conversation"
            )
        except Exception as cache_error:
            logger.warning(f"Error caching session info: {str(cache_error)}")
        
        return session_id
    except Exception as e:
        logger.error(f"Error registering public session: {str(e)}")
        # No lanzamos excepción para no interrumpir el flujo del chat
        return session_id