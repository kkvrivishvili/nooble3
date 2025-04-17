"""
Funciones para verificación de tenant y acceso.
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException
import logging
from os import getenv

from ..models.base import TenantInfo
from ..db.tables import get_table_name
from ..db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

async def verify_tenant(tenant_id: str) -> TenantInfo:
    """
    Verifica que un tenant exista y tenga una suscripción activa.
    
    Args:
        tenant_id: ID del tenant a verificar
        
    Returns:
        TenantInfo: Información del tenant
        
    Raises:
        HTTPException: Si el tenant no existe o no tiene suscripción activa
    """
    logger.debug(f"Verificando tenant: {tenant_id}")
    supabase = get_supabase_client()
    
    # Verificar que el tenant existe
    tenant_data = supabase.table(get_table_name("tenants")).select("*").eq("tenant_id", tenant_id).execute()
    
    if not tenant_data.data:
        logger.warning(f"Tenant no encontrado: {tenant_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Tenant no encontrado: {tenant_id}"
        )
    
    # Verificar que tiene una suscripción activa
    subscription_data = supabase.table(get_table_name("tenant_subscriptions")).select("*") \
        .eq("tenant_id", tenant_id) \
        .eq("is_active", True) \
        .execute()
    
    if not subscription_data.data:
        logger.warning(f"Sin suscripción activa para tenant: {tenant_id}")
        raise HTTPException(status_code=403, detail=f"No active subscription for tenant {tenant_id}")
    
    subscription = subscription_data.data[0]
    
    return TenantInfo(
        tenant_id=tenant_id,
        subscription_tier=subscription["subscription_tier"]
    )


async def is_tenant_active(tenant_id: str) -> bool:
    """
    Verifica si un tenant está activo, devolviendo un booleano en lugar de lanzar excepciones.
    
    Args:
        tenant_id: ID del tenant a verificar
        
    Returns:
        bool: True si el tenant existe y tiene una suscripción activa, False en caso contrario
    """
    try:
        await verify_tenant(tenant_id)
        return True
    except HTTPException:
        return False
    except Exception as e:
        logger.error(f"Error verificando tenant {tenant_id}: {e}")
        return False


def is_tenant_active_sync(tenant_id: str) -> bool:
    """Wrapper síncrono para compatibilidad"""
    import asyncio
    return asyncio.run(is_tenant_active(tenant_id))