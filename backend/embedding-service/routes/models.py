"""
Endpoints para gestión de modelos de embeddings.
"""

import logging

from fastapi import APIRouter, Depends

from common.models import TenantInfo, ModelListResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.auth.tenant import TenantInfo, verify_tenant
from common.config.tiers import get_available_embedding_models, get_embedding_model_details

# Importar configuración centralizada
from config.settings import get_settings
from config.constants import EMBEDDING_DIMENSIONS

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

@router.get("/models", response_model=None, response_model_exclude_none=True, response_model_exclude={"ctx"})
@with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para obtener modelos según tier
@handle_errors(error_type="simple", log_traceback=False)
async def list_available_models(
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
) -> ModelListResponse:
    """
    Lista los modelos de embedding disponibles para el tenant según su nivel de suscripción.
    
    Este endpoint proporciona información detallada sobre los modelos de embedding
    disponibles para el tenant según su nivel de suscripción, incluyendo dimensiones,
    capacidades y límites de tokens.
    """
    tenant_id = tenant_info.tenant_id
    subscription_tier = tenant_info.subscription_tier
    
    # Obtener modelos disponibles para este tier usando la función centralizada
    available_models = get_available_embedding_models(subscription_tier, tenant_id=tenant_id)
    
    # Obtener detalles para cada modelo disponible usando la función centralizada
    model_details = {}
    for model_id in available_models:
        details = get_embedding_model_details(model_id)
        if details:  # Solo incluir si hay detalles disponibles
            model_details[model_id] = details
    
    return ModelListResponse(
        message="Modelos de embedding disponibles obtenidos correctamente",
        models=model_details,
        default_model=settings.default_embedding_model,
        subscription_tier=subscription_tier,
        tenant_id=tenant_id
    )