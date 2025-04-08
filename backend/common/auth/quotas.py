"""
Verificación de cuotas y límites para tenants.
"""

import logging
from fastapi import HTTPException

from ..models.base import TenantInfo
from ..db.supabase import get_supabase_client, get_table_name
from ..config.tiers import get_tier_limits

logger = logging.getLogger(__name__)

async def check_tenant_quotas(tenant_info: TenantInfo) -> bool:
    """
    Verifica que un tenant no haya excedido sus cuotas.
    
    Args:
        tenant_info: Información del tenant
        
    Returns:
        bool: True si el tenant está dentro de sus cuotas
        
    Raises:
        HTTPException: Si el tenant ha excedido alguna de sus cuotas
    """
    supabase = get_supabase_client()
    
    # Obtener estadísticas de uso actual
    usage_data = supabase.table(get_table_name("tenant_stats")).select("*") \
        .eq("tenant_id", tenant_info.tenant_id) \
        .execute()
    
    if not usage_data.data:
        # Sin datos de uso aún, está dentro de la cuota
        return True
    
    current_usage = usage_data.data[0]
    
    # Obtener límites según nivel de suscripción
    tier_limits = get_tier_limits(tenant_info.subscription_tier)
    
    # Verificar límite de documentos
    if current_usage.get("document_count", 0) >= tier_limits["max_docs"]:
        logger.warning(f"Límite de documentos excedido para tenant: {tenant_info.tenant_id}")
        raise HTTPException(
            status_code=429, 
            detail=f"Document limit reached for your subscription tier: {tier_limits['max_docs']}"
        )
    
    # Verificar límite de tokens
    max_tokens = tier_limits.get("max_tokens_per_month")
    if max_tokens and current_usage.get("tokens_used", 0) >= max_tokens:
        logger.warning(f"Límite de tokens excedido para tenant: {tenant_info.tenant_id}")
        raise HTTPException(
            status_code=429, 
            detail=f"Monthly token limit reached for your subscription tier: {max_tokens}"
        )
    
    return True