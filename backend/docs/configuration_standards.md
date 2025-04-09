# Estándares de Configuración en Nooble3

Este documento define los estándares para la configuración centralizada de todos los servicios de la plataforma Nooble3.

## Principios Generales

1. **Centralización**: Toda la configuración debe estar definida en `common.config.settings`
2. **Extensibilidad**: Los servicios deben extender la configuración base, no duplicarla
3. **Invalidación clara**: Mecanismos explícitos para invalidar la caché de configuración
4. **Configuración por tenant**: Soporte para configuración específica por tenant

## Acceso a la Configuración

Siempre utiliza `get_settings()` para acceder a la configuración:

```python
from common.config.settings import get_settings

def mi_funcion():
    settings = get_settings()
    url = settings.embedding_service_url
    # ...
```

## Extensión de la Configuración para Servicios Específicos

Para añadir configuraciones específicas de un servicio:

1. Extiende la clase Settings en el módulo de configuración del servicio:

```python
# En ingestion-service/config.py
from pydantic import Field
from common.config.settings import Settings as BaseSettings

class IngestionSettings(BaseSettings):
    """Configuración específica para el servicio de ingesta."""
    
    # Configuraciones específicas
    max_document_size: int = Field(10_000_000, description="Tamaño máximo de documento en bytes")
    supported_extensions: list = Field(["pdf", "docx", "txt"], description="Extensiones soportadas")
    
    # No repitas configuraciones que ya estén en BaseSettings

# Función de acceso centralizada
def get_ingestion_settings():
    # Obtener configuración base y extenderla
    base_settings = get_settings()
    
    # Crear instancia con valores por defecto
    ingestion_settings = IngestionSettings(
        # Pasar valores de configuración base que se necesitan
        service_name="ingestion-service",
        environment=base_settings.environment,
        # ... otros valores heredados
    )
    
    return ingestion_settings
```

2. Usa la configuración específica en el servicio:

```python
from ingestion-service.config import get_ingestion_settings

def process_document():
    settings = get_ingestion_settings()
    max_size = settings.max_document_size
    # ...
```

## Configuración por Tenant

Para obtener configuración específica por tenant:

```python
from common.db.supabase import get_tenant_configurations
from common.context.vars import get_current_tenant_id

async def mi_funcion():
    tenant_id = get_current_tenant_id()
    
    # Obtener configuración específica del tenant
    tenant_config = await get_tenant_configurations(
        tenant_id=tenant_id,
        scope="llm",  # Categoría de configuración
        scope_id="gpt-4"  # ID específico opcional
    )
    
    # Usar la configuración
    max_tokens = tenant_config.get("max_tokens", 2048)  # Valor por defecto como fallback
```

## Invalidación de Caché

Para forzar la recarga de la configuración:

```python
from common.config.settings import invalidate_settings_cache

# Invalidar para un tenant específico
invalidate_settings_cache(tenant_id="tenant123")

# Invalidar para todos los tenants
invalidate_settings_cache()
```

## Manejo de Secretos y Claves API

1. **Nunca** hardcodear secretos o claves API en el código
2. Utilizar siempre variables de entorno para valores sensibles:

```python
# En settings.py
api_key: str = Field(..., env="API_SERVICE_KEY", description="API key para servicio externo")
```

3. Para claves específicas de tenant, almacenarlas en Supabase y acceder mediante `get_tenant_configurations`

## Configuración en Tiempo de Ejecución

Para modificar la configuración en tiempo de ejecución:

```python
from common.config.settings import get_settings, invalidate_settings_cache
from common.db.supabase import update_tenant_configuration

async def update_config(tenant_id: str, new_value: int):
    # Actualizar en base de datos
    await update_tenant_configuration(
        tenant_id=tenant_id,
        scope="rate_limit",
        scope_id="api",
        value=new_value
    )
    
    # Invalidar caché para que se recargue
    invalidate_settings_cache(tenant_id=tenant_id)
```

## Validación de Configuración

Utiliza los validadores de Pydantic para asegurar valores correctos:

```python
from pydantic import validator

class MySettings(BaseSettings):
    port: int = 8080
    
    @validator("port")
    def validate_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError("El puerto debe estar entre 1024 y 65535")
        return v
```

## Configuración de Desarrollo vs. Producción

- Usa la variable `environment` para comportamiento específico según el entorno:

```python
settings = get_settings()
if settings.environment == "development":
    # Comportamiento de desarrollo
    logging.getLogger().setLevel(logging.DEBUG)
else:
    # Comportamiento de producción
    logging.getLogger().setLevel(logging.INFO)
```

## Registro y Depuración de Configuración

Para depurar la configuración:

```python
def print_config_debug():
    settings = get_settings()
    # Omitir valores sensibles
    safe_values = {k: v for k, v in settings.dict().items() 
                  if "key" not in k.lower() and "secret" not in k.lower()}
    logger.debug(f"Configuración actual: {json.dumps(safe_values, indent=2)}")
```

## Migración de Código Existente

Para migrar código existente a la configuración centralizada:

1. Identificar y listar todas las configuraciones específicas del servicio
2. Verificar si ya existen en `common.config.settings.Settings`
3. Crear una clase derivada de Settings para las configuraciones no existentes
4. Reemplazar todos los usos de configuración existentes por llamadas a get_settings()
