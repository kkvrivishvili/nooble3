# Migración a TTLs Centralizados en Agent Service

## Resumen

Este documento describe la implementación de un sistema centralizado de TTL (Time-To-Live) para la caché del Agent Service, eliminando valores hardcodeados y asegurando consistencia en toda la aplicación al utilizar las constantes definidas en `common/core/constants.py`.

## Implementación

### 1. Importación de Constantes Centralizadas

Se utilizan las constantes TTL definidas en el módulo común en lugar de acceder directamente a los atributos de `CacheManager`:

```python
# Antes (usando atributos de CacheManager)
ttl=CacheManager.ttl_standard

# Después (usando constantes centralizadas)
from common.core.constants import TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT
ttl=TTL_STANDARD
```

### 2. Mapeo de TTL por Tipo de Datos

Se ha implementado un mapeo específico para el Agent Service en `config/constants.py`:

```python
# Mapeo de TTLs para tipos de datos específicos del Agent Service
AGENT_SERVICE_TTL_MAPPING = {
    CACHE_TYPE_AGENT: TTL_STANDARD,                    # 1 hora
    CACHE_TYPE_AGENT_CONFIG: TTL_STANDARD,             # 1 hora
    CACHE_TYPE_AGENT_TOOLS: TTL_STANDARD,              # 1 hora
    CACHE_TYPE_CONVERSATION: TTL_EXTENDED,             # 24 horas
    CACHE_TYPE_CONVERSATION_MEMORY: TTL_EXTENDED,      # 24 horas
    CACHE_TYPE_CONVERSATION_MESSAGE: TTL_EXTENDED,     # 24 horas
    CACHE_TYPE_CONVERSATION_MESSAGES_LIST: TTL_EXTENDED, # 24 horas
    CACHE_TYPE_AGENT_EXECUTION_STATE: TTL_SHORT,       # 5 minutos
    CACHE_TYPE_COLLECTION_METADATA: TTL_STANDARD,      # 1 hora
}
```

### 3. Función Auxiliar para Obtener TTL

Se ha creado una función para obtener el TTL adecuado según el tipo de datos:

```python
def get_ttl_for_data_type(data_type: str) -> int:
    """
    Obtiene el TTL adecuado para un tipo de datos específico del Agent Service.
    Primero verifica el mapeo específico del servicio, luego el mapeo global.
    
    Args:
        data_type: Tipo de datos
        
    Returns:
        TTL en segundos
    """
    from common.core.constants import DEFAULT_TTL_MAPPING
    
    # Verificar primero en el mapeo específico del servicio
    if data_type in AGENT_SERVICE_TTL_MAPPING:
        return AGENT_SERVICE_TTL_MAPPING[data_type]
    
    # Verificar en el mapeo global
    if data_type in DEFAULT_TTL_MAPPING:
        return DEFAULT_TTL_MAPPING[data_type]
    
    # Valor por defecto
    return TTL_STANDARD
```

## Patrón de Uso en el Código

```python
# Importar la función auxiliar
from config.constants import get_ttl_for_data_type, CACHE_TYPE_AGENT

# Obtener TTL específico para un tipo de datos
ttl = get_ttl_for_data_type(CACHE_TYPE_AGENT)

# Usar en operaciones de caché
await CacheManager.set(
    data_type=CACHE_TYPE_AGENT,
    resource_id=agent_id,
    value=agent_data,
    tenant_id=tenant_id,
    ttl=ttl
)
```

## Beneficios

- **Consistencia**: Todos los TTLs se definen en un único lugar
- **Mantenibilidad**: Los cambios en TTLs solo requieren modificar la configuración central
- **Adaptabilidad**: Permite ajustar TTLs específicos para diferentes tipos de datos según su volatilidad
- **Trazabilidad**: Facilita la identificación de problemas relacionados con expiración de caché

## Relación con el Patrón Cache-Aside

Esta implementación mejora la efectividad del patrón Cache-Aside al asegurar tiempos de expiración adecuados según la naturaleza de los datos:

- Datos volátiles (resultados de consultas): TTL_SHORT (5 minutos)
- Datos estándar (configuraciones): TTL_STANDARD (1 hora)
- Datos estables (memoria de conversación): TTL_EXTENDED (24 horas)
- Datos permanentes (constantes del sistema): TTL_PERMANENT (sin expiración)
