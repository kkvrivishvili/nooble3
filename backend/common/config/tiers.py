"""
Definiciones de niveles, límites y configuraciones específicas por tier.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

def get_tier_rate_limit(tier: str) -> int:
    """
    Obtiene el límite de tasa para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        int: Número de solicitudes permitidas en el periodo
    """
    # Definimos los límites directamente para evitar la importación circular
    limits = {
        "free": 600,        # Valores predeterminados
        "pro": 1200,
        "business": 3000
    }
    return limits.get(tier, 600)  # Valor por defecto para free tier


def get_tier_limits(tier: str, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Obtiene los límites para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        settings: Configuraciones opcionales (evita importación circular)
        
    Returns:
        Dict[str, Any]: Límites del nivel de suscripción
    """
    # Usamos los límites predeterminados si no se proporcionan settings
    if settings is None:
        from .settings import default_tier_limits
        return default_tier_limits.get(tier, default_tier_limits["free"])
    
    # Combinamos con configuraciones personalizadas si existen
    tier_limits = default_tier_limits.get(tier, default_tier_limits["free"]).copy()
    
    # Sobreescribimos con configuraciones personalizadas si existen
    custom_limits = settings.get("tier_limits", {}).get(tier, {})
    tier_limits.update(custom_limits)
    
    return tier_limits


def get_available_llm_models(tier: str, settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Obtiene los modelos LLM disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        settings: Configuraciones opcionales (evita importación circular)
        
    Returns:
        List[str]: Lista de modelos LLM disponibles
    """
    tier_limits = get_tier_limits(tier, settings)
    
    # Añadir modelos de Ollama si está configurado para usarlos
    available_models = list(tier_limits.get("allowed_llm_models", []))
    if settings and settings.get("use_ollama"):
        default_ollama_model = settings.get("default_ollama_llm_model", "llama3")
        available_models.append(default_ollama_model)
    
    return available_models


def get_available_embedding_models(tier: str, settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Obtiene los modelos de embedding disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        settings: Configuraciones opcionales (evita importación circular)
        
    Returns:
        List[str]: Lista de modelos de embedding disponibles
    """
    tier_limits = get_tier_limits(tier, settings)
    
    # Añadir modelos de Ollama si está configurado para usarlos
    available_models = list(tier_limits.get("allowed_embedding_models", []))
    if settings and settings.get("use_ollama"):
        default_ollama_model = settings.get("default_ollama_embedding_model", "nomic-embed-text")
        available_models.append(default_ollama_model)
    
    return available_models


def get_service_port(service_name: str, settings: Optional[Dict[str, Any]] = None) -> int:
    """
    Obtiene el puerto configurado para un servicio específico.
    
    Args:
        service_name: Nombre del servicio ('embedding', 'ingestion', 'query', 'agent')
        settings: Configuraciones opcionales (evita importación circular)
        
    Returns:
        int: Puerto configurado para el servicio
    """
    # Intentar obtener el puerto específico para cada servicio
    try:
        if service_name == "embedding":
            return settings.get("embedding_service_port", 8001)
        elif service_name == "ingestion":
            return settings.get("ingestion_service_port", 8000)
        elif service_name == "query":
            return settings.get("query_service_port", 8002)
        elif service_name == "agent":
            return settings.get("agent_service_port", 8003)
        else:
            return 8004  # Puerto por defecto
    except AttributeError:
        # Valores por defecto si no están definidos en configuración
        defaults = {
            "embedding": 8001,
            "ingestion": 8000,
            "query": 8002,
            "agent": 8003
        }
        return defaults.get(service_name, 8004)


# Funciones de entorno para configuración
def is_development_environment() -> bool:
    """
    Detecta si el entorno actual es de desarrollo.
    
    Returns:
        bool: True si estamos en entorno de desarrollo
    """
    import os
    # Verificar variables de entorno comunes para identificar desarrollo
    env_vars = os.environ.get("CONFIG_ENVIRONMENT", "").lower()
    return (
        env_vars in ["development", "dev", "local", ""] or
        os.environ.get("DEBUG", "").lower() in ["true", "1", "yes"]
    )

def should_use_mock_config() -> bool:
    """
    Determina si se deben usar configuraciones mock.
    
    Se usarán configuraciones mock si:
    1. Estamos en entorno de desarrollo Y
    2. No hay conexión a Supabase o no hay configuraciones
    
    Returns:
        bool: True si se deben usar configuraciones mock
    """
    import os
    if not is_development_environment():
        return False
        
    # Verificar si tenemos valores básicos de Supabase
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    
    # Si no tenemos credenciales de Supabase, usar mock
    if not supabase_url or not supabase_key or supabase_url == "http://localhost:54321":
        return True
        
    return False