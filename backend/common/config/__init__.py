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

# Re-exportar símbolos principales para acceso directo
__all__ = [
    # Settings
    'Settings',
    'get_settings',
    'get_service_settings',
    'invalidate_settings_cache',
    
    # Tiers (Single Source of Truth)
    'get_tier_limits',
    'get_available_llm_models', 
    'get_available_embedding_models',
    'get_tier_rate_limit',
    
    # Nuevas funciones centralizadas
    'get_embedding_model_details',
    'get_llm_model_details',
    'get_agent_limits',
    'get_default_system_prompt',
    
    # Funciones de utilidad
    'is_development_environment',
    'should_use_mock_config'
]

# Nota: Las funciones internas como get_service_configurations, get_mock_configurations y 
# override_settings_from_supabase no se exportan deliberadamente para evitar
# dependencias circulares y forzar el uso de los puntos de entrada principales.