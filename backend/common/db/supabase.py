"""
Cliente Supabase centralizado con funciones de utilidad.
"""

from functools import lru_cache
import logging
import json
import os
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

from ..context.vars import get_current_tenant_id
from ..cache.manager import CacheManager
# Importamos las funciones desde auth.tenant para mantener compatibilidad
from ..auth.tenant import is_tenant_active, is_tenant_active_sync

logger = logging.getLogger(__name__)

# Constantes para configuración de Supabase, evitando importación circular
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
    """
    url = SUPABASE_URL
    
    # Determinar qué clave usar
    key = SUPABASE_KEY
    if use_service_role and SUPABASE_SERVICE_KEY:
        key = SUPABASE_SERVICE_KEY
    
    if not url or not key:
        logger.error("Credenciales Supabase no configuradas")
        raise ValueError("Supabase URL and key must be configured")
    
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Error creando cliente Supabase: {e}")
        raise


async def get_supabase_client_with_token(token: Optional[str] = None, use_service_role: bool = True) -> Client:
    """
    Versión async del cliente con token.
    Nota: La creación del cliente sigue siendo síncrona (limite de la librería supabase)
    """
    if token:
        # Verificar token async si es necesario
        from ..auth.utils import verify_token_async
        await verify_token_async(token)
        
    # La creación del cliente sigue siendo síncrona
    return get_supabase_client(use_service_role)


async def init_supabase() -> None:
    """
    Inicializa el cliente Supabase de forma async.
    Verifica conectividad y permisos.
    """
    try:
        client = get_supabase_client()
        # Test connection async
        from ..utils.async_utils import run_sync_as_async
        await run_sync_as_async(client.table('tenants').select('*').limit(1).execute)
        logger.info("Supabase initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Supabase: {e}")
        raise


async def get_tenant_configurations(
    tenant_id: Optional[str] = None, 
    scope: str = 'tenant',
    scope_id: Optional[str] = None,
    environment: str = "development"
) -> Dict[str, Any]:
    """
    Versión completamente async de la función
    """
    if tenant_id is None:
        from ..context import get_current_tenant_id
        tenant_id = get_current_tenant_id()

    try:
        cached_configs = await CacheManager.get(
            tenant_id=tenant_id, 
            data_type="tenant_configs",
            resource_id=f"{scope}:{scope_id or 'default'}:{environment}"
        )
        
        if cached_configs:
            return json.loads(cached_configs)
            
        client = get_supabase_client()
        query = client.table(get_table_name("tenant_configurations")).select(
            "config_key", "config_value", "config_type", "is_sensitive"
        ).eq("tenant_id", tenant_id).eq("environment", environment)
        
        if scope:
            query = query.eq("scope", scope)
            if scope_id:
                query = query.eq("scope_id", scope_id)
                
        result = query.execute()
        
        configurations = {}
        for config in result.data:
            if scope != 'tenant' and config.get('is_sensitive', False):
                continue
                
            config_type = config.get('config_type', 'string')
            from ..config.supabase_loader import safe_convert_config_value
            typed_value = safe_convert_config_value(config['config_value'], config_type)
            configurations[config['config_key']] = typed_value

        await CacheManager.set(
            tenant_id=tenant_id,
            data_type="tenant_configs",
            resource_id=f"{scope}:{scope_id or 'default'}:{environment}",
            value=json.dumps(configurations),
            ttl=3600
        )
        
        return configurations
    except Exception as e:
        logger.error(f"Error obteniendo configuraciones para tenant {tenant_id}: {e}")
        raise


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