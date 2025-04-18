"""
Endpoints para gestión de modelos de embeddings.
"""

import logging

from fastapi import APIRouter, Depends

from common.models import TenantInfo, ModelListResponse
from common.errors import handle_service_error_simple
from common.context import with_context
from common.auth import verify_tenant
from common.config import get_settings

from config import get_available_models_for_tier

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

@router.get("/models", response_model=ModelListResponse)
@with_context(tenant=True)
@handle_service_error_simple
async def list_available_models(
    tenant_info: TenantInfo = Depends(verify_tenant)
) -> ModelListResponse:
    """
    Lista los modelos de embedding disponibles para el tenant según su nivel de suscripción.
    
    Este endpoint proporciona información detallada sobre los modelos de embedding
    disponibles para el tenant según su nivel de suscripción, incluyendo dimensiones,
    capacidades y límites de tokens.
    """
    tenant_id = tenant_info.tenant_id
    subscription_tier = tenant_info.subscription_tier
    
    # Obtener modelos disponibles para este tier
    available_models = get_available_models_for_tier(subscription_tier)
    
    return ModelListResponse(
        success=True,
        message="Modelos de embedding disponibles obtenidos correctamente",
        models=available_models,
        default_model=settings.default_embedding_model,
        subscription_tier=subscription_tier,
        tenant_id=tenant_id
    )