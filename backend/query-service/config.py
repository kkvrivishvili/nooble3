"""
Configuraciones específicas para el servicio de consultas.
"""

import os
from typing import Dict, Any, Optional, List

from common.config import get_settings as get_common_settings
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de consultas.
    
    Esta función extiende get_settings() de common con configuraciones
    específicas del servicio de consultas.
    
    Returns:
        Settings: Configuración combinada
    """
    # Obtener configuración base
    settings = get_common_settings()
    
    # Agregar configuraciones específicas del servicio de consultas
    settings.service_name = "query-service"
    settings.service_version = os.getenv("SERVICE_VERSION", "1.3.0")
    
    # Configuraciones específicas de RAG
    settings.default_similarity_top_k = int(os.getenv("DEFAULT_SIMILARITY_TOP_K", "4"))
    settings.default_response_mode = os.getenv("DEFAULT_RESPONSE_MODE", "compact")
    settings.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
    
    # Modos de respuesta disponibles
    settings.available_response_modes = [
        "compact", 
        "refine", 
        "tree_summarize", 
        "simple_summarize"
    ]
    
    return settings

def get_collection_config(collection_id: str) -> Dict[str, Any]:
    """
    Obtiene la configuración específica para una colección.
    
    Args:
        collection_id: ID de la colección
        
    Returns:
        Dict[str, Any]: Configuración de la colección
    """
    tenant_id = get_current_tenant_id()
    settings = get_settings()
    
    # Valores por defecto
    config = {
        "similarity_top_k": settings.default_similarity_top_k,
        "response_mode": settings.default_response_mode,
        "similarity_threshold": settings.similarity_threshold,
    }
    
    try:
        # Importar aquí para evitar dependencias circulares
        from common.db.supabase import get_effective_configurations
        
        # Obtener configuraciones específicas para esta colección
        collection_configs = get_effective_configurations(
            tenant_id=tenant_id,
            service_name="query",
            collection_id=collection_id,
            environment=settings.environment
        )
        
        # Actualizar configuraciones si existen
        if collection_configs:
            if "default_similarity_top_k" in collection_configs:
                config["similarity_top_k"] = int(collection_configs["default_similarity_top_k"])
                
            if "default_response_mode" in collection_configs:
                config["response_mode"] = collection_configs["default_response_mode"]
                
            if "similarity_threshold" in collection_configs:
                config["similarity_threshold"] = float(collection_configs["similarity_threshold"])
    except Exception as e:
        # Continuar con valores por defecto
        pass
    
    return config