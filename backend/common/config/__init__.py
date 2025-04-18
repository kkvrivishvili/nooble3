"""
Módulo para configuraciones y límites por tier.
"""

from .tiers import (
    get_tier_limits, 
    get_available_llm_models, 
    get_available_embedding_models,
    get_tier_rate_limit
)

# Nota: Las funciones de tracking no se importan aquí para evitar
# ciclos de importación. Se deben importar directamente de common.tracking

__all__ = [
    'get_tier_limits',
    'get_available_llm_models', 
    'get_available_embedding_models',
    'get_tier_rate_limit',
]

"""
Configuración centralizada para todos los servicios de la plataforma.
Proporciona acceso a ajustes, esquemas de configuración y límites por nivel.
"""

from .settings import Settings, get_settings, invalidate_settings_cache
from .schema import get_service_configurations, get_mock_configurations
from .tiers import get_tier_limits, get_available_llm_models, get_available_embedding_models
from .supabase_loader import override_settings_from_supabase

# Re-exportar símbolos principales para acceso directo
__all__ = [
    'Settings',
    'get_settings',
    'invalidate_settings_cache',
    'get_service_configurations', 
    'get_mock_configurations',
    'get_tier_limits',
    'get_available_llm_models',
    'get_available_embedding_models',
    'override_settings_from_supabase'
]