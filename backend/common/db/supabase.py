"""
Cliente Supabase centralizado con funciones de utilidad.
"""

from functools import lru_cache
import logging
import json
import os
import traceback
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

from ..context.vars import get_current_tenant_id, get_full_context
from ..cache.manager import CacheManager
from ..errors.exceptions import DatabaseError, ConfigurationError, ServiceError, ErrorCode
from ..errors.handlers import handle_errors

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_TABLE_PREFIX = os.getenv("SUPABASE_TABLE_PREFIX", "")

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
        
    Raises:
        ConfigurationError: Si las credenciales de Supabase no están configuradas
        DatabaseError: Si hay un error al crear el cliente Supabase
    """
    error_context = {"function": "get_supabase_client"}
    
    url = SUPABASE_URL
    
    # Determinar qué clave usar
    key = SUPABASE_KEY
    if use_service_role and SUPABASE_SERVICE_KEY:
        key = SUPABASE_SERVICE_KEY
    
    if not url or not key:
        error_message = "Credenciales Supabase no configuradas"
        logger.error(error_message, extra=error_context)
        raise ConfigurationError(
            message=error_message,
            error_code=ErrorCode.MISSING_CONFIGURATION.value,
            context=error_context
        )
    
    try:
        return create_client(url, key)
    except Exception as e:
        error_context["error_type"] = type(e).__name__
        error_context["traceback"] = traceback.format_exc()
        error_message = f"Error creando cliente Supabase: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise DatabaseError(
            message=error_message,
            error_code=ErrorCode.DATABASE_ERROR.value,
            context=error_context
        )


async def get_supabase_client_with_token(token: Optional[str] = None, use_service_role: bool = True) -> Client:
    """
    Versión async del cliente con token.
    Nota: La creación del cliente sigue siendo síncrona (limite de la librería supabase)
    
    Args:
        token: Token JWT opcional para verificación
        use_service_role: Si es True, usa la clave de servicio
        
    Returns:
        Client: Cliente Supabase
        
    Raises:
        AuthenticationError: Si el token no es válido
        DatabaseError: Si hay un error al crear el cliente
    """
    error_context = {"function": "get_supabase_client_with_token"}
    error_context.update(get_full_context())
    
    try:
        if token:
            # Verificar token async si es necesario
            from ..auth.utils import verify_token_async
            await verify_token_async(token)
            
        # La creación del cliente sigue siendo síncrona
        return get_supabase_client(use_service_role)
    except Exception as e:
        # Si ya es un error tipado, propagarlo
        if isinstance(e, (DatabaseError, ConfigurationError)):
            raise
        
        error_context["error_type"] = type(e).__name__
        error_message = f"Error al obtener cliente Supabase con token: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise DatabaseError(
            message=error_message,
            context=error_context
        )


async def init_supabase() -> None:
    """
    Inicializa el cliente Supabase de forma async.
    Verifica conectividad y permisos.
    
    Raises:
        DatabaseError: Si hay un error al inicializar Supabase
    """
    error_context = {"function": "init_supabase"}
    
    try:
        client = get_supabase_client()
        # Test connection async
        from ..utils.async_utils import run_sync_as_async
        await run_sync_as_async(client.table('tenants').select('*').limit(1).execute)
        logger.info("Supabase initialized successfully")
    except Exception as e:
        # Si ya es un error tipado, propagarlo
        if isinstance(e, (DatabaseError, ConfigurationError)):
            raise
            
        error_context["error_type"] = type(e).__name__
        error_context["traceback"] = traceback.format_exc()
        error_message = f"Error initializing Supabase: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise DatabaseError(
            message=error_message,
            context=error_context
        )


async def get_tenant_configurations(
    tenant_id: Optional[str] = None, 
    scope: str = 'tenant',
    scope_id: Optional[str] = None,
    environment: str = "development"
) -> Dict[str, Any]:
    """
    Obtiene configuraciones para un tenant específico.
    
    Args:
        tenant_id: ID del tenant (opcional, usa contexto si no se proporciona)
        scope: Ámbito de configuración ('tenant', 'service', 'agent', 'collection')
        scope_id: ID específico del ámbito
        environment: Entorno ('development', 'staging', 'production')
        
    Returns:
        Dict: Configuraciones del tenant
        
    Raises:
        DatabaseError: Si hay un error de base de datos
        ServiceError: Para otros errores de servicio
    """
    # Usar contexto si no se proporciona tenant_id
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
    
    error_context = {
        "function": "get_tenant_configurations",
        "tenant_id": tenant_id,
        "scope": scope,
        "environment": environment
    }
    
    if scope_id:
        error_context["scope_id"] = scope_id

    try:
        # Intentar obtener desde caché primero
        cache_key = f"config:{tenant_id}:{scope}"
        if scope_id:
            cache_key += f":{scope_id}"
        cache_key += f":{environment}"
        
        cached_configs = await CacheManager.get(
            tenant_id=tenant_id, 
            data_type="configurations",
            resource_id=cache_key
        )
        
        if cached_configs:
            logger.debug(f"Usando configuraciones en caché para {tenant_id}")
            return cached_configs
            
        # Si no está en caché, obtener de Supabase
        logger.debug(f"Obteniendo configuraciones para tenant {tenant_id} desde Supabase")
        
        client = get_supabase_client(use_service_role=True)
        
        # Construir la consulta base
        query = (
            client.table('tenant_configurations')
            .select('*')
            .eq('tenant_id', tenant_id)
            .eq('environment', environment)
        )
        
        # Filtrar por scope y scope_id
        if scope != 'tenant':
            query = query.eq('scope', scope)
            
            if scope_id:
                query = query.eq('scope_id', scope_id)
        
        # Ejecutar consulta
        from ..utils.async_utils import run_sync_as_async
        result = await run_sync_as_async(query.execute)
        
        # Procesar configuraciones
        configurations = {}
        if result.data:
            for config in result.data:
                config_key = config['config_key']
                config_value = config['config_value']
                config_type = config['config_type']
                
                # Convertir valor según tipo
                if config_type == 'integer':
                    config_value = int(config_value)
                elif config_type == 'float':
                    config_value = float(config_value)
                elif config_type == 'boolean':
                    config_value = config_value.lower() in ('true', 't', '1', 'yes', 'y')
                elif config_type == 'json':
                    try:
                        config_value = json.loads(config_value)
                    except Exception as json_err:
                        logger.warning(f"Error parsing JSON config {config_key}: {json_err}", extra=error_context)
                
                configurations[config_key] = config_value
        
        # Guardar en caché para futuras solicitudes
        await CacheManager.set(
            tenant_id=tenant_id,
            data_type="configurations",
            resource_id=cache_key,
            data=configurations,
            ttl=3600  # 1 hora
        )
        
        return configurations
    except Exception as e:
        # Si ya es un error tipado, propagarlo
        if isinstance(e, (DatabaseError, ServiceError)):
            raise
            
        error_context["error_type"] = type(e).__name__
        error_context["traceback"] = traceback.format_exc()
        error_message = f"Error al obtener configuraciones: {str(e)}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise DatabaseError(
            message=error_message,
            context=error_context
        )


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
    import asyncio
    configs = asyncio.run(get_tenant_configurations(
        tenant_id=tenant_id, 
        scope='tenant',
        environment=environment
    ))
    
    # Sobrescribir con configuraciones de servicio si aplica
    if service_name:
        service_configs = asyncio.run(get_tenant_configurations(
            tenant_id=tenant_id,
            scope='service',
            scope_id=service_name,
            environment=environment
        ))
        configs.update(service_configs)
    
    # Sobrescribir con configuraciones de agente si aplica
    if agent_id:
        agent_configs = asyncio.run(get_tenant_configurations(
            tenant_id=tenant_id,
            scope='agent',
            scope_id=agent_id,
            environment=environment
        ))
        configs.update(agent_configs)
        
    # Sobrescribir con configuraciones de colección si aplica
    if collection_id:
        collection_configs = asyncio.run(get_tenant_configurations(
            tenant_id=tenant_id,
            scope='collection',
            scope_id=collection_id,
            environment=environment
        ))
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