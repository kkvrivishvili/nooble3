"""
Configuraciones específicas para el servicio de embeddings.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_settings as get_common_settings
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de embeddings.
    
    Esta función extiende get_settings() de common con configuraciones
    específicas del servicio de embeddings.
    
    Returns:
        Settings: Configuración combinada
    """
    # Obtener configuración base
    settings = get_common_settings()
    
    # Agregar configuraciones específicas del servicio de embeddings
    settings.service_name = "embedding-service"
    settings.service_version = os.getenv("SERVICE_VERSION", "1.2.0")
    
    # Configuraciones específicas de embeddings
    settings.embedding_cache_enabled = os.getenv("EMBEDDING_CACHE_ENABLED", "true").lower() in ["true", "1", "yes"]
    settings.embedding_batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
    settings.default_embedding_dimension = int(os.getenv("DEFAULT_EMBEDDING_DIMENSION", "1536"))
    
    return settings

def get_available_models_for_tier(tier: str) -> Dict[str, Dict[str, Any]]:
    """
    Obtiene los modelos de embeddings disponibles para un nivel de suscripción.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'enterprise')
        
    Returns:
        Dict[str, Dict[str, Any]]: Diccionario con modelos disponibles
    """
    # Modelos básicos disponibles para todos
    basic_models = {
        "text-embedding-3-small": {
            "dimensions": 1536,
            "description": "OpenAI text-embedding-3-small model, suitable for most applications",
            "max_tokens": 8191
        },
        "text-embedding-ada-002": {
            "dimensions": 1536,
            "description": "OpenAI legacy model, maintained for backwards compatibility",
            "max_tokens": 8191
        }
    }
    
    # Modelos adicionales para niveles premium
    pro_models = {
        "text-embedding-3-large": {
            "dimensions": 3072,
            "description": "OpenAI's most capable embedding model with higher dimensions for better performance",
            "max_tokens": 8191
        }
    }
    
    # Modelos exclusivos para nivel enterprise
    enterprise_models = {
        "text-embedding-3-turbo": {
            "dimensions": 3072,
            "description": "Embeddings de mayor rendimiento, optimizados para RAG y búsquedas semánticas",
            "max_tokens": 16000
        },
        "custom-domain-embedding": {
            "dimensions": 4096,
            "description": "Embeddings personalizados para dominios específicos con entrenamiento adicional",
            "max_tokens": 32000
        }
    }
    
    # Devolver modelos según el nivel de suscripción
    result = basic_models.copy()
    
    if tier.lower() in ['pro', 'business']:
        result.update(pro_models)
        
    if tier.lower() in ['enterprise', 'business']:
        result.update(enterprise_models)
        
    return result