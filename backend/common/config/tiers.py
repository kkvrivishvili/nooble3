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
    from .settings import get_settings
    settings = get_settings()
    limits = {
        "free": settings.rate_limit_free_tier,
        "pro": settings.rate_limit_pro_tier,
        "business": settings.rate_limit_business_tier
    }
    return limits.get(tier, settings.rate_limit_free_tier)


def get_tier_limits(tier: str) -> Dict[str, Any]:
    """
    Obtiene los límites para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        Dict[str, Any]: Límites del nivel de suscripción
    """
    from .settings import get_settings
    tier_limits = {
        "free": {
            "max_docs": 20,
            "max_knowledge_bases": 1,
            "has_advanced_rag": False,
            "max_tokens_per_month": 100000,
            "similarity_top_k": 4,
            "allowed_llm_models": ["gpt-3.5-turbo"],
            "allowed_embedding_models": ["text-embedding-3-small"],
            "query_rate_limit_per_day": 100,
            "max_agents": 1,
            "max_tools_per_agent": 2,
            "max_public_agents": 1
        },
        "pro": {
            "max_docs": 100,
            "max_knowledge_bases": 5,
            "has_advanced_rag": True,
            "max_tokens_per_month": 1000000,
            "similarity_top_k": 8,
            "allowed_llm_models": ["gpt-3.5-turbo", "gpt-4-turbo"],
            "allowed_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
            "query_rate_limit_per_day": 1000,
            "max_agents": 5,
            "max_tools_per_agent": 5,
            "max_public_agents": 2
        },
        "business": {
            "max_docs": 500,
            "max_knowledge_bases": 20,
            "has_advanced_rag": True,
            "max_tokens_per_month": None,  # Ilimitado
            "similarity_top_k": 16,
            "allowed_llm_models": ["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4-turbo-vision", "claude-3-5-sonnet"],
            "allowed_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
            "query_rate_limit_per_day": 10000,
            "max_agents": 20,
            "max_tools_per_agent": 10,
            "max_public_agents": 5
        }
    }
    
    return tier_limits.get(tier, tier_limits["free"])


def get_available_llm_models(tier: str) -> List[str]:
    """
    Obtiene los modelos LLM disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        List[str]: Lista de modelos LLM disponibles
    """
    from .settings import get_settings
    tier_limits = get_tier_limits(tier)
    settings = get_settings()
    
    # Añadir modelos de Ollama si está configurado para usarlos
    available_models = list(tier_limits.get("allowed_llm_models", []))
    if settings.use_ollama:
        default_ollama_model = getattr(settings, "default_ollama_llm_model", "llama3")
        available_models.append(default_ollama_model)
    
    return available_models


def get_available_embedding_models(tier: str) -> List[str]:
    """
    Obtiene los modelos de embedding disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        List[str]: Lista de modelos de embedding disponibles
    """
    from .settings import get_settings
    tier_limits = get_tier_limits(tier)
    settings = get_settings()
    
    # Añadir modelos de Ollama si está configurado para usarlos
    available_models = list(tier_limits.get("allowed_embedding_models", []))
    if settings.use_ollama:
        default_ollama_model = getattr(settings, "default_ollama_embedding_model", "nomic-embed-text")
        available_models.append(default_ollama_model)
    
    return available_models


def get_service_port(service_name: str) -> int:
    """
    Obtiene el puerto configurado para un servicio específico.
    
    Args:
        service_name: Nombre del servicio ('embedding', 'ingestion', 'query', 'agent')
        
    Returns:
        int: Puerto configurado para el servicio
    """
    from .settings import get_settings
    settings = get_settings()
    
    # Intentar obtener el puerto específico para cada servicio
    try:
        if service_name == "embedding":
            return getattr(settings, "embedding_service_port", 8001)
        elif service_name == "ingestion":
            return getattr(settings, "ingestion_service_port", 8000)
        elif service_name == "query":
            return getattr(settings, "query_service_port", 8002)
        elif service_name == "agent":
            return getattr(settings, "agent_service_port", 8003)
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