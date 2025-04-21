# Sistema de Configuración Centralizada

Este documento describe el sistema de configuración centralizada implementado en la plataforma. El objetivo principal es proporcionar una forma consistente y sin duplicaciones para gestionar las configuraciones de todos los servicios.

## Principios de Diseño

El sistema de configuración se basa en los siguientes principios:

1. **Single Source of Truth (SSOT)**: Cada configuración tiene un único lugar donde se define, lo que evita inconsistencias y duplicaciones.
2. **Single Implementation (SI)**: Cada funcionalidad tiene una única implementación de referencia.
3. **Separación de Responsabilidades**: Las configuraciones básicas (settings.py), las configuraciones por tier (tiers.py) y la lógica de aplicación están claramente separadas.
4. **Sin Dependencias Circulares**: La arquitectura evita dependencias circulares entre módulos.

## Estructura General

```
common/
├── config/
│   ├── __init__.py       # Re-exportaciones para facilitar importaciones
│   ├── settings.py       # Configuraciones básicas y específicas por servicio
│   └── tiers.py          # Configuraciones específicas por tier de suscripción
├── auth/
│   └── models.py         # Lógica de validación de acceso a modelos
└── tracking/
    └── __init__.py       # Funciones de tracking de uso
```

## Módulos Principales

### 1. Settings (`common.config.settings`)

Contiene la clase `Settings` y funciones para obtener configuraciones globales y específicas por servicio.

#### Funciones Principales

- `get_settings(tenant_id: Optional[str] = None) -> Settings`: Obtiene las configuraciones para un tenant específico.
- `invalidate_settings_cache(tenant_id: Optional[str] = None)`: Invalida la caché de configuraciones.
- `get_service_settings(service_name: str, service_version: Optional[str] = None, tenant_id: Optional[str] = None) -> Settings`: Obtiene configuraciones específicas de un servicio.

### 2. Tiers (`common.config.tiers`)

Contiene todas las configuraciones relacionadas con los tiers de suscripción y modelos disponibles.

#### Funciones Principales

- `get_tier_limits(tier: str) -> Dict[str, Any]`: Obtiene límites para un tier específico.
- `get_available_llm_models(tier: str) -> List[str]`: Obtiene modelos LLM disponibles para un tier.
- `get_available_embedding_models(tier: str) -> List[str]`: Obtiene modelos de embedding disponibles para un tier.
- `get_tier_rate_limit(tenant_id: str, tier: str, service_name: str) -> int`: Obtiene límites de tasa personalizados.

#### Funciones Adicionales

- `get_embedding_model_details(model_id: str) -> Dict[str, Any]`: Obtiene detalles de un modelo de embedding.
- `get_llm_model_details(model_id: str) -> Dict[str, Any]`: Obtiene detalles de un modelo LLM.
- `get_agent_limits(agent_type: str, tier: str) -> Dict[str, Any]`: Obtiene límites específicos de agentes.
- `get_default_system_prompt(agent_type: str) -> str`: Obtiene el prompt por defecto para un tipo de agente.

## Configuración por Servicio

Cada servicio tiene su archivo `config.py` que utiliza `get_service_settings()` para configurarse correctamente. Esto elimina la duplicación de código y asegura la consistencia entre servicios.

### 1. Agent Service

```python
# agent-service/config.py
from common.config import get_service_settings, get_agent_limits, get_default_system_prompt

def get_settings():
    return get_service_settings("agent-service")
```

### 2. Embedding Service

```python
# embedding-service/config.py  
from common.config import get_service_settings, get_embedding_model_details

def get_settings():
    return get_service_settings("embedding-service")
```

### 3. Query Service

```python
# query-service/config.py
from common.config import get_service_settings

def get_settings():
    return get_service_settings("query-service")
```

### 4. Ingestion Service

```python
# ingestion-service/config.py
from common.config import get_service_settings

def get_settings():
    return get_service_settings("ingestion-service")
```

## Variables de Entorno

Las variables de entorno se definen en el archivo `.env` en la raíz del proyecto y se cargan automáticamente. Las variables específicas para cada servicio están documentadas en este archivo.

## Guía de Uso

### Obtener Configuraciones Básicas

```python
from common.config import get_settings

settings = get_settings()
redis_url = settings.redis_url
```

### Obtener Configuraciones de Servicio

```python
from common.config import get_service_settings

# Para un servicio específico
settings = get_service_settings("query-service")
chunk_size = settings.chunk_size

# Dentro de un servicio, simplemente use el helper local
from config import get_settings
settings = get_settings()
```

### Obtener Configuraciones de Tier

```python
from common.config.tiers import get_tier_limits, get_available_llm_models

# Obtener límites para un tier
limits = get_tier_limits("pro")
max_tokens = limits["max_tokens"]

# Obtener modelos disponibles
models = get_available_llm_models("business")
```

### Validar Acceso a Modelos

```python
from common.auth import validate_model_access

is_allowed = validate_model_access(tenant_id, model_id, model_type="llm")
```

## Buenas Prácticas

1. **Importar Correctamente**: Siempre importar desde `common.config` y no desde submódulos específicos.
2. **No Duplicar Configuraciones**: No definir configuraciones fuera del sistema centralizado.
3. **Respetar Responsabilidades**: Usar tiers.py solo para datos de configuración, no para lógica de aplicación.
4. **Validación en Auth**: La validación de acceso debe hacerse a través de `common.auth`.
5. **Tracking Centralizado**: Usar `common.tracking` para tracking de uso.

## Actualización de Configuraciones

Para actualizar las configuraciones:

1. Para configuraciones básicas: modificar `Settings` en `settings.py`.
2. Para configuraciones por tier: modificar las estructuras en `tiers.py`.
3. Para configuraciones específicas de servicio: modificar la función `get_service_settings` en `settings.py`.

## Conclusión

Este sistema de configuración centralizada asegura consistencia, evita duplicaciones y facilita el mantenimiento del código. Todas las configuraciones fluyen desde sus respectivos módulos centralizados hacia los servicios que las utilizan, siguiendo los principios de SSOT y SI.
