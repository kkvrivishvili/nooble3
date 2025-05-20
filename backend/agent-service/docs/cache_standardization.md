# Estandarización de Claves de Caché en Agent Service

## Resumen

Este documento describe la implementación de un sistema estandarizado para las claves de caché utilizadas en el Agent Service, garantizando consistencia, mantenibilidad y facilitando la depuración de problemas relacionados con la caché.

## Implementación

### 1. Definición de Constantes

Se han definido constantes para los tipos de datos almacenados en caché en `config/constants.py`:

```python
# Cache Data Types
CACHE_TYPE_AGENT = "agent"
CACHE_TYPE_AGENT_CONFIG = "agent_config"
CACHE_TYPE_AGENT_TOOLS = "agent_tools"
CACHE_TYPE_CONVERSATION = "conversation"
CACHE_TYPE_CONVERSATION_MEMORY = "conversation_memory"
CACHE_TYPE_CONVERSATION_MESSAGE = "conversation_message"
CACHE_TYPE_CONVERSATION_MESSAGES_LIST = "conversation_messages_list"
CACHE_TYPE_AGENT_EXECUTION_STATE = "agent_execution_state"
CACHE_TYPE_COLLECTION_METADATA = "collection_metadata"
```

### 2. Estructura Jerárquica de Claves

Las claves de caché siguen una estructura jerárquica estándar:

```
tenant_id:data_type:[agent:agent_id]:[conv:conversation_id]:[coll:collection_id]:resource_id
```

Ejemplos:
- `tenant123:agent_config:agent:agent456:my_config`
- `tenant123:conversation_memory:conv:conv789:memory`

### 3. Utilidades para Caché

Se ha creado un nuevo archivo `services/cache_utils.py` con funciones auxiliares para interactuar con la caché:

```python
async def get_agent_with_cache(agent_id, tenant_id, fetch_function):
    """Obtiene un agente usando el patrón Cache-Aside estandarizado."""

async def get_agent_config_with_cache(agent_id, tenant_id, fetch_function):
    """Obtiene la configuración de un agente con caché estandarizada."""

async def get_conversation_memory_with_cache(conversation_id, tenant_id, agent_id, fetch_function, generate_function):
    """Obtiene la memoria de conversación con caché estandarizada."""
```

## Patrón de Uso en el Código

```python
# Importar las constantes y utilidades
from config.constants import CACHE_TYPE_AGENT, CACHE_TYPE_AGENT_CONFIG
from services.cache_utils import get_agent_with_cache

# Usar las funciones auxiliares para interactuar con la caché
agent, metrics = await get_agent_with_cache(
    agent_id=agent_id,
    tenant_id=tenant_id,
    fetch_function=fetch_agent_from_db
)
```

## Beneficios

- **Consistencia**: Todas las referencias a tipos de datos usan las mismas constantes
- **Mantenibilidad**: Los cambios en el formato de claves solo requieren modificar un punto central 
- **Depuración**: Las claves estandarizadas son más fáciles de identificar y monitorear
- **Validación**: Prevención de errores tipográficos al usar constantes en lugar de strings

## Pruebas y Verificación

Se recomienda verificar las claves utilizadas en Redis después de realizar operaciones:

```bash
# Conectar a Redis
redis-cli

# Listar todas las claves para un tenant específico
KEYS tenant123*

# Verificar el formato de las claves
KEYS tenant123:agent*
```
