"""
Seguimiento de uso de embeddings para facturación y métricas.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional

from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
from ..config.settings import get_settings
from .tokens import track_token_usage

logger = logging.getLogger(__name__)

async def track_embedding_usage(
    tenant_id: str, 
    texts: List[str], 
    model: str, 
    cached_count: int = 0,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    """
    Registra el uso de embeddings para un tenant.
    
    En caso de conversaciones públicas con agentes, detecta automáticamente si los tokens
    deben contabilizarse al propietario del agente en lugar del usuario que interactúa.
    
    Args:
        tenant_id: ID del tenant que realiza la solicitud (obtenido del JWT)
        texts: Lista de textos procesados
        model: Modelo de embedding usado
        cached_count: Cantidad de embeddings que se obtuvieron de caché
        agent_id: ID del agente (opcional)
                  Si se proporciona, se verifica si los tokens deben contabilizarse al propietario.
        conversation_id: ID de la conversación (opcional)
        
    Returns:
        bool: True si se registró correctamente
    """
    # Verificar si el tracking está habilitado
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de uso deshabilitado, omitiendo registro de {len(texts)} embeddings para {tenant_id}")
        return True
        
    supabase = get_supabase_client()
    
    try:
        # Calcular tokens aproximados (muy aproximado) para embeddings
        total_words = sum(len(text.split()) for text in texts)
        estimated_tokens = int(total_words * 1.3)  # Factor aproximado
        
        # Generar ID único para la métrica
        metric_id = str(uuid.uuid4())
        
        # Registrar uso de tokens, verificando automáticamente si debe contabilizarse al propietario
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=estimated_tokens,
            model=model,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type="embedding"
        )
        
        # Registrar métricas de embedding específicas en Supabase
        date_bucket = time.strftime("%Y-%m-%d")
        embedding_data = {
            "id": metric_id,
            "tenant_id": tenant_id,
            "date_bucket": date_bucket,
            "model": model,
            "total_requests": len(texts),
            "cache_hits": cached_count,
            "tokens_processed": estimated_tokens,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        # Agregar campos opcionales sólo si tienen valor
        if agent_id:
            embedding_data["agent_id"] = agent_id
            
        if conversation_id:
            embedding_data["conversation_id"] = conversation_id
        
        # Insertar en Supabase
        await supabase.table(get_table_name("embedding_metrics")).insert(embedding_data).execute()
        
        # Cachear métricas en Redis también (diarias por agente y tenant)
        if agent_id:
            try:
                # Actualizar estadísticas del agente en Redis
                from ..cache.counters import increment_token_counter
                
                # Intentar incrementar contadores de embedding en Redis
                await increment_token_counter(
                    tenant_id=tenant_id,  # Aquí usamos el tenant_id original porque track_token_usage ya manejó la redirección
                    tokens=estimated_tokens,
                    token_type="embedding",
                    agent_id=agent_id,
                    conversation_id=conversation_id
                )
            except Exception as redis_error:
                logger.warning(f"Error caching embedding metrics in Redis: {str(redis_error)}")
        
        return True
    except Exception as e:
        logger.error(f"Error tracking embedding usage: {str(e)}")
        return False