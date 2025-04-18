"""
Tracking unificado de tokens, queries y embeddings.
"""
import time
import uuid
import logging
from typing import Dict, Any, List, Optional

from ..cache.manager import CacheManager
from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
from ..db.rpc import increment_token_usage as rpc_increment_token_usage
from ..config.settings import get_settings
from ..config.tiers import get_tier_rate_limit
from ..context.vars import get_current_tenant_id

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
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking deshabilitado, omitiendo {tokens} tokens")
        return True
    if not tenant_id:
        tenant_id = get_current_tenant_id()
        if not tenant_id or tenant_id == "default":
            logger.warning("No se pudo registrar uso de tokens: tenant_id no disponible")
            return False
    try:
        cost_factor = settings.model_cost_factors.get(model, 1.0) if model else 1.0
        adjusted = int(tokens * cost_factor)
        combined = metadata.copy() if metadata else {}
        combined.update({"token_type": token_type, "cost_factor": cost_factor})
        if agent_id:
            combined["agent_id"] = agent_id
        if conversation_id:
            combined["conversation_id"] = conversation_id
        await CacheManager.increment_counter(
            scope="token_usage",
            resource_id=model or "default",
            tokens=adjusted,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            token_type=token_type
        )
        await rpc_increment_token_usage(
            tenant_id=tenant_id,
            tokens=adjusted,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type=token_type
        )
        return True
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

async def track_embedding_usage(
    tenant_id: str,
    texts: List[str],
    model: str,
    cached_count: int = 0,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking embedding deshabilitado para {tenant_id}")
        return True
    supabase = get_supabase_client()
    words = sum(len(t.split()) for t in texts)
    estimated = int(words * 1.3)
    metric_id = str(uuid.uuid4())
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=estimated,
        model=model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type="embedding",
        operation="embedding",
        metadata={"texts": len(texts), "cache_hits": cached_count}
    )
    row = {
        "id": metric_id,
        "tenant_id": tenant_id,
        "date_bucket": time.strftime("%Y-%m-%d"),
        "model": model,
        "total_requests": len(texts),
        "cache_hits": cached_count,
        "tokens_processed": estimated,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    if agent_id:
        row["agent_id"] = agent_id
    if conversation_id:
        row["conversation_id"] = conversation_id
    try:
        await supabase.table(get_table_name("embedding_metrics")).insert(row).execute()
        if agent_id:
            await CacheManager.increment_counter(
                scope="embedding_usage",
                resource_id=model,
                tokens=estimated,
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                token_type="embedding"
            )
        return True
    except Exception as e:
        logger.error(f"Error track_embedding_usage Supabase: {e}")
        return False

async def estimate_prompt_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)

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
            return await track_embedding_usage(
                tenant_id=tenant_id,
                texts=metadata.get("texts", []),
                model=metadata.get("model", "unknown"),
                cached_count=metadata.get("cached_count", 0),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id")
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
