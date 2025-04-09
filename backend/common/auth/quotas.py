"""
Verificación de cuotas y límites para tenants.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Union, Tuple
from fastapi import HTTPException

from ..models.base import TenantInfo
from ..db.supabase import get_supabase_client, get_table_name
from ..cache.manager import CacheManager
from ..config.tiers import get_tier_limits
from ..context.vars import get_current_tenant_id

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
    # Intentar obtener datos de cuota desde caché primero
    tenant_id = tenant_info.tenant_id
    cached_quota_check = await CacheManager.get(
        tenant_id=tenant_id,
        data_type="quota_check",
        resource_id="last_check"
    )
    
    # Si tenemos un resultado reciente en caché (últimos 5 minutos), usarlo
    if cached_quota_check and cached_quota_check.get("timestamp", 0) > time.time() - 300:
        logger.debug(f"Usando verificación de cuotas cacheada para tenant: {tenant_id}")
        quota_status = cached_quota_check.get("status")
        if not quota_status:
            error_detail = cached_quota_check.get("error_detail", "Quota exceeded")
            raise HTTPException(status_code=429, detail=error_detail)
        return True
    
    # Si no hay caché válida, consultamos de Supabase
    try:
        supabase = get_supabase_client()
        
        # Obtener estadísticas de uso actual
        result = await supabase.table(get_table_name("tenant_stats")).select("*") \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if not result.data:
            # Sin datos de uso aún, está dentro de la cuota
            await _update_quota_check_cache(tenant_id, True)
            return True
        
        current_usage = result.data[0]
        
        # Obtener límites según nivel de suscripción
        tier_limits = get_tier_limits(tenant_info.subscription_tier)
        
        # Verificar límite de documentos
        if current_usage.get("document_count", 0) >= tier_limits["max_docs"]:
            logger.warning(f"Límite de documentos excedido para tenant: {tenant_id}")
            error_msg = f"Document limit reached for your subscription tier: {tier_limits['max_docs']}"
            await _update_quota_check_cache(tenant_id, False, error_msg)
            raise HTTPException(status_code=429, detail=error_msg)
        
        # Verificar límite de tokens
        max_tokens = tier_limits.get("max_tokens_per_month")
        if max_tokens and current_usage.get("tokens_used", 0) >= max_tokens:
            logger.warning(f"Límite de tokens excedido para tenant: {tenant_id}")
            error_msg = f"Monthly token limit reached for your subscription tier: {max_tokens}"
            await _update_quota_check_cache(tenant_id, False, error_msg)
            raise HTTPException(status_code=429, detail=error_msg)
        
        # Todo está bien
        await _update_quota_check_cache(tenant_id, True)
        return True
        
    except HTTPException:
        # Re-lanzar excepciones HTTP
        raise
    except Exception as e:
        logger.exception(f"Error verificando cuotas para tenant {tenant_id}: {str(e)}")
        # En caso de error, permitimos continuar para no bloquear operaciones
        return True

async def _update_quota_check_cache(
    tenant_id: str,
    status: bool,
    error_detail: str = None
) -> None:
    """
    Actualiza el estado de verificación de cuotas en caché.
    
    Args:
        tenant_id: ID del tenant
        status: True si está dentro de cuotas, False si excede
        error_detail: Detalle del error si status es False
    """
    try:
        await CacheManager.set(
            tenant_id=tenant_id,
            data_type="quota_check",
            resource_id="last_check",
            data={
                "timestamp": time.time(),
                "status": status,
                "error_detail": error_detail
            },
            ttl=300  # 5 minutos
        )
    except Exception as e:
        logger.warning(f"Error actualizando caché de cuotas: {str(e)}")

async def check_quota_async(tenant_id: str, resource: str) -> bool:
    """Versión async del quota check"""
    try:
        quota = await get_tenant_configurations(tenant_id, scope='quota', scope_id=resource)
        usage = await CacheManager.get(f"quota_usage:{tenant_id}:{resource}")
        return int(usage or 0) < quota.get('limit', 1000)
    except Exception:
        return True  # Fallback permitido

async def track_token_usage(
    tenant_id: Optional[str] = None,
    model: str = "default",
    tokens: int = 0,
    operation: str = "query",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Registra el uso de tokens para un tenant.
    
    Args:
        tenant_id: ID del tenant (si es None, se obtiene del contexto actual)
        model: Nombre del modelo utilizado
        tokens: Número de tokens consumidos
        operation: Tipo de operación (query, embed, chat, etc)
        metadata: Metadatos adicionales de la operación
        
    Returns:
        bool: True si se registró correctamente
    """
    if tokens <= 0:
        return True  # Nada que registrar
        
    # Obtener tenant_id del contexto si no se proporciona
    if not tenant_id:
        tenant_id = get_current_tenant_id()
        if not tenant_id or tenant_id == "default":
            logger.warning("No se pudo registrar uso de tokens: tenant_id no disponible")
            return False
    
    # Preparar datos para registro
    usage_data = {
        "tenant_id": tenant_id,
        "model": model,
        "tokens": tokens,
        "operation": operation,
        "timestamp": time.time()
    }
    
    if metadata:
        usage_data["metadata"] = metadata
    
    try:
        # 1. Actualizar contador en Redis para operaciones de alta frecuencia
        await CacheManager.increment(
            tenant_id=tenant_id,
            data_type="token_usage",
            resource_id=f"{model}:{operation}",
            amount=tokens
        )
        
        # 2. Añadir a la cola de persistencia para almacenar en Supabase
        await CacheManager.rpush(
            queue_name="token_usage_queue",
            data=usage_data
        )
        
        return True
    except Exception as e:
        logger.error(f"Error registrando uso de tokens: {str(e)}")
        return False

async def get_tenant_token_usage(
    tenant_id: str,
    period: str = "month"
) -> Dict[str, Any]:
    """
    Obtiene estadísticas de uso de tokens para un tenant.
    
    Args:
        tenant_id: ID del tenant
        period: Periodo de tiempo (day, week, month)
        
    Returns:
        Dict[str, Any]: Estadísticas de uso de tokens
    """
    try:
        # Determinar timestamp de inicio según periodo
        now = time.time()
        start_time = now
        
        if period == "day":
            start_time = now - 86400  # 24 horas
        elif period == "week":
            start_time = now - 604800  # 7 días
        elif period == "month":
            start_time = now - 2592000  # 30 días
        
        # Consultar a Supabase para obtener uso de tokens
        supabase = get_supabase_client()
        
        result = await supabase.table(get_table_name("token_usage")) \
            .select("model, operation, sum(tokens)") \
            .eq("tenant_id", tenant_id) \
            .gte("created_at", start_time) \
            .group_by("model, operation") \
            .execute()
        
        # Combinar con datos de caché para incluir uso más reciente
        cache_keys = await CacheManager.keys(
            tenant_id=tenant_id,
            data_type="token_usage",
            pattern="*"
        )
        
        cached_usage = {}
        for key in cache_keys:
            model_op = key.split(":")[-1]  # Obtener model:operation
            count = await CacheManager.get(
                tenant_id=tenant_id,
                data_type="token_usage",
                resource_id=model_op
            )
            if count:
                model, operation = model_op.split(":")
                if model not in cached_usage:
                    cached_usage[model] = {}
                cached_usage[model][operation] = count
        
        # Combinar resultados de Supabase con caché
        combined_usage = {}
        
        # Procesar datos de Supabase
        if result.data:
            for item in result.data:
                model = item.get("model", "default")
                operation = item.get("operation", "query")
                tokens = item.get("sum", 0)
                
                if model not in combined_usage:
                    combined_usage[model] = {}
                if operation not in combined_usage[model]:
                    combined_usage[model][operation] = 0
                
                combined_usage[model][operation] += tokens
        
        # Añadir datos de caché
        for model, ops in cached_usage.items():
            if model not in combined_usage:
                combined_usage[model] = {}
                
            for op, count in ops.items():
                if op not in combined_usage[model]:
                    combined_usage[model][op] = 0
                combined_usage[model][op] += count
        
        # Calcular totales
        total_tokens = 0
        for model, ops in combined_usage.items():
            for op, count in ops.items():
                total_tokens += count
        
        return {
            "tenant_id": tenant_id,
            "period": period,
            "total_tokens": total_tokens,
            "usage_by_model": combined_usage
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo uso de tokens: {str(e)}")
        return {
            "tenant_id": tenant_id,
            "period": period,
            "total_tokens": 0,
            "usage_by_model": {},
            "error": str(e)
        }