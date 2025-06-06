"""
Validador de tenants y rate limiting.
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from fastapi import HTTPException
from common.redis_pool import get_redis_client

logger = logging.getLogger(__name__)

class TenantValidator:
    """Validador y rate limiter para tenants."""
    
    def __init__(self):
        self.tenant_cache: Dict[str, dict] = {}
        self.cache_ttl = 300  # 5 minutos
    
    async def validate_tenant(self, tenant_id: str) -> bool:
        """
        Valida que un tenant exista y esté activo.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            bool: True si es válido
            
        Raises:
            HTTPException: Si el tenant no es válido
        """
        # Verificar caché local
        if tenant_id in self.tenant_cache:
            cached = self.tenant_cache[tenant_id]
            if time.time() - cached["timestamp"] < self.cache_ttl:
                if not cached["valid"]:
                    raise HTTPException(status_code=403, detail="Tenant inválido o inactivo")
                return True
        
        # Verificar en Redis
        redis_client = await get_redis_client()
        tenant_key = f"tenant:info:{tenant_id}"
        
        tenant_info = await redis_client.get(tenant_key)
        
        if not tenant_info:
            # Simular validación (en producción consultaría la DB)
            # Por ahora, aceptar cualquier tenant con formato UUID válido
            import re
            uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            is_valid = bool(re.match(uuid_pattern, tenant_id.lower()))
            
            # Cachear resultado
            self.tenant_cache[tenant_id] = {
                "valid": is_valid,
                "timestamp": time.time()
            }
            
            if not is_valid:
                raise HTTPException(status_code=403, detail="Tenant ID inválido")
                
        return True
    
    async def check_rate_limit(
        self,
        tenant_id: str,
        action: str,
        limit: int = 100,
        window: int = 60
    ) -> Tuple[bool, Optional[int]]:
        """
        Verifica rate limit para un tenant.
        
        Args:
            tenant_id: ID del tenant
            action: Tipo de acción
            limit: Límite de requests
            window: Ventana de tiempo en segundos
            
        Returns:
            Tuple[bool, Optional[int]]: (permitido, requests_restantes)
        """
        redis_client = await get_redis_client()
        
        # Clave para rate limiting
        rate_key = f"rate_limit:{tenant_id}:{action}"
        current_time = int(time.time())
        window_start = current_time - window
        
        # Usar sorted set para ventana deslizante
        pipe = redis_client.pipeline()
        
        # Eliminar entradas viejas
        pipe.zremrangebyscore(rate_key, 0, window_start)
        
        # Contar requests en la ventana
        pipe.zcard(rate_key)
        
        # Agregar request actual
        pipe.zadd(rate_key, {str(current_time): current_time})
        
        # TTL para limpiar automáticamente
        pipe.expire(rate_key, window + 1)
        
        results = await pipe.execute()
        request_count = results[1]
        
        if request_count >= limit:
            return False, 0
        
        return True, limit - request_count - 1
    
    async def track_usage(
        self,
        tenant_id: str,
        action: str,
        tokens: int = 0,
        cost: float = 0.0
    ):
        """
        Registra uso para billing.
        
        Args:
            tenant_id: ID del tenant
            action: Tipo de acción  
            tokens: Tokens consumidos
            cost: Costo estimado
        """
        redis_client = await get_redis_client()
        
        # Clave de uso diario
        today = datetime.now().strftime("%Y-%m-%d")
        usage_key = f"usage:{tenant_id}:{today}"
        
        # Incrementar contadores
        pipe = redis_client.pipeline()
        pipe.hincrby(usage_key, f"{action}_count", 1)
        pipe.hincrbyfloat(usage_key, f"{action}_tokens", tokens)
        pipe.hincrbyfloat(usage_key, f"{action}_cost", cost)
        pipe.hincrbyfloat(usage_key, "total_tokens", tokens)
        pipe.hincrbyfloat(usage_key, "total_cost", cost)
        
        # TTL de 90 días
        pipe.expire(usage_key, 7776000)
        
        await pipe.execute()
        
        logger.info(f"Uso registrado para {tenant_id}: {action} - {tokens} tokens")
    
    async def get_usage_summary(
        self,
        tenant_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Obtiene resumen de uso.
        
        Args:
            tenant_id: ID del tenant
            days: Días a consultar
            
        Returns:
            Dict con resumen de uso
        """
        redis_client = await get_redis_client()
        summary = {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_tokens": 0,
            "total_cost": 0.0,
            "by_action": {},
            "by_day": []
        }
        
        # Iterar por días
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            usage_key = f"usage:{tenant_id}:{date}"
            
            daily_usage = await redis_client.hgetall(usage_key)
            if daily_usage:
                summary["by_day"].append({
                    "date": date,
                    "usage": daily_usage
                })
                
                # Sumar totales
                summary["total_tokens"] += float(daily_usage.get("total_tokens", 0))
                summary["total_cost"] += float(daily_usage.get("total_cost", 0))
        
        return summary

# Instancia global
tenant_validator = TenantValidator()