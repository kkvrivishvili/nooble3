"""
Validación y gestión de acceso a modelos según suscripción.
"""

from typing import List, Optional
import logging

from ..models.base import TenantInfo
from ..config.tiers import get_tier_limits
from ..errors import ServiceError, ErrorCode

logger = logging.getLogger(__name__)

def get_allowed_models_for_tier(tier: str, model_type: str = "llm") -> list:
    """
    Obtiene los modelos permitidos para un nivel de suscripción.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        model_type: Tipo de modelo ('llm' o 'embedding')
        
    Returns:
        list: Lista de IDs de modelos permitidos
    """
    tier_limits = get_tier_limits(tier)
    
    if model_type == "llm":
        return tier_limits.get("allowed_llm_models", ["gpt-3.5-turbo"])
    else:  # embedding
        return tier_limits.get("allowed_embedding_models", ["text-embedding-3-small"])


async def validate_model_access(tenant_info: TenantInfo, model_id: str, model_type: str = "llm") -> str:
    """
    Valida que un tenant pueda acceder a un modelo.
    
    Args:
        tenant_info: Información del tenant
        model_id: ID del modelo solicitado
        model_type: Tipo de modelo ('llm' o 'embedding')
        
    Returns:
        str: ID del modelo autorizado
        
    Raises:
        ServiceError: Si el modelo solicitado no está permitido para el tier del tenant
    """
    tier = tenant_info.subscription_tier
    allowed_models = get_allowed_models_for_tier(tier, model_type)
    
    # Si el modelo solicitado está permitido, lo devolvemos
    if model_id in allowed_models:
        return model_id
        
    # Crear contexto para el error
    error_context = {
        "tenant_id": tenant_info.tenant_id,
        "subscription_tier": tier,
        "requested_model": model_id,
        "model_type": model_type,
        "allowed_models": allowed_models
    }
    
    # Log de advertencia con contexto enriquecido
    logger.warning(
        f"Modelo {model_id} no permitido para tenant {tenant_info.tenant_id} en tier {tier}",
        extra=error_context
    )
    
    # Lanzar excepción con información detallada
    raise ServiceError(
        message=f"Modelo {model_id} no permitido para su plan de suscripción {tier}",
        error_code=ErrorCode.ACCESS_DENIED.value,
        context=error_context
    )