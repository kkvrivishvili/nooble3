"""
Funciones comunes para verificación de salud y estado de los servicios.

Este módulo provee funciones estandarizadas para implementar endpoints
de health check y status en todos los servicios backend, siguiendo
el patrón cache-aside y facilitando la centralización de métricas.
"""

import time
import logging
from typing import Dict, Callable, Awaitable, Optional, Any, Union

from common.models import HealthResponse, ServiceStatusResponse
from common.cache.manager import CacheManager
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.config import get_settings

logger = logging.getLogger(__name__)

async def basic_health_check(include_tenant_check: bool = True) -> Dict[str, str]:
    """
    Realiza un chequeo básico de salud verificando componentes críticos.
    
    Este es un chequeo ligero ideal para:
    - Liveness probes de Kubernetes
    - Monitoreo básico de disponibilidad
    - Health checks rápidos
    
    Args:
        include_tenant_check: Si debe verificar también la tabla de tenants (por defecto True)
        
    Returns:
        Dict[str, str]: Diccionario con componentes y sus estados ("available" o "unavailable")
    """
    components: Dict[str, str] = {}
    
    # Verificar cache
    cache_status = "unavailable"
    try:
        # Usamos directamente Redis para evitar dependencias circulares
        from redis.asyncio import Redis
        from common.cache.manager import get_redis_client
        
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.ping()
            cache_status = "available"
    except Exception as e:
        logger.warning(f"Cache no disponible en health check: {str(e)}")
    
    components["cache"] = cache_status
    
    # Verificar Supabase
    supabase_status = "unavailable"
    try:
        supabase = get_supabase_client()
        
        if include_tenant_check:
            # Verificar acceso a tabla de tenants (operación mínima)
            table_name = get_table_name("tenants")
            await supabase.table(table_name).select("tenant_id").limit(1).execute()
        
        supabase_status = "available"
    except Exception as e:
        logger.warning(f"Supabase no disponible en health check: {str(e)}")
    
    components["supabase"] = supabase_status
    
    return components


async def detailed_status_check(
    service_name: str,
    service_version: str,
    start_time: float,
    extra_checks: Optional[Dict[str, Callable[[], Awaitable[str]]]] = None,
    extra_metrics: Optional[Dict[str, Any]] = None
) -> ServiceStatusResponse:
    """
    Realiza un chequeo detallado del estado del servicio, incluyendo uptime y dependencias.
    
    Este es un chequeo completo ideal para:
    - Dashboards de monitoreo
    - Endpoints de observabilidad
    - Debugging manual
    
    Args:
        service_name: Nombre del servicio
        service_version: Versión del servicio
        start_time: Timestamp de inicio del servicio
        extra_checks: Funciones asíncronas adicionales para verificar componentes específicos
        extra_metrics: Métricas adicionales para incluir en la respuesta
        
    Returns:
        ServiceStatusResponse: Respuesta detallada con el estado del servicio
    """
    settings = get_settings()
    
    # Calcular tiempo de actividad
    uptime_seconds = time.time() - start_time
    uptime_formatted = time.strftime("%H:%M:%S", time.gmtime(uptime_seconds))
    
    # Obtener componentes básicos
    components = await basic_health_check()
    
    # Convertir estado de componentes a valores booleanos para dependencies
    dependencies = {key: (value == "available") for key, value in components.items()}
    
    # Ejecutar verificaciones adicionales específicas del servicio
    if extra_checks:
        for name, check_fn in extra_checks.items():
            try:
                status = await check_fn()
                components[name] = status
                dependencies[name] = (status == "available")
            except Exception as e:
                logger.warning(f"Error en verificación adicional '{name}': {str(e)}")
                components[name] = "unavailable"
                dependencies[name] = False
    
    # Determinar estado general
    # - Healthy: Todos los componentes críticos disponibles
    # - Degraded: Algunos componentes críticos no disponibles
    # - Limited: Componentes críticos disponibles pero dependencias no
    
    # Los componentes críticos son cache y supabase
    critical_available = components["cache"] == "available" and components["supabase"] == "available"
    all_available = all(value == "available" for value in components.values())
    
    if critical_available:
        if all_available:
            status = "healthy"
        else:
            status = "limited"
    else:
        status = "degraded"
    
    # Construir respuesta
    response = ServiceStatusResponse(
        success=True,
        service_name=service_name,
        version=service_version,
        environment=settings.environment,
        uptime=uptime_seconds,
        uptime_formatted=uptime_formatted,
        status=status,
        components=components,
        dependencies=dependencies
    )
    
    # Añadir métricas adicionales si se proporcionaron
    if extra_metrics:
        response.metadata = extra_metrics
    
    return response


def get_service_health(components: Dict[str, str], service_version: str) -> HealthResponse:
    """
    Genera una respuesta de health check basada en componentes verificados.
    
    Args:
        components: Diccionario de componentes y sus estados
        service_version: Versión del servicio
        
    Returns:
        HealthResponse: Respuesta estándar de health check
    """
    # Determinar estado general
    all_available = all(value == "available" for value in components.values())
    critical_available = (
        components.get("cache", "unavailable") == "available" and 
        components.get("supabase", "unavailable") == "available"
    )
    
    if all_available:
        status = "healthy"
        message = "Servicio completamente operativo"
    elif critical_available:
        status = "degraded"
        message = "Servicio operativo con funcionalidad limitada"
    else:
        status = "unavailable"
        message = "Servicio no operativo"
    
    # Construir respuesta
    return HealthResponse(
        success=True,
        status=status,
        components=components,
        version=service_version,
        message=message
    )
