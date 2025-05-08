# Sistema de Caché Centralizado

## Descripción General

Este módulo proporciona una implementación centralizada y unificada del sistema de caché para todos los servicios del backend. Está diseñado siguiendo principios de alto rendimiento, escalabilidad y consistencia.

El sistema se compone de dos componentes principales que trabajan en conjunto:

1. **CacheManager**: Infraestructura base de caché multinivel
2. **get_with_cache_aside**: Implementación estandarizada del patrón Cache-Aside

## Arquitectura

### Caché Multinivel

El sistema implementa una arquitectura de caché en dos niveles:

- **Nivel 1**: Caché en memoria para acceso ultra-rápido
  - Configurable mediante `settings.use_memory_cache`
  - Tamaño máximo y políticas de limpieza configurables
  - Sin persistencia entre reinicios

- **Nivel 2**: Caché en Redis para persistencia y coordinación
  - Persistencia entre reinicios
  - Estado compartido entre múltiples instancias
  - Alta disponibilidad y escalabilidad

### Claves Jerárquicas

El sistema utiliza un modelo jerárquico de claves que permite buscar valores en niveles crecientes de generalidad:

```
{tenant_id}:{data_type}:agent:{agent_id}:conv:{conversation_id}:coll:{collection_id}:{resource_id}
```

La búsqueda jerárquica permite, por ejemplo, encontrar configuraciones a nivel de tenant si no existen a nivel específico de agente o conversación.

## Uso Principal

### Patrón Cache-Aside con `get_with_cache_aside`

Para la mayoría de los casos de uso, se recomienda usar la función `get_with_cache_aside` que implementa el patrón completo:

```python
from common.cache.helpers import get_with_cache_aside

async def get_embedding(text: str, tenant_id: str):
    result, metrics = await get_with_cache_aside(
        data_type="embedding",
        resource_id=generate_resource_id_hash(text),
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_embedding_from_db,
        generate_func=generate_embedding_via_api,
        collection_id=collection_id
    )
    return result
```

Esta función maneja automáticamente:
- Verificación en caché primero
- Búsqueda en base de datos si no está en caché
- Generación del valor si no existe en ninguna parte
- Almacenamiento en caché con TTL apropiado
- Tracking de métricas completo
- Manejo de errores y reintentos

### Operaciones Directas con `CacheManager`

Para operaciones más específicas o cuando no se necesita el patrón completo:

```python
from common.cache.manager import CacheManager

# Obtener valor
value = await CacheManager.get(
    data_type="config",
    resource_id="api_limits",
    tenant_id=tenant_id
)

# Establecer valor
await CacheManager.set(
    data_type="config",
    resource_id="api_limits",
    value=limits_dict,
    tenant_id=tenant_id,
    ttl=3600  # 1 hora
)

# Eliminar valor
await CacheManager.delete(
    data_type="config",
    resource_id="api_limits",
    tenant_id=tenant_id
)
```

## Tipos de Datos y TTL

Cada tipo de datos tiene un TTL (Time To Live) predeterminado configurado en `DEFAULT_TTL_MAPPING`:

| Tipo de Datos | TTL Predeterminado | Descripción |
|---------------|-------------------|-------------|
| embedding     | TTL_EXTENDED      | Embeddings vectoriales |
| query_result  | TTL_STANDARD      | Resultados de consultas |
| agent_config  | TTL_STANDARD      | Configuraciones de agentes |
| vector_store  | TTL_STANDARD      | Referencias a almacenes vectoriales |
| token_counter | TTL_SHORT         | Contadores de tokens |
| system        | TTL_EXTENDED      | Datos del sistema |

## Integración con Otros Sistemas

### Con el Sistema de Contexto

El sistema de caché se integra automáticamente con el sistema de contexto:

```python
@with_context(tenant=True, validate_tenant=True)
async def process_data(ctx: Context = None):
    # CacheManager usa automáticamente el tenant_id del contexto si no se proporciona
    result = await CacheManager.get(
        data_type="config",
        resource_id="settings"
    )
```

### Con el Sistema de Tracking

Todas las operaciones de caché registran métricas automáticamente mediante el sistema centralizado de tracking:

- Hits y misses de caché
- Latencia de operaciones
- Tamaño de objetos en caché
- Errores de serialización/deserialización

## Buenas Prácticas

1. **Usar `get_with_cache_aside` para patrones completos**
   - Proporciona una implementación estandarizada y probada
   - Maneja todos los escenarios, métricas y errores

2. **Definir funciones claras para fetch_from_db y generate**
   - Separar claramente la lógica de obtención de BD y generación

3. **Manejo consistente de tipos de datos**
   - Usar los mismos nombres de data_type en todo el código
   - Respetar los TTL predeterminados por tipo

4. **Validación de Tenant ID**
   - Siempre proporcionar un tenant_id válido (excepto para datos del sistema)
   - Utilizar el sistema de contexto para obtener automáticamente el tenant_id

## Evolución y Migración

Este sistema reemplaza implementaciones anteriores de caché. Si encuentras código utilizando:
- Manipulación directa de Redis
- Patrones de caché específicos por servicio
- Implementaciones personalizadas de Cache-Aside

Debes migrarlos para usar esta implementación centralizada.

## Ejemplos Avanzados

### Invalidación Coordinada

Para invalidar datos relacionados en cascada:

```python
from common.cache.helpers import invalidate_coordinated

await invalidate_coordinated(
    tenant_id=tenant_id,
    primary_data_type="document",
    primary_resource_id=document_id,
    related_invalidations=[
        {"data_type": "embedding", "resource_id": embedding_id},
        {"data_type": "vector_store", "resource_id": collection_id}
    ]
)
```

### Contadores Distribuidos

```python
from common.cache.helpers import increment_counter

await increment_counter(
    counter_type="token_usage",
    tenant_id=tenant_id,
    value=token_count,
    resource_id=model_name
)
```

## Mantenimiento y Extensión

Al extender o modificar este sistema:

1. Mantener la compatibilidad hacia atrás
2. Seguir el patrón de diseño existente
3. Documentar nuevas funcionalidades
4. Asegurar que todos los servicios usen la misma implementación
