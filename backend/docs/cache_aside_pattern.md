# Patrón Cache-Aside en el Sistema RAG

## Introducción

Este documento describe la implementación estandarizada del patrón Cache-Aside para optimizar el rendimiento y la escalabilidad del sistema RAG (Retrieval Augmented Generation) a través de sus cuatro servicios principales: ingestion, embedding, query y agent.

## ¿Qué es el Patrón Cache-Aside?

El patrón Cache-Aside es una estrategia de caché donde la aplicación es responsable de cargar datos en la caché y recuperarlos de ella. La aplicación busca primero datos en la caché; si no están disponibles, los obtiene de la fuente de datos original y los almacena en la caché para futuras consultas.

## Diagrama de Flujo

```
┌───────────────┐     No     ┌───────────────┐      No      ┌───────────────┐
│  ¿Dato en     │─────────►│  ¿Dato en     │──────────►│   Generar     │
│    Caché?     │            │   Supabase?   │             │    Dato       │
└───────┬───────┘            └───────┬───────┘             └───────┬───────┘
        │                            │                             │
        │ Sí                         │ Sí                          │
        ▼                            ▼                             │
┌───────────────┐            ┌───────────────┐                     │
│   Retornar    │            │   Guardar en  │◄────────────────────┘
│    Dato       │            │    Caché      │
└───────────────┘            └───────┬───────┘
                                     │
                                     ▼
                             ┌───────────────┐
                             │   Retornar    │
                             │    Dato       │
                             └───────────────┘
```

## Implementación en el Sistema RAG

### 1. Principios Clave

1. **Consistencia en todos los servicios**: Mismo enfoque en ingestion, embedding, query, y agent
2. **Uso estricto de funciones comunes**: Utilizar funciones como `get_table_name()` y `get_supabase_client()`
3. **Jerarquía de búsqueda en caché**: De lo más específico a lo más general
4. **Fallback a Supabase**: Cuando no hay datos en caché, buscar en la base de datos
5. **Métricas unificadas**: Seguimiento consistente del rendimiento de caché
6. **Centralización de configuraciones**: Todos los valores de TTL y configuraciones provienen de `common/config/settings.py`

### 2. Implementación Centralizada

Para estandarizar el patrón y evitar inconsistencias, se ha implementado una solución centralizada en `common/cache/helpers.py` que proporciona las siguientes funcionalidades:

#### Funciones Principales

```python
from common.cache import (
    CacheManager,                  # Gestor centralizado de caché
    get_with_cache_aside,          # Implementación completa del patrón
    invalidate_resource_cache,     # Invalidación simple de un recurso
    invalidate_coordinated,        # Invalidación coordinada de recursos relacionados
    invalidate_document_update,    # Invalidación específica para actualizaciones de documentos
    track_cache_metrics,           # Función unificada para métricas de caché
    serialize_for_cache,           # Serializador para diferentes tipos de datos 
    deserialize_from_cache,        # Deserializador para diferentes tipos de datos
    generate_resource_id_hash,     # Generador de identificadores consistentes
    DEFAULT_TTL_MAPPING,           # Mapeo de tipos de datos a TTL predeterminados
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT  # Constantes TTL centralizadas
)
```

#### Función Central: `get_with_cache_aside`

Esta función implementa el patrón completo:

```python
async def get_with_cache_aside(
    data_type: str,                      # Tipo de dato (embedding, vector_store, etc.)
    resource_id: str,                    # ID único del recurso
    tenant_id: str,                      # ID del tenant
    fetch_from_db_func: Callable,        # Función para buscar en Supabase
    generate_func: Optional[Callable],   # Función para generar el dato (opcional)
    agent_id: Optional[str] = None,      # ID del agente (opcional)
    conversation_id: Optional[str] = None, # ID de conversación (opcional) 
    collection_id: Optional[str] = None, # ID de colección (opcional)
    ctx: Optional[Context] = None,       # Contexto (opcional)
    ttl: Optional[int] = None,           # TTL personalizado (opcional)
    serializer: Optional[Callable] = None, # Función de serialización personalizada
    deserializer: Optional[Callable] = None # Función de deserialización personalizada
) -> Tuple[Optional[T], Dict[str, Any]]: # Dato y métricas
    """
    Implementación centralizada del patrón Cache-Aside para el sistema RAG.
    
    Sigue el flujo estándar:
    1. Verificar caché primero
    2. Si no está en caché, buscar en Supabase mediante fetch_from_db_func
    3. Si no está en BD, generar dato (si se proporciona generate_func)
    4. Almacenar en caché con TTL adecuado según el tipo de dato
    5. Retornar dato con métricas unificadas del proceso
    
    Este método garantiza consistencia en la implementación del patrón en
    todos los servicios (ingestion, embedding, query, agent).
    
    Returns:
        Tuple[Optional[T], Dict[str, Any]]: 
            - El dato solicitado o None si no se encuentra
            - Diccionario con métricas de rendimiento
    """
```

### 3. TTL Estándarizados

Los tiempos de vida para diferentes tipos de datos están centralizados en `common/config/settings.py` y se accede a ellos a través del mapeo en `common/cache/__init__.py`:

| Tipo de Dato | Constante | Duración | Descripción |
|--------------|-----------|----------|-------------|
| Embeddings | `TTL_EXTENDED` | 24 horas | Datos altamente estables |
| Vector Stores | `TTL_STANDARD` | 1 hora | Datos moderadamente estables |
| Query Results | `TTL_SHORT` | 5 minutos | Datos volátiles |
| Agent Configs | `TTL_STANDARD` | 1 hora | Datos moderadamente estables |
| Agent Responses | `TTL_SHORT` | 5 minutos | Datos volátiles |
| Conversation | `TTL_STANDARD` | 1 hora | Datos moderadamente estables |
| Document | `TTL_STANDARD` | 1 hora | Datos moderadamente estables |
| Retrieval Cache | `TTL_SHORT` | 5 minutos | Resultados de recuperación volátiles |
| Embedding Batch | `TTL_EXTENDED` | 24 horas | Lotes de embeddings estables |
| Semantic Index | `TTL_STANDARD` | 1 hora | Índices semánticos moderadamente estables |
| Default | `TTL_STANDARD` | 1 hora | Valor por defecto |

### 4. Serialización Consistente de Tipos Específicos

La función `serialize_for_cache` asegura la consistencia en la serialización para todos los servicios:

#### Embeddings

```python
# Los embeddings se serializan automáticamente a listas planas de Python
if data_type == "embedding":
    # Conversión automática desde numpy arrays
    if 'numpy' in str(type(value)) and hasattr(value, 'tolist'):
        return value.tolist()
    
    # Conversión automática desde tensores PyTorch
    if 'torch' in str(type(value)) and hasattr(value, 'detach') and hasattr(value, 'cpu') and hasattr(value, 'numpy'):
        return value.detach().cpu().numpy().tolist()
    
    # Conversión automática desde tensores TensorFlow
    if 'tensorflow' in str(type(value)) and hasattr(value, 'numpy'):
        return value.numpy().tolist()
        
    # Si ya es una lista, asegurarse de que los valores son nativos de Python
    if isinstance(value, list):
        # Verificar si hay floats32 o tipos similares de numpy
        if value and hasattr(value[0], 'item') and callable(value[0].item):
            return [float(v.item()) if hasattr(v, 'item') else float(v) for v in value]
        return value
```

### 5. Invalidación Coordinada

El sistema proporciona mecanismos para invalidación inteligente cuando se actualizan recursos:

#### Invalidación de Actualizaciones de Documentos

```python
async def invalidate_document_update(
    tenant_id: str,
    document_id: str,
    collection_id: Optional[str] = None
) -> Dict[str, int]:
    """
    Invalidación especializada para actualizaciones de documentos en el sistema RAG.
    
    Cuando se actualiza un documento, esta función invalida automáticamente:
    1. La caché del documento mismo
    2. Los embeddings relacionados con el documento
    3. El vector store de la colección
    4. Las consultas que pudieron haber usado ese documento
    
    Esta invalidación coordinada mantiene la consistencia del sistema
    después de actualizaciones, asegurando que no se usen datos obsoletos.
    """
    # Preparar invalidaciones relacionadas
    invalidations = [
        {"data_type": "embedding", "resource_id": f"doc:{document_id}"},
        {"data_type": "retrieval_cache", "resource_id": "*"}
    ]
    
    # Añadir invalidación del vector store si tenemos collection_id
    if collection_id:
        invalidations.append({"data_type": "vector_store", "resource_id": collection_id})
        invalidations.append({"data_type": "semantic_index", "resource_id": collection_id})
    
    # Usar la función de invalidación coordinada existente
    return await invalidate_coordinated(
        tenant_id=tenant_id,
        primary_data_type="document",
        primary_resource_id=document_id,
        related_invalidations=invalidations,
        collection_id=collection_id
    )
```

### 6. Métricas Unificadas

Se ha implementado una función centralizada `track_cache_metrics` que unifica el registro de todas las métricas relacionadas con caché:

```python
await track_cache_metrics(
    data_type="vector_store",
    tenant_id=tenant_id,
    metric_type=METRIC_CACHE_HIT,  # o METRIC_CACHE_MISS, METRIC_LATENCY, METRIC_CACHE_SIZE
    value=True,                    # o latencia en ms, tamaño en bytes
    metadata={"source": SOURCE_CACHE}
)
```

## Implementación en Servicios

### Ejemplo Estandarizado de Uso

```python
from common.cache import (
    CacheManager, 
    get_with_cache_aside,
    invalidate_document_update
)

# Ejemplo de uso básico:
async def get_document_embedding(doc_id: str, tenant_id: str):
    # Definir la función para buscar en Supabase
    async def fetch_embedding_from_db(resource_id, tenant_id, ctx):
        # Lógica específica para buscar embeddings en Supabase
        client = await get_supabase_client(tenant_id)
        # Resto de lógica...
        return result
    
    # Definir la función para generar si no existe
    async def generate_embedding_if_needed(resource_id, tenant_id, ctx):
        # Lógica para generar embeddings
        return embedding_result
    
    # Usar el patrón Cache-Aside centralizado
    result, metrics = await get_with_cache_aside(
        data_type="embedding",
        resource_id=f"doc:{doc_id}",
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_embedding_from_db,
        generate_func=generate_embedding_if_needed
    )
    return result

# Ejemplo con invalidación coordinada:
async def update_document(doc_id: str, tenant_id: str, collection_id: str, content: str):
    # Actualizar en la base de datos
    await update_document_in_db(doc_id, tenant_id, content)
    
    # Invalidar todas las cachés relacionadas
    invalidation_results = await invalidate_document_update(
        tenant_id=tenant_id,
        document_id=doc_id,
        collection_id=collection_id
    )
    
    return invalidation_results
```

## Buenas Prácticas

1. **No Usar TTL Hardcodeados**: Permitir la asignación automática por tipo de datos
2. **Validar tenant_id y resource_id**: Usar comprobaciones explícitas de parámetros obligatorios
3. **Manejar Errores de Serialización**: Capturar excepciones y registrarlas en métricas
4. **Seguir Jerarquía de Claves**: Proporcionar contexto como agent_id y collection_id cuando estén disponibles
5. **Implementar Invalidación Coordinada**: Usar `invalidate_document_update` para mantener consistencia

## Conclusión

La implementación estandarizada del patrón Cache-Aside proporciona un enfoque coherente y eficiente para la caché en todo el sistema RAG, mejorando significativamente el rendimiento y la escalabilidad mientras mantiene la consistencia de los datos.
