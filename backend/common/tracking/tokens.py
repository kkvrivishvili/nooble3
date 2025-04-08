"""
Seguimiento de uso de tokens para facturación y cuotas.
"""

import logging
from typing import Dict, Any, Optional

from ..db.rpc import increment_token_usage as rpc_increment_token_usage
from ..cache.counters import increment_token_counter
from ..config.settings import get_settings

logger = logging.getLogger(__name__)

async def track_token_usage(
    tenant_id: str, 
    tokens: int, 
    model: str = None, 
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    token_type: str = "llm"
) -> bool:
    """
    Registra el uso de tokens para un tenant.
    
    En caso de conversaciones públicas con agentes, detecta automáticamente si los tokens
    deben contabilizarse al propietario del agente en lugar del usuario que interactúa.
    
    Args:
        tenant_id: ID del tenant que realiza la solicitud (obtenido del JWT)
        tokens: Número estimado de tokens
        model: Modelo usado (para ajustar el factor de costo)
        agent_id: ID del agente con el que se interactúa (opcional)
                  Si se proporciona, se verifica si los tokens deben contabilizarse al propietario.
        conversation_id: ID de la conversación (opcional, para tracking)
        token_type: Tipo de tokens ('llm' o 'embedding')
        
    Returns:
        bool: True si se registró correctamente
    """
    # Verificar si el tracking está habilitado
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de uso deshabilitado, omitiendo registro de {tokens} tokens para {tenant_id}")
        return True
    
    try:
        # Obtener factores de costo desde la configuración centralizada
        settings = get_settings()
        
        # Usar el factor de costo del modelo o 1.0 por defecto
        cost_factor = settings.model_cost_factors.get(model, 1.0) if model else 1.0
        adjusted_tokens = int(tokens * cost_factor)
        
        # Usar la función helper centralizada para incrementar los tokens en Supabase
        success = await rpc_increment_token_usage(
            tenant_id=tenant_id,
            tokens=adjusted_tokens,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type=token_type
        )
        
        if not success:
            logger.warning(f"No se pudo incrementar el contador de tokens para {token_type} del tenant {tenant_id}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error tracking {token_type} token usage: {str(e)}")
        return False