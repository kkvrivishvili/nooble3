"""
Configuraciones específicas para el servicio de agentes.
"""

import os
from typing import Dict, Any, Optional

from common.config import get_settings as get_common_settings
from common.models import HealthResponse
from common.context import get_current_tenant_id

def get_settings():
    """
    Obtiene la configuración específica para el servicio de agentes.
    
    Esta función extiende get_settings() de common con configuraciones
    específicas del servicio de agentes.
    
    Returns:
        Settings: Configuración combinada
    """
    # Obtener configuración base
    settings = get_common_settings()
    
    # Agregar configuraciones específicas del servicio de agentes
    settings.service_name = "agent-service"
    settings.service_version = os.getenv("SERVICE_VERSION", "1.2.0")
    
    # Agregar configuraciones específicas de LLM que no están en settings común
    if not hasattr(settings, "model_capacity"):
        settings.model_capacity = {
            "gpt-3.5-turbo": 4096,
            "gpt-4": 8192,
            "gpt-4-turbo": 16384,
            "llama3": 8192,
        }
    
    # Configuraciones específicas de agentes
    settings.agent_default_message_limit = int(os.getenv("AGENT_DEFAULT_MESSAGE_LIMIT", "50"))
    settings.agent_streaming_timeout = int(os.getenv("AGENT_STREAMING_TIMEOUT", "300"))
    
    return settings

def get_agent_limits(agent_type: str) -> Dict[str, Any]:
    """
    Obtiene los límites específicos para un tipo de agente.
    
    Args:
        agent_type: Tipo de agente ("conversational", "assistant", "custom")
        
    Returns:
        Dict[str, Any]: Límites para el tipo de agente
    """
    settings = get_settings()
    limits = {
        "conversational": {
            "max_tools": 5,
            "max_iterations": 5,
            "max_memory_window": 10
        },
        "assistant": {
            "max_tools": 8,
            "max_iterations": 8,
            "max_memory_window": 20
        },
        "custom": {
            "max_tools": 10,
            "max_iterations": 10,
            "max_memory_window": 30
        }
    }
    
    return limits.get(agent_type, limits["conversational"])

def get_default_system_prompt(agent_type: str) -> str:
    """
    Obtiene el prompt de sistema predeterminado para un tipo de agente.
    
    Args:
        agent_type: Tipo de agente
        
    Returns:
        str: Prompt de sistema predeterminado
    """
    prompts = {
        "conversational": "Eres un asistente conversacional útil que responde preguntas de manera clara y concisa.",
        "assistant": "Eres un asistente avanzado que puede usar herramientas para ayudar a resolver problemas complejos.",
        "custom": "Eres un asistente personalizable que se adapta a las necesidades del usuario."
    }
    
    return prompts.get(agent_type, prompts["conversational"])