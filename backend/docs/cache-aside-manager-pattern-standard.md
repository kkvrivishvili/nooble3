
# Estándar del Patrón Cache-Aside

**Tags:** `#cache` `#performance` `#pattern` `#multitenancy` `#redis`

## 1. Principios Fundamentales

**Tags:** `#principles` `#core_concepts`

1. **Consistencia en todos los servicios**: Mismo enfoque de caché para embedding, query, agent e ingestion
2. **Uso del patrón Cache-Aside**: Verificar caché primero, si no está obtener de base de datos, si no existe generar
3. **Jerarquía de búsqueda en caché**: Desde lo más específico a lo más general
4. **Fallback a Supabase**: Cuando no hay datos en caché, buscar en la base de datos
5. **Métricas unificadas**: Seguimiento consistente de rendimiento (hits, misses, latencia)
6. **Serialización estandarizada**: Reglas consistentes para serializar diferentes tipos de datos

## 2. Estructura y Componentes

**Tags:** `#architecture` `#components`

### 2.1 Estructura de Módulos

```
common/cache/
├── __init__.py      # Exportaciones y constantes TTL
├── manager.py       # Implementación de CacheManager
└── helpers.py       # Funciones de implementación de Cache-Aside
```

### 2.2 Componentes Principales

1. **CacheManager**: Clase para gestión centralizada de caché (Redis + memoria)
2. **get_with_cache_aside**: Función principal para implementar el patrón
3. **Funciones de serialización**: Para garantizar consistencia entre servicios
4. **Funciones de invalidación**: Para mantener consistencia de datos
5. **Funciones de métricas**: Para monitoreo del rendimiento

### 2.3 Importaciones Correctas

```python
# ✅ CORRECTO - Importar desde el módulo principal
from common.cache import (
    CacheManager, get_with_cache_aside,
    serialize_for_cache, TTL_STANDARD,
    invalidate_document_update
)

# ❌ INCORRECTO - No importar desde submódulos internos
from common.cache.manager import CacheManager  # Evitar
```

## 3. Patrón Principal - get_with_cache_aside

**Tags:** `#primary_pattern` `#implementation`

### 3.1 Flujo del Patrón Cache-Aside

```
1. VERIFICAR CACHÉ
   |
   +-- ACIERTO --> Retornar dato + métricas
   |
   +-- FALLO --> Buscar en Supabase mediante fetch_from_db_func
                 |
                 +-- ENCONTRADO --> Guardar en caché con TTL --> Retornar
                 |
                 +-- NO ENCONTRADO --> Generar dato mediante generate_func
                                       --> Guardar en caché --> Retornar
```

### 3.2 Implementación Recomendada

**Tags:** `#recommended_usage` `#example`

```python
from common.cache import get_with_cache_aside, TTL_STANDARD
from common.db.supabase import get_supabase_client

async def get_document_metadata(document_id: str, tenant_id: str, ctx=None):
    # Función para buscar en Supabase
    async def fetch_from_db(resource_id, tenant_id, ctx):
        client = await get_supabase_client(tenant_id)
        table = get_table_name("documents")
        result = await client.table(table).select("*").eq("document_id", resource_id).execute()
        return result.data[0] if result.data else None
    
    # Función para generar el dato si no existe (opcional)
    async def generate_if_needed(resource_id, tenant_id, ctx):
        # Si no hay generación posible, retornar None
        return None
    
    # Usar el patrón Cache-Aside centralizado
    result, metrics = await get_with_cache_aside(
        data_type="document",
        resource_id=document_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_from_db,
        generate_func=generate_if_needed,  # Opcional, puede ser None
        ctx=ctx
    )
    
    # Si necesitas las métricas para telemetría
    if metrics["source"] == "cache":
        logger.debug(f"Cache hit para documento {document_id}")
    
    return result
```

### 3.3 Parámetros Importantes

**Tags:** `#parameters` `#configuration`

```python
await get_with_cache_aside(
    data_type="embedding",          # Tipo de datos para TTL automático
    resource_id="doc_123",          # Identificador único del recurso
    tenant_id="tenant_abc",         # ID del tenant (obligatorio)
    fetch_from_db_func=fetch_func,  # Función para buscar en BD (obligatorio)
    generate_func=generate_func,    # Función para generar (opcional)
    agent_id="agent_456",           # Contexto adicional (opcional)
    conversation_id="conv_789",     # Contexto adicional (opcional)
    collection_id="coll_101112",    # Contexto adicional (opcional)
    ctx=ctx,                        # Objeto Context (opcional)
    ttl=3600,                       # TTL personalizado (opcional)
    serializer=None,                # Función serialización personalizada
    deserializer=None               # Función deserialización personalizada
)
```

## 4. Clase CacheManager

**Tags:** `#cache_manager` `#core_implementation`

### 4.1 Patrón Singleton

**Tags:** `#singleton` `#design_pattern`

```python
# Obtener la instancia singleton
cache_manager = CacheManager.get_instance()

# O usar los métodos estáticos compatibles
await CacheManager.get(data_type="document", resource_id="doc_123", tenant_id="tenant_abc")
```

### 4.2 Métodos Principales

**Tags:** `#core_methods` `#basic_operations`

```python
# Operaciones básicas de caché
await CacheManager.get(data_type, resource_id, tenant_id, ...)
await CacheManager.set(data_type, resource_id, value, tenant_id, ...)
await CacheManager.invalidate(tenant_id, data_type, resource_id, ...)
await CacheManager.delete(data_type, resource_id, tenant_id, ...)

# Operaciones específicas para tipos comunes
await CacheManager.get_embedding(text, model_name, tenant_id)
await CacheManager.set_embedding(text, embedding, model_name, tenant_id)
await CacheManager.get_query_result(query, collection_id, tenant_id, ...)
await CacheManager.set_query_result(query, result, collection_id, tenant_id, ...)
await CacheManager.get_agent_config(agent_id, tenant_id)
await CacheManager.set_agent_config(agent_id, config, tenant_id)
```

### 4.3 Estructura de Claves

**Tags:** `#key_structure` `#hierarchy`

Las claves de caché siguen una estructura jerárquica:

```
tenant_id:data_type:agent:agent_id:conv:conversation_id:coll:collection_id:resource_id
```

**Ejemplo**: `tenant_abc:embedding:agent:agent_123:doc_456`

La búsqueda jerárquica sigue este orden:
1. Clave completa con todos los parámetros
2. Claves intermedias con combinaciones de parámetros
3. Clave básica solo con tenant_id

### 4.4 Caché Multinivel

**Tags:** `#multilevel_cache` `#performance`

El sistema utiliza automáticamente:

1. **Caché en memoria**: Para acceso ultra-rápido sin latencia de red
2. **Caché en Redis**: Para persistencia y coordinación entre servicios

## 5. TTL Estándarizados

**Tags:** `#ttl` `#expiration` `#constants`

### 5.1 Constantes Predefinidas

```python
from common.cache import TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT

# TTL_SHORT: 300 (5 minutos) - Para datos volátiles
# TTL_STANDARD: 3600 (1 hora) - Para la mayoría de los datos
# TTL_EXTENDED: 86400 (24 horas) - Para datos muy estables
# TTL_PERMANENT: 0 (sin expiración) - Para datos permanentes
```

### 5.2 TTL por Tipo de Datos

El sistema asigna automáticamente TTL según el tipo de datos:

| Tipo de Dato | TTL | Descripción |
|--------------|-----|-------------|
| embedding | TTL_EXTENDED | Embeddings son estables a largo plazo |
| vector_store | TTL_STANDARD | Stores pueden cambiar con frecuencia moderada |
| query_result | TTL_SHORT | Resultados de consultas son más volátiles |
| agent_config | TTL_STANDARD | Configuraciones relativamente estables |
| agent_response | TTL_SHORT | Respuestas pueden cambiar frecuentemente |
| retrieval_cache | TTL_SHORT | Resultados de recuperación son volátiles |
| semantic_index | TTL_STANDARD | Índices relativamente estables |

## 6. Serialización y Deserialización

**Tags:** `#serialization` `#format` `#data_types`

### 6.1 Funciones Centralizadas

```python
from common.cache import serialize_for_cache, deserialize_from_cache

# Serializar según tipo
cached_value = serialize_for_cache(original_value, "embedding")

# Deserializar según tipo
original_value = deserialize_from_cache(cached_value, "embedding")
```

### 6.2 Reglas para Embeddings

**Tags:** `#embeddings` `#vectors`

La serialización de embeddings sigue estas reglas:

```python
# Numpy arrays -> listas Python planas
if hasattr(value, 'tolist'):
    return value.tolist()

# Tensores PyTorch
if 'torch' in str(type(value)) and hasattr(value, 'detach'):
    return value.detach().cpu().numpy().tolist()

# Tensores TensorFlow
if 'tensorflow' in str(type(value)) and hasattr(value, 'numpy'):
    return value.numpy().tolist()
```

### 6.3 Serialización Personalizada

**Tags:** `#custom_serialization` `#extension`

Para tipos de datos complejos:

```python
async def get_complex_data(data_id, tenant_id):
    # Funciones de serialización específicas
    def custom_serializer(value):
        # Lógica específica para este tipo
        return {"serialized": True, "data": value.to_dict()}
    
    def custom_deserializer(cached_value):
        # Convertir de vuelta al tipo original
        return CustomClass.from_dict(cached_value["data"])
    
    result, metrics = await get_with_cache_aside(
        data_type="complex_data",
        resource_id=data_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_from_db,
        serializer=custom_serializer,
        deserializer=custom_deserializer
    )
    return result
```

## 7. Invalidación de Caché

**Tags:** `#invalidation` `#consistency` `#cache_management`

### 7.1 Invalidación Simple

**Tags:** `#simple_invalidation` `#basic`

```python
# Invalida una entrada específica
await CacheManager.invalidate(
    tenant_id="tenant_abc",
    data_type="document",
    resource_id="doc_123"
)

# Invalida todas las entradas de un tipo
await CacheManager.invalidate(
    tenant_id="tenant_abc",
    data_type="document",
    resource_id="*"  # Comodín para todas las entradas
)
```

### 7.2 Invalidación Coordinada

**Tags:** `#coordinated_invalidation` `#complex`

Para mantener consistencia cuando se actualiza un recurso que afecta a otros:

```python
from common.cache import invalidate_document_update

# Actualiza documentos o chunks
await update_document_in_db(document_id, content)

# Invalida todas las cachés relacionadas
await invalidate_document_update(
    tenant_id="tenant_abc",
    document_id="doc_123",
    collection_id="coll_456"
)
```

Esta función realiza invalidación coordinada:
1. La caché del documento mismo
2. Los embeddings relacionados con el documento
3. El vector store de la colección
4. Las consultas que pudieron haber usado ese documento

### 7.3 Invalidación Completa

**Tags:** `#complete_invalidation` `#reset`

```python
# Invalida toda la caché de un agente
await CacheManager.invalidate_agent_complete(
    tenant_id="tenant_abc",
    agent_id="agent_123"
)

# Invalida toda la caché de una colección
await CacheManager.invalidate_collection_complete(
    tenant_id="tenant_abc", 
    collection_id="coll_456"
)
```

## 8. Optimización para Lotes (Batch)

**Tags:** `#batch_processing` `#optimization`

### 8.1 Embeddings en Lote

**Tags:** `#batch_embeddings` `#vectors`

```python
from common.cache import get_embeddings_batch_with_cache

# Procesar múltiples textos eficientemente
embeddings, metrics = await get_embeddings_batch_with_cache(
    texts=["texto1", "texto2", "texto3"],
    tenant_id="tenant_abc",
    model_name="text-embedding-ada-002",
    embedding_provider=generate_embeddings_batch  # Función que genera embeddings en lote
)

# Métricas específicas de lote
print(f"Cache hits: {metrics['cache_hits']}")
print(f"Cache misses: {metrics['cache_misses']}")
```

La función batch:
1. Consulta la caché para todos los textos a la vez
2. Identifica sólo aquellos que necesitan generación
3. Genera embeddings únicamente para esos textos
4. Combina los resultados de caché y generación
5. Almacena los nuevos embeddings en caché

## 9. Métricas y Monitoreo

**Tags:** `#metrics` `#monitoring` `#observability`

### 9.1 Métricas Integradas

**Tags:** `#integrated_metrics` `#tracking`

El sistema registra automáticamente:

```python
# Estas métricas se generan automáticamente en get_with_cache_aside
METRIC_CACHE_HIT      # Aciertos de caché
METRIC_CACHE_MISS     # Fallos de caché
METRIC_LATENCY        # Tiempos de respuesta
METRIC_CACHE_SIZE     # Tamaño de datos en caché
```

### 9.2 Métricas Personalizadas

**Tags:** `#custom_metrics` `#extension`

```python
from common.cache import track_cache_metrics

# Registrar una métrica personalizada
await track_cache_metrics(
    data_type="embedding",
    tenant_id="tenant_abc",
    metric_type="custom_metric_name",
    value=35.7,  # Valor numérico
    metadata={"source": "mi_servicio", "operation": "custom_op"}
)
```

### 9.3 Contadores para Métricas Complejas

**Tags:** `#counters` `#aggregation`

```python
# Incrementar un contador para seguimiento a largo plazo
await CacheManager.increment_counter(
    counter_type="api_calls",
    amount=1,
    resource_id="my_endpoint",
    tenant_id="tenant_abc",
    metadata={"status": "success"}
)

# Obtener el valor actual
count = await CacheManager.get_counter(
    scope="api_calls",
    resource_id="my_endpoint",
    tenant_id="tenant_abc"
)
```

## 10. Integración con Sistema de Contexto

**Tags:** `#context_integration` `#multitenancy`

### 10.1 Uso con Sistema de Contexto

**Tags:** `#context_system` `#with_context`

```python
@with_context(tenant=True, agent=True)
async def my_function(ctx: Context):
    # El tenant_id y agent_id se toman automáticamente del contexto
    result, metrics = await get_with_cache_aside(
        data_type="my_data",
        resource_id="resource_id",
        tenant_id=ctx.get_tenant_id(),  # Del contexto validado
        agent_id=ctx.get_agent_id(),    # Del contexto
        fetch_from_db_func=fetch_from_db
    )
    return result
```

### 10.2 Jerarquía de Búsqueda con Contexto

**Tags:** `#search_hierarchy` `#context_awareness`

Cuando se proporcionan elementos de contexto, la búsqueda inteligente sigue este orden:

1. `tenant_id:data_type:agent:agent_id:conv:conv_id:coll:coll_id:resource_id`
2. `tenant_id:data_type:agent:agent_id:conv:conv_id:resource_id`
3. `tenant_id:data_type:agent:agent_id:coll:coll_id:resource_id`
4. `tenant_id:data_type:coll:coll_id:resource_id`
5. `tenant_id:data_type:agent:agent_id:resource_id`
6. `tenant_id:data_type:resource_id`

## 11. Casos de Uso Comunes

**Tags:** `#use_cases` `#examples` `#patterns`

### 11.1 Embeddings

**Tags:** `#embeddings_use_case` `#vectors`

```python
# Usando el método especializado
embedding = await CacheManager.get_embedding(
    text="Texto a embeber",
    model_name="text-embedding-ada-002",
    tenant_id="tenant_abc"
)

if not embedding:
    # Si no está en caché, generarlo
    embedding = await embedding_provider.embed(text)
    
    # Guardarlo en caché
    await CacheManager.set_embedding(
        text="Texto a embeber",
        embedding=embedding,
        model_name="text-embedding-ada-002",
        tenant_id="tenant_abc"
    )
```

### 11.2 Resultados de Consultas

**Tags:** `#query_results` `#rag`

```python
# Usando el método especializado
result = await CacheManager.get_query_result(
    query="¿Cómo funciona X?",
    collection_id="coll_123",
    tenant_id="tenant_abc",
    similarity_top_k=4
)

if not result:
    # Si no está en caché, ejecutar la consulta
    result = await execute_query(query, collection_id, similarity_top_k)
    
    # Guardar en caché
    await CacheManager.set_query_result(
        query="¿Cómo funciona X?",
        result=result,
        collection_id="coll_123",
        tenant_id="tenant_abc",
        similarity_top_k=4
    )
```

### 11.3 Configuración de Agentes

**Tags:** `#agent_config` `#settings`

```python
# Usando el método especializado
config = await CacheManager.get_agent_config(
    agent_id="agent_123",
    tenant_id="tenant_abc"
)

if not config:
    # Si no está en caché, cargar desde BD
    config = await load_agent_config_from_db(agent_id, tenant_id)
    
    # Guardar en caché
    await CacheManager.set_agent_config(
        agent_id="agent_123",
        config=config,
        tenant_id="tenant_abc"
    )
```

## 12. Buenas Prácticas y Recomendaciones

**Tags:** `#best_practices` `#recommendations`

### 12.1 Uso del Patrón Cache-Aside

**Tags:** `#pattern_usage` `#consistency`

1. **Usar get_with_cache_aside**: Para implementación consistente en todos los servicios
2. **Proporcionar funciones específicas**: Crear funciones fetch_from_db y generate_func claras
3. **Manejar None adecuadamente**: Tratar valores nulos de manera explícita

### 12.2 Organización de Código

**Tags:** `#code_organization` `#structure`

1. **Centralizar lógica de caché**: No reimplementar el patrón en cada servicio
2. **Separar lógica de negocio**: Las funciones fetch_from_db y generate_func deben contener solo lógica específica
3. **Manejar errores**: Capturar y manejar errores de caché sin interrumpir operaciones

### 12.3 Rendimiento

**Tags:** `#performance` `#optimization`

1. **TTL adecuados**: Usar los TTL recomendados por tipo de dato
2. **Granularidad correcta**: Cachear a nivel adecuado (ni demasiado fino ni demasiado grueso)
3. **Invalidación específica**: Evitar invalidar más de lo necesario
4. **Usar procesamiento por lotes**: Para operaciones intensivas como embeddings

### 12.4 Seguridad

**Tags:** `#security` `#isolation`

1. **Aislamiento por tenant**: Las claves siempre incluyen tenant_id para garantizar aislamiento
2. **No almacenar datos sensibles**: Evitar almacenar información sensible en caché
3. **Validar tenant_id**: Asegurarse de que sea válido antes de acceder a caché

## 13. Solución de Problemas

**Tags:** `#troubleshooting` `#debugging`

### 13.1 Pérdida de Datos en Caché

**Tags:** `#data_loss` `#debugging`

Si los datos desaparecen de la caché antes de lo esperado:

1. Verificar TTL con `await CacheManager.ttl("data_type", "resource_id", "tenant_id")`
2. Revisar si hubo invalidación coordinada
3. Comprobar que Redis está funcionando correctamente

### 13.2 Datos Inconsistentes

**Tags:** `#consistency_issues` `#data_integrity`

Si los datos en caché no coinciden con la base de datos:

1. Verificar invalidación después de actualizaciones
2. Implementar la función invalidate_document_update para objetos actualizados
3. Usar funciones de serialización consistentes

### 13.3 Problemas de Rendimiento

**Tags:** `#performance_issues` `#latency`

Si la caché no mejora el rendimiento como se esperaba:

1. Verificar métricas de tasa de aciertos vs. fallos
2. Examinar la latencia de diferentes fuentes de datos
3. Ajustar TTL para maximizar aciertos sin comprometer consistencia
