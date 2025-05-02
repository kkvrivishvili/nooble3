"""
Definiciones de niveles, límites y configuraciones específicas por tier.
"""

from typing import Dict, Any, List, Optional
import logging
from ..errors.handlers import handle_errors

logger = logging.getLogger(__name__)

# Centralización de límites de tiers en un único lugar
# Estos son los valores por defecto para cada tier
default_tier_limits = {
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
    },
    "pro": {
        "max_docs": 100,
        "max_knowledge_bases": 5,
        "has_advanced_rag": True,
        "max_tokens_per_month": 500000,
        "similarity_top_k": 8,
        "allowed_llm_models": ["gpt-3.5-turbo", "gpt-4"],
        "allowed_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
        "query_rate_limit_per_day": 500,
        "max_agents": 5,
        "max_tools_per_agent": 5,
    },
    "business": {
        "max_docs": 500,
        "max_knowledge_bases": 20,
        "has_advanced_rag": True,
        "max_tokens_per_month": 2000000,
        "similarity_top_k": 12,
        "allowed_llm_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        "allowed_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
        "query_rate_limit_per_day": 2000,
        "max_agents": 20,
        "max_tools_per_agent": 10,
    },
    "enterprise": {
        "max_docs": -1,  # Sin límite
        "max_knowledge_bases": -1,  # Sin límite
        "has_advanced_rag": True,
        "max_tokens_per_month": -1,  # Sin límite
        "similarity_top_k": 16,
        "allowed_llm_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4-32k"],
        "allowed_embedding_models": ["text-embedding-3-small", "text-embedding-3-large"],
        "query_rate_limit_per_day": -1,  # Sin límite
        "max_agents": -1,  # Sin límite
        "max_tools_per_agent": -1,  # Sin límite
    }
}

# Configuraciones de tasa por defecto para cada tier
default_rate_limits = {
    "free": 5,  # 5 solicitudes por minuto
    "pro": 30,  # 30 solicitudes por minuto
    "business": 60,  # 60 solicitudes por minuto
    "enterprise": 120  # 120 solicitudes por minuto (personalizable)
}

# Multiplicadores por servicio para ajuste fino
service_multipliers = {
    "embedding": 2.0,  # Mayor límite para embeddings (menos intensivos)
    "query": 0.8,  # Menor límite para consultas (más intensivas)
    "chat": 1.0,   # Límite estándar
    "agent": 0.5,  # Límite restringido (son costosos)
    "ingestion": 0.3  # Muy restringido (alta carga)
}

@handle_errors
async def get_tier_rate_limit(tenant_id: str, tier: str, service_name: Optional[str] = None) -> int:
    """
    Obtiene el límite de tasa para un tenant y tier específicos.
    
    Args:
        tenant_id: ID del tenant
        tier: Nivel de suscripción ('free', 'pro', 'business')
        service_name: Servicio específico (agent, query, chat, embedding, etc.)
        
    Returns:
        int: Número de solicitudes permitidas en el periodo
        
    Raises:
        ServiceError: Si hay un error obteniendo el límite
    """
    # Mantener la implementación actual...
    error_context = {
        "function": "get_tier_rate_limit",
        "tenant_id": tenant_id,
        "tier": tier,
        "service_name": service_name
    }
    
    try:
        # Intentar obtener configuración personalizada del tenant
        try:
            from ..db.supabase import get_tenant_configurations
            tenant_rate_limit_config = await get_tenant_configurations(
                tenant_id=tenant_id,
                scope="rate_limit",
                scope_id=service_name or "default"
            )
            
            # Si existe configuración específica para este tenant y servicio
            if tenant_rate_limit_config and "max_requests" in tenant_rate_limit_config:
                logger.debug(f"Usando límite personalizado para tenant {tenant_id}: "
                            f"{tenant_rate_limit_config['max_requests']} req/min",
                            extra=error_context)
                return int(tenant_rate_limit_config["max_requests"])
        except Exception as config_error:
            # Si hay error obteniendo configuración, usar valores predeterminados
            logger.warning(f"Error obteniendo configuración de rate limit para tenant {tenant_id}: {str(config_error)}",
                         extra=error_context)
            # Continuamos con valores predeterminados
        
        # Obtener límite base según el tier
        base_limit = default_rate_limits.get(tier.lower(), default_rate_limits["free"])
        error_context["base_limit"] = base_limit
        
        # Aplicar multiplicador si es un servicio específico
        if service_name:
            multiplier = service_multipliers.get(service_name, 1.0)
            final_limit = int(base_limit * multiplier)
            error_context["multiplier"] = multiplier
            error_context["final_limit"] = final_limit
            
            logger.debug(f"Límite de tasa para tenant {tenant_id}, tier {tier}, "
                        f"servicio {service_name}: {final_limit} req/min",
                        extra=error_context)
            return final_limit
        
        # Si no hay servicio específico, devolver límite base
        logger.debug(f"Límite de tasa para tenant {tenant_id}, tier {tier}: {base_limit} req/min",
                    extra=error_context)
        return base_limit
    
    except Exception as e:
        error_message = f"Error determinando límite de tasa para tenant {tenant_id}: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        
        # Devolver un valor predeterminado para no interrumpir el servicio
        return default_rate_limits.get("free", 5)


@handle_errors
async def get_tier_limits(tier: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene los límites para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        tenant_id: ID opcional del tenant para personalización
        
    Returns:
        Dict[str, Any]: Límites del nivel de suscripción
    """
    # Normalizar tier a lowercase
    tier = tier.lower()
    error_context = {"tenant_id": tenant_id, "tier": tier}
    
    try:
        # Si no existe el tier, usar free
        if tier not in default_tier_limits:
            logger.warning(f"Tier no reconocido: {tier}, usando 'free'", extra=error_context)
            tier = "free"
            
        # Copia de los límites por defecto
        limits = default_tier_limits[tier].copy()
        
        # Si hay tenant_id, verificar personalizaciones desde DB
        if tenant_id:
            # Importación tardía para evitar ciclos
            from ..db.supabase import get_table_name, get_supabase_client
            
            try:
                supabase = get_supabase_client()
                tier_customizations = supabase.table(get_table_name("tenant_tier_customizations")) \
                    .select("customizations") \
                    .eq("tenant_id", tenant_id) \
                    .eq("tier", tier) \
                    .execute()
                    
                if tier_customizations.data:
                    custom_limits = tier_customizations.data[0].get("customizations", {})
                    # Actualizar límites con personalizaciones
                    limits.update(custom_limits)
                    logger.debug(f"Límites personalizados aplicados para tenant {tenant_id}, tier {tier}")
            except Exception as e:
                logger.warning(f"Error obteniendo personalizaciones para tenant {tenant_id}: {e}", 
                              extra=error_context)
                # Continuar con valores por defecto
                
        return limits
        
    except Exception as e:
        logger.error(f"Error obteniendo límites para tier {tier}: {e}", extra=error_context)
        # Devolver límites de free como fallback
        return default_tier_limits["free"].copy()

def get_available_llm_models(tier: str, tenant_id: Optional[str] = None) -> List[str]:
    """
    Obtiene los modelos LLM disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        tenant_id: ID opcional del tenant para personalización
        
    Returns:
        List[str]: Lista de modelos LLM disponibles
    """
    # Primero obtener los límites completos del tier (que ya implementa personalización por tenant)
    tier_limits = get_tier_limits(tier, tenant_id)
    
    # Extraer los modelos permitidos de los límites
    return tier_limits.get("allowed_llm_models", ["gpt-3.5-turbo"])

def get_available_embedding_models(tier: str, tenant_id: Optional[str] = None) -> List[str]:
    """
    Obtiene los modelos de embedding disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        tenant_id: ID opcional del tenant para personalización
        
    Returns:
        List[str]: Lista de modelos de embedding disponibles
    """
    # Primero obtener los límites completos del tier (que ya implementa personalización por tenant)
    tier_limits = get_tier_limits(tier, tenant_id)
    
    # Extraer los modelos permitidos de los límites
    return tier_limits.get("allowed_embedding_models", ["text-embedding-3-small"])

def get_service_port(service_name: str) -> int:
    """
    Obtiene el puerto configurado para un servicio específico.
    
    Args:
        service_name: Nombre del servicio ('embedding', 'ingestion', 'query', 'agent')
        
    Returns:
        int: Puerto configurado para el servicio
    """
    # Mapa de puertos por defecto para servicios
    service_ports = {
        "embedding": 8001,
        "ingestion": 8000,
        "query": 8002,
        "agent": 8003,
        "chat": 8004
    }
    
    # Intentamos obtener de la configuración de entorno
    import os
    env_port = os.environ.get(f"{service_name.upper()}_SERVICE_PORT")
    if env_port and env_port.isdigit():
        return int(env_port)
    
    # Por defecto
    return service_ports.get(service_name.lower(), 8000)


# Funciones de entorno para configuración
def is_development_environment() -> bool:
    """
    Detecta si el entorno actual es de desarrollo.
    
    Returns:
        bool: True si estamos en entorno de desarrollo
    """
    import os
    env = os.getenv("ENVIRONMENT", "development").lower()
    return env in ["development", "dev", "local"]


def should_use_mock_config() -> bool:
    """
    Determina si se deben usar configuraciones mock.
    
    Se usarán configuraciones mock si:
    1. Estamos en entorno de desarrollo Y
    2. No hay conexión a Supabase o no hay configuraciones
    
    Returns:
        bool: True si se deben usar configuraciones mock
    """
    # Solo evaluar en entorno de desarrollo
    if not is_development_environment():
        return False
    
    # Verificar si hay conexión a Supabase
    try:
        from ..db.supabase import check_supabase_connection
        connection_ok = check_supabase_connection()
        
        if not connection_ok:
            logger.info("No hay conexión a Supabase, usando configuraciones mock")
            return True
            
        # Verificar si hay configuraciones base
        from ..db.supabase import get_base_configurations
        configs = get_base_configurations()
        
        if not configs:
            logger.info("No hay configuraciones en Supabase, usando configuraciones mock")
            return True
            
        return False
    except Exception as e:
        logger.warning(f"Error verificando Supabase, usando configuraciones mock: {e}")
        return True


"""
NOTA IMPORTANTE: SEPARACIÓN DE RESPONSABILIDADES

Este módulo contiene SOLAMENTE la configuración relacionada con tiers y limites,
sin añadir dependencias circulares. Las validaciones y tracking de uso están
en auth/models.py y tracking/usage.py respectivamente.
"""

# Nuevas funciones centralizadas para detalles de modelos y límites de agentes
def get_embedding_model_details(model_id: str) -> Dict[str, Any]:
    """
    Obtiene los detalles técnicos de un modelo de embedding específico.
    
    Args:
        model_id: ID del modelo de embedding
        
    Returns:
        Dict[str, Any]: Detalles del modelo (dimensiones, descripción, etc.)
    """
    # Diccionario centralizado con detalles de los modelos
    model_details = {
        "text-embedding-3-small": {
            "dimensions": 1536,
            "description": "OpenAI text-embedding-3-small model, adecuado para la mayoría de aplicaciones",
            "max_tokens": 8191,
            "provider": "openai",
            "version": "3",
            "cost_per_1k_tokens": 0.02
        },
        "text-embedding-3-large": {
            "dimensions": 3072,
            "description": "OpenAI text-embedding-3-large model, mayor precisión para tareas complejas",
            "max_tokens": 8191,
            "provider": "openai",
            "version": "3",
            "cost_per_1k_tokens": 0.13
        },
        "text-embedding-ada-002": {
            "dimensions": 1536,
            "description": "OpenAI text-embedding-ada-002 model (legacy)",
            "max_tokens": 8191,
            "provider": "openai",
            "version": "2",
            "cost_per_1k_tokens": 0.1
        },
        "nomic-embed-text": {
            "dimensions": 768,
            "description": "Nomic AI embedding model for Ollama",
            "max_tokens": 8192,
            "provider": "ollama",
            "version": "1",
            "cost_per_1k_tokens": 0
        }
    }
    
    # Si el modelo no existe, devolver diccionario vacío
    return model_details.get(model_id, {})


def get_llm_model_details(model_id: str) -> Dict[str, Any]:
    """
    Obtiene los detalles técnicos de un modelo de LLM específico.
    
    Args:
        model_id: ID del modelo LLM
        
    Returns:
        Dict[str, Any]: Detalles del modelo (contexto, capacidades, etc.)
    """
    # Diccionario centralizado con detalles de los modelos LLM
    model_details = {
        "gpt-3.5-turbo": {
            "context_window": 16385,
            "description": "Modelo GPT-3.5 Turbo de OpenAI, buena relación costo-rendimiento",
            "max_output_tokens": 4096,
            "provider": "openai",
            "version": "3.5",
            "cost_per_1k_input_tokens": 0.0015,
            "cost_per_1k_output_tokens": 0.002,
            "capabilities": ["text_generation", "chat", "function_calling"]
        },
        "gpt-4": {
            "context_window": 8192,
            "description": "Modelo GPT-4 de OpenAI, alta precisión y comprensión",
            "max_output_tokens": 4096,
            "provider": "openai",
            "version": "4",
            "cost_per_1k_input_tokens": 0.03,
            "cost_per_1k_output_tokens": 0.06,
            "capabilities": ["text_generation", "chat", "function_calling", "advanced_reasoning"]
        },
        "gpt-4-turbo": {
            "context_window": 128000,
            "description": "Modelo GPT-4 Turbo de OpenAI, amplio contexto y alto rendimiento",
            "max_output_tokens": 4096,
            "provider": "openai",
            "version": "4",
            "cost_per_1k_input_tokens": 0.01,
            "cost_per_1k_output_tokens": 0.03,
            "capabilities": ["text_generation", "chat", "function_calling", "advanced_reasoning", "vision"]
        },
        "llama3": {
            "context_window": 8192,
            "description": "Modelo Llama3 de Meta a través de Ollama",
            "max_output_tokens": 4096,
            "provider": "ollama",
            "version": "3",
            "cost_per_1k_input_tokens": 0,
            "cost_per_1k_output_tokens": 0,
            "capabilities": ["text_generation", "chat"]
        },
        "qwen3:1.7b": {
            "context_window": 8192,
            "description": "Modelo Qwen3 de Alibaba (1.7b) a través de Ollama",
            "max_output_tokens": 4096,
            "provider": "ollama",
            "version": "3",
            "cost_per_1k_input_tokens": 0,
            "cost_per_1k_output_tokens": 0,
            "capabilities": ["text_generation", "chat", "function_calling"]
        }
    }
    
    # Si el modelo no existe, devolver diccionario vacío
    return model_details.get(model_id, {})


def get_agent_limits(agent_type: str, tier: str) -> Dict[str, Any]:
    """
    Obtiene los límites específicos para un tipo de agente y tier.
    
    Args:
        agent_type: Tipo de agente ("conversational", "assistant", "custom", "rag")
        tier: Nivel de suscripción
        
    Returns:
        Dict[str, Any]: Límites específicos para el tipo de agente
    """
    # Bases por tipo de agente
    base_limits = {
        "conversational": {
            "max_messages": 100,
            "max_tokens_per_message": 2048,
            "max_functions": 5,
            "max_kb_connections": 1
        },
        "assistant": {
            "max_messages": 200,
            "max_tokens_per_message": 4096,
            "max_functions": 10,
            "max_kb_connections": 3
        },
        "rag": {
            "max_messages": 150,
            "max_tokens_per_message": 3072,
            "max_functions": 3,
            "max_kb_connections": 5
        },
        "custom": {
            "max_messages": 50,
            "max_tokens_per_message": 1024,
            "max_functions": 2,
            "max_kb_connections": 1
        }
    }
    
    # Modificadores por tier
    tier_multipliers = {
        "free": 1.0,
        "pro": 2.0,
        "business": 5.0,
        "enterprise": 10.0
    }
    
    # Obtener los valores base para el tipo de agente (o usar conversational como fallback)
    result = base_limits.get(agent_type, base_limits["conversational"]).copy()
    
    # Obtener multiplicador según tier (o usar 1.0 como fallback)
    multiplier = tier_multipliers.get(tier, 1.0)
    
    # Aplicar multiplicador a todos los valores numéricos
    for key in result:
        if isinstance(result[key], (int, float)):
            result[key] = int(result[key] * multiplier)
    
    return result


def get_default_system_prompt(agent_type: str) -> str:
    """
    Obtiene el prompt de sistema predeterminado para un tipo de agente.
    
    Args:
        agent_type: Tipo de agente
        
    Returns:
        str: Prompt de sistema predeterminado
    """
    system_prompts = {
        "conversational": (
            "Eres un asistente conversacional AI amigable y útil. "
            "Tu objetivo es ayudar al usuario proporcionando respuestas claras, "
            "precisas y útiles a sus preguntas."
        ),
        "assistant": (
            "Eres un asistente personal inteligente. Ayuda al usuario con sus tareas, "
            "recordatorios, búsqueda de información y cualquier otra solicitud. "
            "Sé proactivo, eficiente y orientado a resultados."
        ),
        "rag": (
            "Eres un asistente especializado en recuperación de información. "
            "Responde preguntas basándote exclusivamente en la información proporcionada "
            "en los documentos de contexto. Si no encuentras la respuesta en el contexto, "
            "indícalo claramente."
        ),
        "custom": (
            "Eres un asistente personalizado. Sigue las instrucciones específicas "
            "proporcionadas por el creador del agente."
        )
    }
    
    return system_prompts.get(agent_type, system_prompts["conversational"])