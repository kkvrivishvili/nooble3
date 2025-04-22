"""
Módulo para configuraciones y límites por tier.
"""

# Importaciones para settings
from .settings import Settings, get_settings, invalidate_settings_cache, get_service_settings

# Importaciones para tiers (Single Source of Truth para configuraciones de tiers)
from .tiers import (
    get_tier_limits,
    get_available_llm_models,
    get_available_embedding_models,
    get_tier_rate_limit,
    get_embedding_model_details,
    get_llm_model_details,
    get_agent_limits,
    get_default_system_prompt,
    is_development_environment,
    should_use_mock_config
)

# Importar todas las constantes globales
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
    DEFAULT_TTL_MAPPING
)

__all__ = [
    # Settings
    "Settings", "get_settings", "invalidate_settings_cache", "get_service_settings",
    
    # Tiers
    "get_tier_limits", "get_available_llm_models", "get_available_embedding_models",
    "get_tier_rate_limit", "get_embedding_model_details", "get_llm_model_details",
    "get_agent_limits", "get_default_system_prompt", "is_development_environment",
    "should_use_mock_config",
    
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
    "DEFAULT_TTL_MAPPING"
]