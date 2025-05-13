"""
Configuraciones específicas para el servicio de consultas.

Este módulo implementa la configuración específica del servicio de consultas
utilizando el sistema centralizado de configuración, separando las configuraciones
específicas del servicio de las configuraciones globales.
"""

from typing import Dict, Any, Optional, List
from pydantic import Field, BaseModel

from common.config import get_service_settings
from common.models import HealthResponse
from common.context import Context

def get_settings():
    """
    Obtiene la configuración específica para el servicio de consultas.
    
    Esta función utiliza get_service_settings() centralizada que ya incluye
    todas las configuraciones específicas para el servicio de consultas.
    
    Returns:
        Settings: Configuración para el servicio de consultas
    """
    # Usar la función centralizada que ya incluye las configuraciones específicas
    return get_service_settings("query-service")

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de consultas.
    
    Returns:
        HealthResponse: Estado de salud del servicio
    """
    settings = get_settings()
    
    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        status="healthy",
        timestamp=None  # Se generará automáticamente
    )

async def get_collection_config(collection_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """
    Obtiene la configuración específica para una colección.
    
    Esta función consulta la base de datos para obtener configuraciones 
    específicas para una colección, con fallback a valores predeterminados.
    Soporta configuraciones personalizadas por tenant y colección.
    
    Args:
        collection_id: ID de la colección
        ctx: Contexto opcional con información del tenant
        
    Returns:
        Dict[str, Any]: Configuración de la colección
    """
    # Obtener configuraciones por defecto del servicio
    settings = get_settings()
    
    # Configuración por defecto para cualquier colección
    default_config = {
        "similarity_top_k": settings.default_similarity_top_k,
        "response_mode": settings.default_response_mode,
        "similarity_threshold": settings.similarity_threshold,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }
    
    # Obtener tenant_id del contexto si está disponible
    tenant_id = None
    if ctx:
        try:
            tenant_id = ctx.get_tenant_id()
        except Exception:
            pass
    
    # Si no tenemos tenant_id o collection_id, devolver configuración por defecto
    if not tenant_id or not collection_id:
        return default_config
    
    try:
        # Importar dependencias necesarias (importación tardía para evitar ciclos)
        from common.db.supabase import get_supabase_client
        from common.db.tables import get_table_name
        from common.cache import CacheManager
        
        # Generar clave de caché para la configuración
        cache_key = f"collection_config:{tenant_id}:{collection_id}"
        
        # Verificar si la configuración está en caché
        cached_config = await CacheManager.get("config", cache_key, tenant_id=tenant_id)
        if cached_config:
            return {**default_config, **cached_config}  # Combinar con valores por defecto
        
        # Si no está en caché, consultar la base de datos
        supabase = get_supabase_client()
        table_name = get_table_name("collections")
        
        # Obtener configuración de la colección desde la base de datos
        result = (supabase.table(table_name)
                  .select("config")
                  .eq("tenant_id", tenant_id)
                  .eq("collection_id", collection_id)
                  .limit(1)
                  .execute())
        
        # Verificar si encontramos la configuración
        if result.data and len(result.data) > 0 and "config" in result.data[0]:
            # Obtener configuración personalizada
            custom_config = result.data[0]["config"]
            
            # Si es un string (JSON), convertirlo a diccionario
            if isinstance(custom_config, str):
                import json
                try:
                    custom_config = json.loads(custom_config)
                except json.JSONDecodeError:
                    custom_config = {}
            
            # Si es None o no es un diccionario, usar un diccionario vacío
            if not isinstance(custom_config, dict):
                custom_config = {}
            
            # Guardar en caché para futuras consultas
            await CacheManager.set(
                data_type="config",
                resource_id=cache_key,
                value=custom_config,
                tenant_id=tenant_id,
                ttl=CacheManager.ttl_standard  # Usando constante estandarizada para configuraciones
            )
            
            # Combinar configuración personalizada con valores por defecto
            return {**default_config, **custom_config}
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error al obtener configuración de colección: {str(e)}")
    
    # Si hay algún error o no se encuentra la configuración, usar valores por defecto
    return default_config
