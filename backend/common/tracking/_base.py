"""
Tracking unificado de tokens, queries y embeddings.
"""
import time
import uuid
import logging
import json
from typing import Dict, Any, List, Optional

from ..cache import CacheManager
from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
from ..db.rpc import increment_token_usage as rpc_increment_token_usage
from ..config import get_settings
from ..config.tiers import get_tier_rate_limit
from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id
from . import attribution

logger = logging.getLogger(__name__)

async def track_token_usage(
    tenant_id: Optional[str] = None,
    tokens: int = 0,
    model: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    token_type: str = "llm",
    operation: str = "query",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    if tokens <= 0:
        return True
    # Obtener configuración con manejo de errores
    try:
        settings = get_settings()
        if not settings.enable_usage_tracking:
            logger.debug(f"Tracking deshabilitado, omitiendo {tokens} tokens")
            return True
    except Exception as config_err:
        logger.debug(f"Error obteniendo configuración, asumiendo tracking habilitado: {str(config_err)}")

    # Obtener tenant_id y otros datos de contexto con manejo de errores
    if not tenant_id:
        try:
            tenant_id = get_current_tenant_id()
        except ImportError:
            pass
        if not tenant_id or tenant_id == "default":
            logger.warning("No se pudo registrar uso de tokens: tenant_id no disponible")
            return False
            
    # Obtener agent_id y conversation_id del contexto si no se proporcionan
    if not agent_id:
        try:
            agent_id = get_current_agent_id()
        except (ImportError, ValueError):
            pass
            
    if not conversation_id:
        try:
            conversation_id = get_current_conversation_id()
        except (ImportError, ValueError):
            pass
            
    try:
        # Determinar el propietario real de los tokens
        try:
            attribution_service = attribution.TokenAttributionService()
            effective_tenant_id = await attribution_service.determine_token_owner(
                requester_tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id
            )
        except Exception as attr_err:
            logger.error(f"Error determinando propietario de tokens: {str(attr_err)}", exc_info=True)
            effective_tenant_id = tenant_id  # Fallback al tenant original
        
        # Calcular factor de coste según el modelo
        cost_factor = 1.0
        if model and hasattr(settings, 'model_cost_factors'):
            cost_factor = settings.model_cost_factors.get(model, 1.0)
        
        # Incrementar contador en Redis
        counter_key = f"{effective_tenant_id}:counter:token_usage:type:{token_type}:model:{model or 'unknown'}"
        redis_success = False
        
        try:
            redis_status = await CacheManager.increment_counter(
                counter_key=counter_key,
                value=tokens,
                metadata={
                    "model": model,
                    "token_type": token_type,
                    "operation": operation,
                    "timestamp": time.time(),
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "collection_id": collection_id
                } if metadata is None else {**metadata, "timestamp": time.time()}
            )
            redis_success = redis_status > 0
        except Exception as redis_err:
            logger.error(f"Error incrementando contador en Redis: {str(redis_err)}", exc_info=True)
            # Continuar con persistencia en BD a pesar del error
        
        # Incrementar contador en la base de datos
        db_success = False
        try:
            db_success = await rpc_increment_token_usage(
                tenant_id=effective_tenant_id,
                tokens=tokens,
                agent_id=agent_id,
                conversation_id=conversation_id,
                token_type=token_type
            )
        except Exception as db_err:
            logger.error(f"Error incrementando contador en BD: {str(db_err)}", exc_info=True)
            
            # Solo marcar para reconciliación si Redis funcionó pero la BD falló
            if redis_success:
                try:
                    record = {
                        "tenant_id": effective_tenant_id,
                        "tokens": tokens,
                        "model": model,
                        "agent_id": agent_id,
                        "conversation_id": conversation_id,
                        "token_type": token_type,
                        "timestamp": time.time(),
                        "retry_count": 0
                    }
                    
                    await CacheManager.add_to_set(
                        set_name="pending_token_reconciliation",
                        tenant_id="system",  # Conjunto a nivel de sistema
                        value=json.dumps(record)
                    )
                    logger.info(f"Tokens marcados para reconciliación futura: {tokens} para {effective_tenant_id}")
                except Exception as rec_err:
                    logger.error(f"Error crítico marcando tokens para reconciliación: {str(rec_err)}", exc_info=True)

        # Registrar valores finales para análisis
        combined_meta = metadata.copy() if metadata else {}
        combined_meta.update({
            "token_type": token_type, 
            "cost_factor": cost_factor,
            "original_tenant_id": tenant_id,
            "effective_tenant_id": effective_tenant_id,
            "redis_success": redis_success,
            "db_success": db_success,
            "total_tokens": tokens
        })
        if agent_id:
            combined_meta["agent_id"] = agent_id
        if conversation_id:
            combined_meta["conversation_id"] = conversation_id
        if model:
            combined_meta["model"] = model

        # Registrar métricas para monitoreo
        logger.info(
            f"Token usage tracked: {tokens} tokens for tenant {effective_tenant_id}",
            extra={"tracking_meta": combined_meta}
        )

        return redis_success or db_success  # Éxito si al menos uno funcionó
    except Exception as e:
        logger.error(f"Error track_token_usage: {e}", extra={"tenant_id": tenant_id})
        return False

async def track_query(
    tenant_id: str,
    operation_type: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    await get_tier_rate_limit(tenant_id, tier=None, service_name='query-service')
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de consultas deshabilitado para {tenant_id}")
        return True
    supabase = get_supabase_client()
    total = tokens_in + tokens_out
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=total,
        model=model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type="llm",
        operation=operation_type,
        metadata={"tokens_in": tokens_in, "tokens_out": tokens_out, "operation_type": operation_type, "model": model}
    )
    data = {
        "tenant_id": tenant_id,
        "operation_type": operation_type,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_tokens": total,
        "timestamp": int(time.time())
    }
    if agent_id:
        data["agent_id"] = agent_id
    if conversation_id:
        data["conversation_id"] = conversation_id
    try:
        await supabase.table(get_table_name("query_logs")).insert(data).execute()
        return True
    except Exception as e:
        logger.error(f"Error track_query Supabase: {e}")
        return False

async def estimate_prompt_tokens(text: str) -> int:
    """
    Estima la cantidad de tokens en un texto.
    
    Args:
        text: Texto a analizar
        
    Returns:
        int: Cantidad estimada de tokens
    """
    return int(len(text.split()) * 1.3)

async def track_usage(
    tenant_id: str,
    operation: str,
    metadata: Dict[str, Any]
) -> bool:
    try:
        if operation == "query":
            return await track_query(
                tenant_id=tenant_id,
                operation_type=metadata.get("operation_type", "query"),
                model=metadata.get("model", "unknown"),
                tokens_in=metadata.get("tokens_in", 0),
                tokens_out=metadata.get("tokens_out", 0),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id")
            )
        elif operation == "embedding":
            return await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("tokens", 0),
                model=metadata.get("model"),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id"),
                collection_id=metadata.get("collection_id"),
                token_type="embedding"
            )
        elif operation == "tokens":
            return await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("tokens", 0),
                model=metadata.get("model"),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id"),
                collection_id=metadata.get("collection_id"),
                token_type=metadata.get("token_type", "llm")
            )
        else:
            logger.warning(f"Tipo de operación desconocido: {operation}")
            return False
    except Exception as e:
        logger.error(f"Error track_usage: {e}", extra={"tenant_id": tenant_id})
        return False
