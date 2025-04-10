"""
Validación y gestión de acceso a modelos según suscripción.
"""

from typing import List, Optional
import logging

from ..models.base import TenantInfo
from ..errors import ServiceError, ErrorCode
from ..config.tiers import get_available_llm_models, get_available_embedding_models

logger = logging.getLogger(__name__)


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
    
    # Obtenemos los modelos permitidos directamente de las funciones en tiers.py
    if model_type == "llm":
        allowed_models = get_available_llm_models(tier)
    elif model_type == "embedding":
        allowed_models = get_available_embedding_models(tier)
    else:
        logger.warning(f"Tipo de modelo desconocido: {model_type}, usando LLM por defecto")
        allowed_models = get_available_llm_models(tier)
    
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
    
    logger.warning(
        f"Modelo {model_id} no permitido para tenant {tenant_info.tenant_id} en tier {tier}",
        extra=error_context
    )
    
    # Si hay modelos permitidos, usamos el primero como alternativa
    if allowed_models:
        default_model = allowed_models[0]
        logger.info(
            f"Usando modelo alternativo {default_model} en lugar de {model_id} para tier {tier}",
            extra=error_context
        )
        return default_model
    
    # Lanzar excepción con información detallada
    raise ServiceError(
        message=f"Modelo {model_id} no permitido para su plan de suscripción {tier}",
        error_code=ErrorCode.ACCESS_DENIED.value,
        context=error_context
    )