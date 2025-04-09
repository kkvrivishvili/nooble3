"""
Funciones para rate limiting centralizado.
"""

import time
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.base import TenantInfo
# Eliminamos la importación directa a Redis ya que usaremos sólo CacheManager
from ..cache.manager import CacheManager
# Actualizamos las importaciones para evitar ciclos
from ..config.tiers import get_tier_rate_limit
from ..config.settings import get_tenant_rate_limit

logger = logging.getLogger(__name__)

async def check_rate_limit_async(bucket: str) -> bool:
    """Versión async del rate limiter"""
    current = await CacheManager.get(f"rate_limit:{bucket}")
    limit = await get_tenant_configurations(
        tenant_id=get_current_tenant_id(), 
        scope='rate_limit', 
        scope_id=bucket
    )
    return int(current or 0) < limit.get('max_requests', 100)

async def apply_rate_limit(tenant_id: str, tier: str, limit_key: str = "api") -> bool:
    """
    Aplica rate limiting para un tenant específico.
    
    Args:
        tenant_id: ID del tenant
        tier: Nivel de suscripción ('free', 'pro', 'business')
        limit_key: Clave del limitador (para diferenciar APIs)
        
    Returns:
        bool: True si está dentro del límite, False si lo excede
        
    Raises:
        HTTPException: Si se excede el límite de tasa
    """
    # Determinar el servicio para obtener configuraciones específicas
    service_name = None
    if limit_key in ["agent", "query", "embedding", "chat"]:
        service_name = limit_key
    
    # Obtener límite según configuraciones específicas del tenant
    rate_limit = get_tenant_rate_limit(tenant_id, tier, service_name)
    
    # Generar clave única para este tenant/servicio
    limit_period = 60  # 1 minuto por defecto
    
    try:
        # Obtener contador actual usando CacheManager
        current_count = await CacheManager.get(
            tenant_id=tenant_id,
            data_type="rate_limit",
            resource_id=f"{limit_key}:count"
        )
        
        current_count = int(current_count) if current_count is not None else 0
        
        # Verificar si excede el límite
        if current_count >= rate_limit:
            # Obtener tiempo restante para reset
            ttl = await CacheManager.ttl(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            
            logger.warning(f"Rate limit excedido para tenant {tenant_id}: {current_count}/{rate_limit}")
            raise HTTPException(
                status_code=429,
                detail={
                    "message": "Has excedido el límite de solicitudes por minuto",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "current": current_count,
                    "limit": rate_limit,
                    "reset_in_seconds": ttl if ttl > 0 else limit_period,
                    "service": service_name or "general"
                }
            )
        
        # Actualizar contador
        if current_count == 0:
            # Primera solicitud en este periodo
            await CacheManager.set(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count",
                data=1,
                ttl=limit_period
            )
        else:
            # Incrementar contador existente
            await CacheManager.increment(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count",
                amount=1
            )
        
        return True
        
    except HTTPException:
        # Re-lanzar excepción HTTP
        raise
    except Exception as e:
        logger.error(f"Error en rate limiting: {str(e)}")
        # Si hay error, permitir la solicitud para no bloquear el servicio
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware para aplicar rate limiting a todas las peticiones.
    """
    
    async def dispatch(self, request: Request, call_next):
        tenant_info = request.scope.get("tenant_info")
        
        # Omitir rate limiting si no hay información de tenant
        if not tenant_info or not isinstance(tenant_info, TenantInfo):
            return await call_next(request)
        
        # Omitir rate limiting para health checks y rutas de monitoreo
        excluded_paths = ["/health", "/metrics", "/status"]
        for path in excluded_paths:
            if request.url.path.endswith(path):
                return await call_next(request)
        
        # Determinar clave del limitador según el endpoint
        service_key = self._determine_service_key(request.url.path)
        
        try:
            # Aplicar limitación de tasa usando servicio específico para el tenant
            await apply_rate_limit(
                tenant_id=tenant_info.tenant_id,
                tier=tenant_info.subscription_tier,
                limit_key=service_key
            )
            
            # Procesar la solicitud normalmente
            response = await call_next(request)
            
            # Añadir headers de rate limit a la respuesta si es posible
            if hasattr(response, "headers"):
                await self._add_rate_limit_headers(
                    response=response,
                    tenant_id=tenant_info.tenant_id,
                    tier=tenant_info.subscription_tier,
                    limit_key=service_key
                )
                
            return response
            
        except HTTPException as e:
            # Re-lanzar excepción desde apply_rate_limit
            raise e
        except Exception as e:
            logger.error(f"Error en rate limiting middleware: {str(e)}")
            # Continuar con la solicitud en caso de error
            return await call_next(request)
    
    def _determine_service_key(self, path: str) -> str:
        """Determina la clave de servicio basada en la ruta de la solicitud"""
        if "/agent" in path:
            return "agent"
        elif "/query" in path or "/search" in path:
            return "query"
        elif "/embedding" in path or "/embed" in path:
            return "embedding"
        elif "/chat" in path:
            return "chat"
        else:
            return "api"  # Valor por defecto
    
    async def _add_rate_limit_headers(
        self, 
        response,
        tenant_id: str,
        tier: str,
        limit_key: str
    ) -> None:
        """Añade headers de rate limit a la respuesta"""
        try:
            # Obtener límite y uso actual
            rate_limit = get_tenant_rate_limit(tenant_id, tier, limit_key)
            current_count = await CacheManager.get(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            
            current_count = int(current_count) if current_count is not None else 0
            
            # Obtener TTL
            ttl = await CacheManager.ttl(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            
            # Añadir headers estándar de rate limit
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit - current_count))
            response.headers["X-RateLimit-Reset"] = str(ttl if ttl > 0 else 60)
            
        except Exception as e:
            logger.warning(f"Error añadiendo headers de rate limit: {str(e)}")


# Función para registrar el middleware
def setup_rate_limiting(app):
    """
    Configura el middleware de rate limiting para la aplicación.
    
    Args:
        app: Aplicación FastAPI
    """
    app.add_middleware(RateLimitMiddleware)
    logger.info("Rate limiting middleware configurado")