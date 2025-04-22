"""
Módulo core para componentes fundamentales compartidos.

Este módulo proporciona la base arquitectónica para evitar dependencias circulares
y facilitar una estructura de código más mantenible usando un enfoque de
arquitectura limpia con inyección de dependencias.
"""

# Exportar constantes fundamentales
from .constants import (
    # Constantes de TTL
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT,
    
    # Constantes de fuente de datos
    SOURCE_CACHE, SOURCE_SUPABASE, SOURCE_GENERATION,
    
    # Constantes de métricas
    METRIC_CACHE_HIT, METRIC_CACHE_MISS, METRIC_LATENCY, METRIC_CACHE_SIZE,
    METRIC_CACHE_INVALIDATION, METRIC_CACHE_INVALIDATION_COORDINATED,
    METRIC_SERIALIZATION_ERROR, METRIC_DESERIALIZATION_ERROR,
    
    # Códigos de error básicos
    ERROR_GENERAL, ERROR_NOT_FOUND, ERROR_VALIDATION, ERROR_TENANT_REQUIRED,
    ERROR_DATABASE, ERROR_CACHE, ERROR_CONFIGURATION,
    
    # Mapeos de TTL
    DEFAULT_TTL_MAPPING,
    
    # Prioridades de componentes
    COMPONENT_PRIORITY_CORE, COMPONENT_PRIORITY_CONFIG, COMPONENT_PRIORITY_DB,
    COMPONENT_PRIORITY_CACHE, COMPONENT_PRIORITY_AUTH, COMPONENT_PRIORITY_ERROR,
    COMPONENT_PRIORITY_SERVICE, COMPONENT_PRIORITY_API
)

# Exportar registro de componentes
from .registry import (
    Registry, register, register_factory, register_lazy, 
    get, get_all, get_sorted_component_names, is_initialized, clear
)

# Exportar adaptadores (interfaces)
from .adapters import (
    ConfigAdapter, CacheAdapter, ErrorAdapter, DatabaseAdapter, 
    MetricsAdapter, ContextAdapter
)

# Exportar sistema de bootstrap
from .bootstrap import (
    # Registro de componentes
    register_component, component,
    
    # Hooks
    register_initialization_hook, register_async_initialization_hook, register_shutdown_hook,
    
    # Inicialización
    initialize_all, initialize_all_async,
    initialize_from_modules, initialize_from_modules_async,
    
    # Apagado
    shutdown
)

# Exportar todos los elementos
__all__ = [
    # Constantes de TTL
    "TTL_SHORT", "TTL_STANDARD", "TTL_EXTENDED", "TTL_PERMANENT",
    
    # Constantes de fuente
    "SOURCE_CACHE", "SOURCE_SUPABASE", "SOURCE_GENERATION",
    
    # Constantes de métricas
    "METRIC_CACHE_HIT", "METRIC_CACHE_MISS", "METRIC_LATENCY", "METRIC_CACHE_SIZE",
    "METRIC_CACHE_INVALIDATION", "METRIC_CACHE_INVALIDATION_COORDINATED",
    "METRIC_SERIALIZATION_ERROR", "METRIC_DESERIALIZATION_ERROR",
    
    # Códigos de error básicos
    "ERROR_GENERAL", "ERROR_NOT_FOUND", "ERROR_VALIDATION", "ERROR_TENANT_REQUIRED",
    "ERROR_DATABASE", "ERROR_CACHE", "ERROR_CONFIGURATION",
    
    # Mapeos de TTL
    "DEFAULT_TTL_MAPPING",
    
    # Prioridades de componentes
    "COMPONENT_PRIORITY_CORE", "COMPONENT_PRIORITY_CONFIG", "COMPONENT_PRIORITY_DB",
    "COMPONENT_PRIORITY_CACHE", "COMPONENT_PRIORITY_AUTH", "COMPONENT_PRIORITY_ERROR",
    "COMPONENT_PRIORITY_SERVICE", "COMPONENT_PRIORITY_API",
    
    # Registry
    "Registry", "register", "register_factory", "register_lazy", 
    "get", "get_all", "get_sorted_component_names", "is_initialized", "clear",
    
    # Adaptadores
    "ConfigAdapter", "CacheAdapter", "ErrorAdapter", "DatabaseAdapter", 
    "MetricsAdapter", "ContextAdapter",
    
    # Bootstrap
    "register_component", "component",
    "register_initialization_hook", "register_async_initialization_hook", "register_shutdown_hook",
    "initialize_all", "initialize_all_async",
    "initialize_from_modules", "initialize_from_modules_async",
    "shutdown"
]
