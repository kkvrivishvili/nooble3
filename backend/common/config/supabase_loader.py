"""
Carga dinámica de configuraciones desde Supabase.
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def override_settings_from_supabase(settings: Any, tenant_id: str, environment: str = "development") -> Any:
    """
    Sobrescribe las configuraciones del objeto Settings con valores de Supabase.
    Esta función es utilizada por get_settings() en settings.py cuando load_config_from_supabase=True.
    
    Utiliza el sistema jerárquico de configuraciones:
    - Configuraciones base a nivel de tenant
    - Sobrescribe con configuraciones específicas del servicio si existen
    
    Args:
        settings: Objeto Settings de configuración
        tenant_id: ID del tenant
        environment: Entorno (development, staging, production)
        
    Returns:
        Any: Objeto Settings con los valores actualizados
    """
    try:
        # Obtener las configuraciones efectivas usando la jerarquía
        from ..db.supabase import get_effective_configurations
        
        configs = get_effective_configurations(
            tenant_id=tenant_id,
            service_name=getattr(settings, "service_name", None),
            environment=environment
        )
        
        if not configs:
            logger.warning(f"No se encontraron configuraciones para tenant {tenant_id} en entorno {environment}")
            return settings
        
        # Convertir y aplicar configuraciones
        for key, value in configs.items():
            if hasattr(settings, key):
                # El valor ya está correctamente convertido por get_effective_configurations
                setattr(settings, key, value)
                logger.debug(f"Configuración {key} actualizada para tenant {tenant_id}")
        
        return settings
    except Exception as e:
        logger.error(f"Error aplicando configuraciones desde Supabase: {e}")
        return settings


def safe_convert_config_value(value: str, config_type: str) -> Any:
    """
    Convierte un valor de configuración al tipo especificado de manera segura.
    
    Args:
        value: Valor como string
        config_type: Tipo de configuración ('string', 'integer', 'float', 'boolean', 'json')
        
    Returns:
        Valor convertido al tipo apropiado
    """
    try:
        if config_type == 'integer':
            if value is None:
                return 0
            return int(value)
        elif config_type == 'float':
            if value is None:
                return 0.0
            return float(value)
        elif config_type == 'boolean':
            if value is None:
                return False
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return bool(value)
        elif config_type == 'json':
            if isinstance(value, str):
                return json.loads(value)
            return value
        # Por defecto, devolver como string
        return str(value)
    except Exception as e:
        logger.error(f"Error convirtiendo valor '{value}' a tipo {config_type}: {e}")
        # En caso de error de conversión, devolver valores predeterminados seguros según el tipo
        if config_type == 'integer':
            return 0
        elif config_type == 'float':
            return 0.0
        elif config_type == 'boolean':
            return False
        elif config_type == 'json':
            return {}
        return ""


def apply_tenant_configuration_changes(
    tenant_id: str, 
    environment: str = "development",
    scope: str = "tenant",
    scope_id: Optional[str] = None
) -> bool:
    """
    Aplica cambios de configuración para un tenant específico, incluyendo
    la invalidación de caché y configuraciones.
    
    Args:
        tenant_id: ID del tenant
        environment: Entorno (development, staging, production)
        scope: Ámbito de la configuración ('tenant', 'service', 'agent', 'collection')
        scope_id: ID específico del ámbito
        
    Returns:
        bool: True si se aplicaron correctamente
    """
    try:
        # Invalidar caché de configuraciones
        from .settings import invalidate_settings_cache
        invalidate_settings_cache(tenant_id)
        
        # Crear patrón de caché para limpiar
        cache_pattern = f"tenant_config:{tenant_id}:{environment}"
        if scope != "tenant":
            cache_pattern = f"{cache_pattern}:{scope}"
            if scope_id:
                cache_pattern = f"{cache_pattern}:{scope_id}"
        
        # Limpiar todas las entradas de caché relacionadas usando cache redis
        import asyncio
        from ..cache.redis import cache_delete_pattern
        # Ejecutar eliminación de patrones en Redis
        asyncio.run(cache_delete_pattern(f"{cache_pattern}*"))
        
        logger.info(f"Configuraciones aplicadas para tenant {tenant_id} en ámbito {scope}")
        return True
    except Exception as e:
        logger.error(f"Error aplicando cambios de configuración para tenant {tenant_id}: {e}")
        return False