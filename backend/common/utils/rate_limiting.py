"""
Funciones para rate limiting centralizado.
"""

import time
import logging
import asyncio
import traceback
from typing import Optional, Dict, Any, Tuple
from fastapi import Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware

from ..models.base import TenantInfo
# Eliminamos la importación directa a Redis ya que usaremos sólo CacheManager
from ..cache.manager import CacheManager
# Actualizamos las importaciones para evitar ciclos
from ..config.tiers import get_tier_rate_limit
from ..config.settings import get_settings
from ..context.vars import get_current_tenant_id, get_full_context
from ..auth.tenant import verify_tenant
from ..errors.exceptions import ServiceError, ErrorCode, RateLimitExceeded
from ..errors.handlers import handle_errors

logger = logging.getLogger(__name__)

async def check_rate_limit_async(bucket: str) -> bool:
    """
    Versión async del rate limiter.
    
    Args:
        bucket: Identificador único del bucket de rate limiting
        
    Returns:
        bool: True si está dentro del límite, False si lo excede
        
    Raises:
        ServiceError: Si hay un error al verificar el límite
    """
    error_context = {
        "function": "check_rate_limit_async",
        "bucket": bucket
    }
    error_context.update(get_full_context())
    
    try:
        tenant_id = get_current_tenant_id()
        error_context["tenant_id"] = tenant_id
        
        current = await CacheManager.get(
            tenant_id=tenant_id,
            data_type="rate_limit",
            resource_id=f"{tenant_id}:bucket:{bucket}"
        )
        
        # Obtener límite de tasa usando configuración centralizada de tiers
        tenant_info = await verify_tenant(tenant_id)
        max_requests = await get_tier_rate_limit(
            tenant_id, tenant_info.subscription_tier, bucket
        )
        
        error_context["max_requests"] = max_requests
        error_context["current_requests"] = int(current or 0)
        
        return int(current or 0) < max_requests
    except Exception as e:
        error_message = f"Error al verificar rate limit para bucket {bucket}: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise ServiceError(
            message=error_message,
            error_code=ErrorCode.RATE_LIMIT_ERROR.value,
            context=error_context
        )

@handle_errors()
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
        RateLimitExceeded: Si se excede el límite de tasa
        ServiceError: Si hay un error al aplicar el límite
    """
    error_context = {
        "function": "apply_rate_limit",
        "tenant_id": tenant_id,
        "tier": tier,
        "limit_key": limit_key
    }
    error_context.update(get_full_context())
    
    try:
        # Determinar el servicio para obtener configuraciones específicas
        service_name = None
        if limit_key in ["agent", "query", "embedding", "chat"]:
            service_name = limit_key
        
        error_context["service_name"] = service_name
        
        # Obtener configuración desde settings
        settings = await get_settings()
        
        # Obtener límite según configuraciones específicas del tenant usando la función estandarizada
        try:
            rate_limit = await get_tier_rate_limit(tenant_id, tier, service_name)
        except Exception as config_error:
            logger.warning(f"Error al obtener rate limit para {tenant_id}: {str(config_error)}", 
                          extra=error_context)
            # Usar valor predeterminado conservador si hay error
            rate_limit = 60  # 60 req/min por defecto
        
        error_context["rate_limit"] = rate_limit
        
        # Generar clave única para este tenant/servicio
        limit_period = getattr(settings, "rate_limit_window_seconds", 60)  # 1 minuto por defecto
        error_context["limit_period"] = limit_period
        
        # Obtener contador actual usando CacheManager
        try:
            current_count = await CacheManager.get(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            
            current_count = int(current_count) if current_count is not None else 0
            error_context["current_count"] = current_count
            
            # Verificar si excede el límite
            if current_count >= rate_limit:
                # Obtener tiempo restante para reset
                ttl = await CacheManager.ttl(
                    tenant_id=tenant_id,
                    data_type="rate_limit",
                    resource_id=f"{limit_key}:count"
                )
                
                reset_in = ttl if ttl > 0 else limit_period
                error_context["reset_in_seconds"] = reset_in
                
                logger.warning(f"Rate limit excedido para tenant {tenant_id}: {current_count}/{rate_limit}", 
                              extra=error_context)
                
                raise RateLimitExceeded(
                    message="Has excedido el límite de solicitudes por minuto",
                    error_code=ErrorCode.RATE_LIMIT_EXCEEDED.value,
                    status_code=429,
                    context={
                        "current": current_count,
                        "limit": rate_limit,
                        "reset_in_seconds": reset_in,
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
                    resource_id=f"{limit_key}:count"
                )
                
            logger.debug(f"Rate limit para tenant {tenant_id}: {current_count+1}/{rate_limit}", 
                        extra=error_context)
            
            return True
        except RateLimitExceeded:
            # Propagar excepción de límite excedido
            raise
        except Exception as cache_error:
            error_message = f"Error de caché al verificar rate limit: {str(cache_error)}"
            logger.error(error_message, extra=error_context, exc_info=True)
            # En caso de error, permitir la solicitud por seguridad
            return True
    except RateLimitExceeded:
        # Propagar excepción de límite excedido
        raise
    except Exception as e:
        error_message = f"Error al aplicar rate limit: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        # En caso de error general, permitir la solicitud pero logging
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware para aplicar rate limiting a todas las peticiones.
    
    Aplica limitación basada en tenant y tipo de servicio.
    Agrega headers estándar de rate limit a la respuesta.
    """
    
    def __init__(self, app, exclude_paths=None):
        """
        Inicializa el middleware.
        
        Args:
            app: Aplicación FastAPI
            exclude_paths: Lista de prefijos de rutas a excluir
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/docs", "/openapi.json", "/health", "/metrics"]
    
    async def dispatch(self, request: Request, call_next):
        """
        Procesa cada solicitud HTTP, aplicando rate limiting según corresponda.
        
        Args:
            request: Solicitud HTTP
            call_next: Función para continuar el procesamiento
            
        Returns:
            Respuesta HTTP
            
        Raises:
            HTTPException: Si la solicitud excede los límites
        """
        path = request.url.path
        
        # Excluir rutas que no requieren rate limiting
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return await call_next(request)
        
        # Extraer tenant_id y tier
        tenant_id = None
        tier = "free"  # Tier por defecto
        
        # Contexto para logging
        error_context = {
            "function": "RateLimitMiddleware.dispatch",
            "path": path,
            "method": request.method
        }
        
        try:
            # Intentar obtener tenant_id del contexto
            tenant_id = get_current_tenant_id()
            error_context["tenant_id"] = tenant_id
            
            # Si no hay tenant_id, verificar en los headers
            if not tenant_id:
                tenant_id = request.headers.get("X-Tenant-ID")
                if tenant_id:
                    error_context["tenant_id"] = tenant_id
                    error_context["source"] = "header"
            
            # Si aún no hay tenant_id, verificar en los parámetros de consulta
            if not tenant_id:
                tenant_id = request.query_params.get("tenant_id")
                if tenant_id:
                    error_context["tenant_id"] = tenant_id
                    error_context["source"] = "query"
            
            # Verificar presencia del tenant_id
            if not tenant_id:
                # Si no podemos determinar el tenant, aplicar límite muy conservador
                logger.warning("No se pudo determinar tenant_id para rate limiting", 
                              extra=error_context)
                tenant_id = "default"
            
            # Determinar tier del tenant (podría obtenerse de Supabase o JWT)
            try:
                # Podrías obtener el tier de alguna fuente según tu arquitectura
                if "tenant_info" in request.state.__dict__:
                    tenant_info = request.state.tenant_info
                    tier = getattr(tenant_info, "tier", tier)
            except Exception as tier_error:
                logger.warning(f"Error al determinar tier: {str(tier_error)}", 
                              extra=error_context)
            
            error_context["tier"] = tier
            
            # Determinar el servicio según la ruta de la solicitud
            limit_key = self._determine_service_key(path)
            error_context["limit_key"] = limit_key
            
            # Aplicar rate limiting
            try:
                await apply_rate_limit(tenant_id, tier, limit_key)
            except RateLimitExceeded as rate_error:
                # Convertir a formato de respuesta HTTP
                error_data = getattr(rate_error, "context", {})
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": rate_error.message,
                        "code": rate_error.error_code,
                        "current": error_data.get("current", 0),
                        "limit": error_data.get("limit", 60),
                        "reset_in_seconds": error_data.get("reset_in_seconds", 60),
                        "service": error_data.get("service", "general")
                    }
                )
            
            # Procesar la solicitud
            response = await call_next(request)
            
            # Añadir headers de rate limit a la respuesta
            response = await self._add_rate_limit_headers(
                response, tenant_id, tier, limit_key
            )
            
            return response
        except HTTPException:
            # Propagar excepciones HTTP
            raise
        except Exception as e:
            # Logging para otros errores y permitir la solicitud
            error_message = f"Error en middleware de rate limit: {str(e)}"
            logger.error(error_message, extra=error_context, exc_info=True)
            # Continuar con la solicitud en caso de error
            return await call_next(request)
    
    def _determine_service_key(self, path: str) -> str:
        """
        Determina la clave de servicio basada en la ruta de la solicitud.
        
        Args:
            path: Ruta de la solicitud
            
        Returns:
            str: Clave del servicio para rate limiting
        """
        path = path.lower()
        
        # Mapeo de rutas a servicios
        if "/agent" in path or "/agents" in path:
            return "agent"
        elif "/query" in path or "/search" in path:
            return "query"
        elif "/embedding" in path or "/embeddings" in path:
            return "embedding"
        elif "/chat" in path or "/conversation" in path:
            return "chat"
        elif "/file" in path or "/upload" in path or "/document" in path:
            return "ingestion"
        elif "/collection" in path or "/kb" in path:
            return "collection"
        
        # Valor predeterminado
        return "api"
    
    async def _add_rate_limit_headers(
        self, 
        response,
        tenant_id: str,
        tier: str,
        limit_key: str
    ):
        """
        Añade headers de rate limit a la respuesta.
        
        Args:
            response: Respuesta HTTP
            tenant_id: ID del tenant
            tier: Nivel de suscripción
            limit_key: Clave del servicio
            
        Returns:
            Respuesta HTTP con headers de rate limit
        """
        try:
            # Obtener información de rate limit actualizada
            current = await CacheManager.get(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            current = int(current or 0)
            
            # Obtener límite según configuraciones
            service_name = None
            if limit_key in ["agent", "query", "embedding", "chat"]:
                service_name = limit_key
            
            # Usar la función estandarizada
            rate_limit = await get_tier_rate_limit(tenant_id, tier, service_name)
            
            # Obtener tiempo para reset
            ttl = await CacheManager.ttl(
                tenant_id=tenant_id,
                data_type="rate_limit",
                resource_id=f"{limit_key}:count"
            )
            
            # Valor por defecto si no hay TTL
            if ttl <= 0:
                settings = await get_settings()
                ttl = getattr(settings, "rate_limit_window_seconds", 60)
            
            # Agregar headers estándar de rate limiting
            # https://tools.ietf.org/id/draft-polli-ratelimit-headers-00.html
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit - current))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + ttl)
            
            return response
        except Exception as e:
            # En caso de error, no modificar la respuesta
            logger.error(f"Error al agregar headers de rate limit: {str(e)}")
            return response


def setup_rate_limiting(app):
    """
    Configura el middleware de rate limiting para la aplicación.
    
    Args:
        app: Aplicación FastAPI
    """
    logger.info("Configurando middleware de rate limiting")
    
    # Excluir rutas específicas
    exclude_paths = [
        "/docs", 
        "/openapi.json", 
        "/redoc", 
        "/health",
        "/metrics",
        "/favicon.ico"
    ]
    
    # Añadir middleware a la aplicación
    app.add_middleware(RateLimitMiddleware, exclude_paths=exclude_paths)
    
    logger.info("Middleware de rate limiting configurado correctamente")