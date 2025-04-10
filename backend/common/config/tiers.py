"""
Definiciones de niveles, límites y configuraciones específicas por tier.
"""

from typing import Dict, Any, List, Optional
import logging

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

# Valores predeterminados para límites de tasa
default_rate_limits = {
    "free": 600,        # 10 req/segundo
    "pro": 1200,        # 20 req/segundo
    "business": 3000,   # 50 req/segundo
    "enterprise": 6000  # 100 req/segundo
}

# Multiplicadores por servicio para límites de tasa
service_multipliers = {
    "agent": 0.5,        # Más restrictivo para agentes
    "chat": 0.5,         # Más restrictivo para chat
    "embedding": 2.0,    # Menos restrictivo para embeddings
    "query": 1.0,        # Normal para consultas
    "ingestion": 0.3,    # Muy restrictivo para ingesta de documentos
    "collection": 0.5    # Restrictivo para operaciones de colección
}

def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            from ..errors.exceptions import ServiceError, ErrorCode
            error_message = f"Error en la función {func.__name__}: {str(e)}"
            logger.error(error_message, exc_info=True)
            raise ServiceError(ErrorCode.INTERNAL_ERROR, error_message)
    return wrapper

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
    from ..context.vars import get_full_context
    from ..db.supabase import get_tenant_configurations
    
    error_context = {
        "function": "get_tier_rate_limit",
        "tenant_id": tenant_id,
        "tier": tier,
        "service_name": service_name
    }
    error_context.update(get_full_context())
    
    try:
        # Intentar obtener configuración personalizada del tenant
        try:
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
        return default_rate_limits.get("free", 600)


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
    # Importaciones dinámicas
    from ..db.supabase import get_tenant_configurations
    from ..errors.exceptions import ServiceError, ErrorCode
    
    if tier not in default_tier_limits:
        raise ServiceError(
            error_code=ErrorCode.INVALID_PARAMETER,
            message=f"Nivel de suscripción no válido: {tier}"
        )
    
    # Por defecto, usamos los límites predefinidos
    limits = default_tier_limits[tier].copy()
    
    # Si se proporciona un tenant_id, intentamos obtener configuraciones personalizadas
    if tenant_id:
        try:
            custom_configs = await get_tenant_configurations(tenant_id)
            # Combinamos con la configuración personalizada si existe
            if custom_configs and "tier_limits" in custom_configs and tier in custom_configs["tier_limits"]:
                custom_tier_limits = custom_configs["tier_limits"][tier]
                limits.update(custom_tier_limits)
        except Exception as e:
            logger.warning(f"Error al obtener configuraciones personalizadas para {tenant_id}: {str(e)}")
    
    return limits

def get_available_llm_models(tier: str) -> List[str]:
    """
    Obtiene los modelos LLM disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        List[str]: Lista de modelos LLM disponibles
    """
    if tier not in default_tier_limits:
        return default_tier_limits["free"]["allowed_llm_models"]
    
    return default_tier_limits[tier]["allowed_llm_models"]

def get_available_embedding_models(tier: str) -> List[str]:
    """
    Obtiene los modelos de embedding disponibles para un nivel de suscripción específico.
    
    Args:
        tier: Nivel de suscripción ('free', 'pro', 'business')
        
    Returns:
        List[str]: Lista de modelos de embedding disponibles
    """
    if tier not in default_tier_limits:
        return default_tier_limits["free"]["allowed_embedding_models"]
    
    return default_tier_limits[tier]["allowed_embedding_models"]

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
    env = os.environ.get("ENVIRONMENT", "development").lower()
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
    # Si no estamos en desarrollo, nunca usamos mock
    if not is_development_environment():
        return False
    
    # En desarrollo, intentamos verificar si tenemos conexión
    try:
        from ..db.supabase import get_supabase_client
        supabase = get_supabase_client()
        
        # Hacemos una consulta simple para verificar conexión
        result = supabase.table("tenants").select("count", count="exact").limit(1).execute()
        
        # Si hay algún error o no hay datos, usamos mock
        if hasattr(result, "error") and result.error:
            logger.warning(f"Usando mock por error de Supabase: {result.error}")
            return True
            
        return False
    except Exception as e:
        logger.warning(f"Usando mock por excepción al verificar Supabase: {str(e)}")
        return True