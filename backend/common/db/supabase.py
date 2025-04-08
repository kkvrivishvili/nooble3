"""
Cliente Supabase centralizado con funciones de utilidad.
"""

from functools import lru_cache
import logging
import json
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

from ..context.vars import get_current_tenant_id

logger = logging.getLogger(__name__)

@lru_cache
def get_supabase_client(use_service_role: bool = True) -> Client:
    """
    Obtiene un cliente Supabase con caché para reutilización.
    
    Args:
        use_service_role: Si es True, usa la clave de servicio (service role) 
                          cuando está disponible, que permite bypass de políticas RLS.
                          Para acceso público debe ser False.
    
    Returns:
        Client: Cliente Supabase
    """
    # Importar get_settings aquí para evitar importación circular
    from ..config.settings import get_settings
    settings = get_settings()
    
    # Usar clave de service role si está disponible y se solicita
    api_key = settings.supabase_key
    if use_service_role and hasattr(settings, 'supabase_service_key') and settings.supabase_service_key:
        api_key = settings.supabase_service_key
        logger.debug("Usando clave de servicio (service role) para Supabase")
    
    supabase = create_client(
        settings.supabase_url,
        api_key
    )
    return supabase


def get_supabase_client_with_token(token: Optional[str] = None, use_service_role: bool = True) -> Client:
    """
    Obtiene un cliente Supabase, opcionalmente con un token JWT de usuario.
    
    Args:
        token: Token JWT opcional del usuario. Si se proporciona, se usa para autenticación
              y prevalece sobre use_service_role.
        use_service_role: Si es True y no hay token, usa la clave de servicio cuando está disponible.
        
    Returns:
        Client: Cliente Supabase configurado
    """
    # Importar get_settings aquí para evitar importación circular
    from ..config.settings import get_settings
    settings = get_settings()
    
    if token:
        # Si hay token, usar para autenticación de usuario
        # Usar la clave pública (anon) ya que el token maneja la autenticación
        api_key = settings.supabase_key
        
        logger.debug("Creando cliente Supabase con token JWT de usuario")
        return create_client(
            settings.supabase_url,
            api_key,
            options={"headers": {"Authorization": f"Bearer {token}"}}
        )
    else:
        # Sin token, usar cliente normal (potencialmente con service key)
        return get_supabase_client(use_service_role=use_service_role)


def init_supabase():
    """
    Inicializa el cliente Supabase.
    Esta función se usa principalmente para garantizar que el cliente
    está disponible durante la inicialización de la aplicación.
    
    Returns:
        None
    """
    try:
        client = get_supabase_client()
        logger.info("Supabase inicializado correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar Supabase: {str(e)}")
        raise


def is_tenant_active(tenant_id: str) -> bool:
    """
    Verifica si un tenant está activo en Supabase.
    
    Args:
        tenant_id: ID del tenant a verificar
        
    Returns:
        bool: True si el tenant existe y está activo, False en caso contrario
    """
    from ..cache.redis import get_cached_value, cache_value
    
    # Usar caché para evitar consultas frecuentes
    cache_key = f"tenant_active:{tenant_id}"
    cached_result = get_cached_value(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    try:
        client = get_supabase_client()
        from .tables import get_table_name
        result = client.table(get_table_name("tenants")).select("is_active").eq("tenant_id", tenant_id).execute()
        
        # Verificar que el tenant exista y esté activo
        is_active = False
        if result.data and len(result.data) > 0:
            is_active = result.data[0].get("is_active", False)
        
        # Cachear el resultado por un tiempo limitado (5 minutos)
        cache_value(cache_key, is_active, ttl=300)
        
        if not is_active:
            logger.warning(f"Tenant {tenant_id} no está activo o no existe")
            
        return is_active
    except Exception as e:
        logger.error(f"Error verificando estado del tenant {tenant_id}: {str(e)}")
        return False


def get_tenant_configurations(
    tenant_id: Optional[str] = None, 
    scope: str = 'tenant',
    scope_id: Optional[str] = None,
    environment: str = "development"
) -> Dict[str, Any]:
    """
    Obtiene configuraciones para un tenant específico con soporte para ámbitos.
    
    Args:
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        scope: Ámbito ('tenant', 'service', 'agent', 'collection')
        scope_id: ID específico del ámbito (ej: agent_id, service_name)
        environment: Entorno (development, staging, production)
        
    Returns:
        Dict[str, Any]: Diccionario con las configuraciones convertidas al tipo apropiado
    """
    if not tenant_id:
        tenant_id = get_current_tenant_id()
    
    # Generar clave de caché específica para este ámbito
    cache_key = f"tenant_config:{tenant_id}:{environment}:{scope}"
    if scope_id:
        cache_key = f"{cache_key}:{scope_id}"
        
    try:
        # Intentar obtener de la caché primero
        from ..cache.redis import get_cached_value, cache_value
        cached_configs = get_cached_value(cache_key)
        if cached_configs is not None:
            return cached_configs
        
        # Si no está en caché, consultar a la base de datos
        client = get_supabase_client()
        query = client.table(get_table_name("tenant_configurations")).select(
            "config_key", "config_value", "config_type", "is_sensitive"
        ).eq("tenant_id", tenant_id).eq("environment", environment)
        
        # Filtrar por ámbito
        if scope:
            query = query.eq("scope", scope)
            if scope_id:
                query = query.eq("scope_id", scope_id)
                
        result = query.execute()
        
        configurations = {}
        for config in result.data:
            # No incluir configuraciones sensibles para solicitudes no de tenant
            if scope != 'tenant' and config.get('is_sensitive', False):
                continue
                
            # Convertir valor al tipo adecuado
            config_type = config.get('config_type', 'string')
            from ..config.supabase_loader import safe_convert_config_value
            typed_value = safe_convert_config_value(config['config_value'], config_type)
            
            # Almacenar en el diccionario de resultados
            configurations[config['config_key']] = typed_value
        
        # Guardar en caché
        cache_value(cache_key, configurations, ttl=300)  # 5 minutos
        
        return configurations
    except Exception as e:
        logger.error(f"Error obteniendo configuraciones para tenant {tenant_id}: {e}")
        return {}


def get_effective_configurations(
    tenant_id: str,
    service_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    environment: str = "development"
) -> Dict[str, Any]:
    """
    Obtiene configuraciones efectivas siguiendo una jerarquía de herencia:
    Tenant → Servicio → Agente → Colección
    
    Args:
        tenant_id: ID del tenant
        service_name: Nombre del servicio
        agent_id: ID del agente
        collection_id: ID de la colección
        environment: Entorno
        
    Returns:
        Configuraciones combinadas con la adecuada prioridad
    """
    # Configuraciones a nivel de tenant (base)
    configs = get_tenant_configurations(
        tenant_id=tenant_id, 
        scope='tenant',
        environment=environment
    )
    
    # Sobrescribir con configuraciones de servicio si aplica
    if service_name:
        service_configs = get_tenant_configurations(
            tenant_id=tenant_id,
            scope='service',
            scope_id=service_name,
            environment=environment
        )
        configs.update(service_configs)
    
    # Sobrescribir con configuraciones de agente si aplica
    if agent_id:
        agent_configs = get_tenant_configurations(
            tenant_id=tenant_id,
            scope='agent',
            scope_id=agent_id,
            environment=environment
        )
        configs.update(agent_configs)
        
    # Sobrescribir con configuraciones de colección si aplica
    if collection_id:
        collection_configs = get_tenant_configurations(
            tenant_id=tenant_id,
            scope='collection',
            scope_id=collection_id,
            environment=environment
        )
        configs.update(collection_configs)
        
    return configs


def set_tenant_configuration(
    tenant_id: str, 
    config_key: str, 
    config_value: Any,
    config_type: Optional[str] = None,
    is_sensitive: bool = False,
    scope: str = 'tenant',
    scope_id: Optional[str] = None,
    description: Optional[str] = None,
    environment: str = "development"
) -> bool:
    """
    Establece o actualiza una configuración para un tenant específico.
    
    Args:
        tenant_id: ID del tenant
        config_key: Clave de configuración
        config_value: Valor de configuración (se convertirá a string)
        config_type: Tipo de configuración (string, integer, float, boolean, json)
        is_sensitive: Indica si la configuración contiene datos sensibles
        scope: Ámbito de la configuración (tenant, service, agent, collection)
        scope_id: ID específico del ámbito (ej: agent_id)
        description: Descripción opcional
        environment: Entorno (development, staging, production)
        
    Returns:
        bool: True si se actualizó correctamente
    """
    try:
        # Determinar el tipo automáticamente si no se proporciona
        if config_type is None:
            if isinstance(config_value, bool):
                config_type = 'boolean'
            elif isinstance(config_value, int):
                config_type = 'integer'
            elif isinstance(config_value, float):
                config_type = 'float'
            elif isinstance(config_value, (dict, list)):
                config_type = 'json'
                config_value = json.dumps(config_value)
            else:
                config_type = 'string'
                
        # Convertir el valor a string para almacenamiento
        if config_type == 'json' and not isinstance(config_value, str):
            str_value = json.dumps(config_value)
        else:
            str_value = str(config_value)
        
        # Insertar/actualizar en la base de datos
        client = get_supabase_client()
        from .tables import get_table_name
        
        data = {
            "tenant_id": tenant_id,
            "config_key": config_key,
            "config_value": str_value,
            "config_type": config_type,
            "is_sensitive": is_sensitive,
            "scope": scope,
            "scope_id": scope_id,
            "environment": environment
        }
        
        if description:
            data["description"] = description
            
        client.table(get_table_name("tenant_configurations")).upsert(data).execute()
        
        # Invalidar caché
        from ..config.supabase_loader import apply_tenant_configuration_changes
        apply_tenant_configuration_changes(tenant_id, environment, scope, scope_id)
        
        return True
    except Exception as e:
        logger.error(f"Error configurando {config_key}={config_value} para tenant {tenant_id}: {e}")
        return False