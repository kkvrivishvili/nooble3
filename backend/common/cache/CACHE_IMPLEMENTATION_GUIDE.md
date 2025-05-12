# Guía Completa de Implementación del Sistema de Caché

## Visión General del Sistema

El sistema de caché proporciona una capa de abstracción centralizada para operaciones de caché en todos los servicios. Implementa un enfoque multinivel que combina caché en memoria y Redis, siguiendo patrones de diseño robustos para garantizar consistencia, rendimiento y mantenibilidad.

## Arquitectura Detallada

### Componentes Principales

1. **CacheManager** (`manager.py`): 
   - Implementa el patrón Singleton 
   - Proporciona acceso directo a Redis y caché en memoria
   - Ofrece interfaces para operaciones básicas de caché

2. **Helpers** (`helpers.py`):
   - Implementa patrones como Cache-Aside
   - Proporciona funciones para serialización/deserialización
   - Incluye utilidades para invalidación coordinada
   - Estandariza metadatos de LlamaIndex

3. **Constantes** (provenientes de `core.constants`):
   - Define TTLs estándar (TTL_SHORT, TTL_STANDARD, TTL_EXTENDED)
   - Establece tipos de fuentes de datos (SOURCE_CACHE, SOURCE_SUPABASE, etc.)
   - Define tipos de métricas y eventos

## Interfaz del CacheManager

### Métodos Estáticos vs. Métodos de Instancia

El CacheManager implementa dos tipos de métodos:

1. **Métodos Estáticos**: Implementaciones compatibles de alto nivel
   - No requieren una instancia de CacheManager
   - Son la interfaz principal recomendada para la mayoría de usos
   - Ejemplos: `CacheManager.get()`, `CacheManager.set()`, `CacheManager.delete()`

2. **Métodos de Instancia**: Implementaciones internas
   - Accedidos a través de `CacheManager.get_instance()`
   - Implementan la funcionalidad real
   - Acceden a atributos de instancia como `self.settings`
   - Incluyen operaciones especializadas como Redis primitives (listas, sets, etc.)

### Operaciones Básicas

```python
# Operaciones básicas (usar métodos estáticos)
await CacheManager.get(data_type, resource_id, tenant_id, ...)
await CacheManager.set(data_type, resource_id, value, tenant_id, ...)
await CacheManager.delete(data_type, resource_id, tenant_id, ...)
await CacheManager.invalidate(tenant_id, data_type, resource_id, ...)
```

### Operaciones de Listas

**IMPORTANTE**: Las operaciones de listas se acceden a través de la instancia:

```python
# Operaciones de listas (usar métodos de instancia)
await CacheManager.get_instance().rpush(list_name, value, tenant_id)
await CacheManager.get_instance().lpop(list_name, tenant_id)
await CacheManager.get_instance().lrange(list_name, start, end, tenant_id)
```

Esta distinción es crucial. No existen actualmente métodos estáticos como `CacheManager.rpush()`.

## Patrones de Implementación

### Patrón Cache-Aside

El patrón Cache-Aside es la base del sistema de caché. Se implementa mediante `get_with_cache_aside`:

```python
result, metrics = await get_with_cache_aside(
    data_type="document",
    resource_id=document_id,
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_document_from_supabase,
    generate_func=None,  # Opcional: función para generar el recurso si no existe
    ttl=None  # Opcional: usa el TTL predeterminado por tipo si no se especifica
)
```

#### Flujo del Patrón Cache-Aside:

1. **Verificar caché**: Intenta recuperar el dato de la caché multinivel
2. **Si no está en caché**: Llama a `fetch_from_db_func` para obtenerlo de Supabase
3. **Si no está en Supabase**: Opcionalmente llama a `generate_func` si se proporciona
4. **Almacenar en caché**: Guarda el resultado con TTL apropiado
5. **Retornar resultado y métricas**: Devuelve el valor y metadatos sobre la operación

### Estandarización de Metadatos

Para garantizar consistencia en los metadatos de documentos y chunks en todo el sistema RAG, utilizamos `standardize_llama_metadata`:

```python
standardized_metadata = standardize_llama_metadata(
    metadata=node.metadata,
    tenant_id=tenant_id,
    document_id=document_id,
    chunk_id=chunk_id,
    collection_id=collection_id,
    ctx=ctx
)
```

Esta función garantiza que todos los metadatos tengan campos críticos como:
- `tenant_id`: Obligatorio para multitenancy
- `document_id`: Obligatorio para chunks, permite trazabilidad
- `chunk_id`: Identificador único para el fragmento
- `collection_id`: Necesario para caché jerárquica 
- `created_at`: Timestamp generado automáticamente si no existe

## Casos de Uso Específicos

### 1. Descarga de Archivos con Caché

Ejemplo de implementación Cache-Aside para descarga de archivos:

```python
async def download_file_from_storage(tenant_id: str, file_key: str, ctx: Context = None) -> str:
    # Generar clave de caché consistente
    cache_key = generate_resource_id_hash(file_key)
    
    # PASO 1: Verificar si ya tenemos en caché la ubicación de este archivo
    cached_path = await CacheManager.get(
        data_type="file",
        resource_id=cache_key,
        tenant_id=tenant_id
    )
    
    # Si encontramos el archivo en caché y existe en el sistema, retornarlo
    if cached_path and os.path.exists(cached_path):
        return cached_path
    
    # PASO 2: No está en caché o el archivo fue eliminado, descargar de nuevo
    temp_file_path = await download_file_logic(file_key, tenant_id)
    
    # PASO 3: Guardar en caché la ubicación con TTL adecuado
    await CacheManager.set(
        data_type="file",
        resource_id=cache_key,
        value=temp_file_path,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_extended  # 24 horas para archivos
    )
    
    return temp_file_path
```

### 2. Procesamiento de Colas Asíncronas

Para colas de procesamiento, utilizamos operaciones de listas de Redis a través de CacheManager:

```python
# Encolar un trabajo
await CacheManager.get_instance().rpush(
    list_name=f"{tenant_id}:ingestion_queue",
    value=job_data
)

# Obtener el siguiente trabajo de la cola
job = await CacheManager.get_instance().lpop(
    list_name=f"{tenant_id}:ingestion_queue"
)
```

### 3. Tracking de Tokens con Idempotencia

Para rastrear el uso de tokens con prevención de doble conteo:

```python
idempotency_key = f"{tenant_id}:{model}:{collection_id}:{operation}:{hash}"

await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    model=model_name,
    token_type=TOKEN_TYPE_EMBEDDING,
    operation=OPERATION_EMBEDDING,
    metadata={
        "chunk_count": len(chunks),
        "service": "ingestion"
    },
    idempotency_key=idempotency_key
)
```

## Integración con Otros Sistemas

### Integración con Contexto

El sistema integra automáticamente con el contexto de ejecución:

```python
@with_context(tenant=True)
async def process_document(document_id: str, ctx: Context = None):
    # No es necesario extraer tenant_id manualmente
    # CacheManager lo obtendrá del contexto si no se proporciona
    result = await CacheManager.get(data_type="document", resource_id=document_id)
```

### Integración con Supabase

La función `get_with_cache_aside` integra perfectamente con Supabase:

```python
async def fetch_from_supabase(resource_id, tenant_id, ctx):
    supabase = get_supabase_client()
    result = await supabase.table("documents") \
        .select("*") \
        .eq("document_id", resource_id) \
        .eq("tenant_id", tenant_id) \
        .execute()
    return result.data[0] if result.data else None

# Usar con Cache-Aside
document, metrics = await get_with_cache_aside(
    data_type="document",
    resource_id=document_id,
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_from_supabase
)
```

### Integración con Tracking de Tokens

El sistema se integra con el tracking de tokens estandarizado:

```python
from common.tracking import track_token_usage, TOKEN_TYPE_EMBEDDING, OPERATION_EMBEDDING

await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    model=model,
    collection_id=collection_id,
    token_type=TOKEN_TYPE_EMBEDDING,
    operation=OPERATION_EMBEDDING,
    metadata={"service": "ingestion"},
    idempotency_key=idempotency_key
)
```

## Valores de TTL Estándar

El sistema define constantes de TTL estandarizadas:

| Constante       | Valor predeterminado | Uso recomendado                     |
|-----------------|----------------------|-------------------------------------|
| TTL_SHORT       | 300 (5 min)          | Resultados de consultas, cachés temporales |
| TTL_STANDARD    | 3600 (1 hora)        | Configuraciones, documentos, vector stores |
| TTL_EXTENDED    | 86400 (24 horas)     | Embeddings, archivos, recursos costosos |
| TTL_PERMANENT   | None (sin expiración)| Datos permanentes, configuraciones críticas |

## Mejores Prácticas

### Cuándo usar métodos estáticos vs. de instancia

1. **Usar métodos estáticos para operaciones básicas**:
   ```python
   # CORRECTO
   await CacheManager.get(data_type, resource_id, tenant_id)
   await CacheManager.set(data_type, resource_id, value, tenant_id)
   ```

2. **Usar métodos de instancia para operaciones de listas y especializadas**:
   ```python
   # CORRECTO
   await CacheManager.get_instance().rpush(list_name, value)
   await CacheManager.get_instance().lpop(list_name)
   ```

### Cuándo usar get_with_cache_aside vs. CacheManager directo

1. **Usar get_with_cache_aside para el patrón completo**:
   - Cuando necesites implementar el flujo Cache-Aside completo
   - Cuando quieras manejo automático de errores, serialización y métricas

2. **Usar CacheManager directo para operaciones simples**:
   - Cuando solo necesites una operación get/set simple
   - Para operaciones especializadas como listas, contadores, etc.

### Errores Comunes a Evitar

1. **No usar métodos estáticos para operaciones de listas**:
   ```python
   # INCORRECTO - No está implementado
   await CacheManager.rpush(list_name, value)
   
   # CORRECTO
   await CacheManager.get_instance().rpush(list_name, value)
   ```

2. **No olvidar tenant_id**:
   ```python
   # INCORRECTO - Sin tenant_id
   await CacheManager.get(data_type="document", resource_id=doc_id)
   
   # CORRECTO
   await CacheManager.get(data_type="document", resource_id=doc_id, tenant_id=tenant_id)
   ```

3. **No reimplementar patrones existentes**:
   ```python
   # INCORRECTO - Reimplementando el patrón Cache-Aside
   value = await CacheManager.get(data_type, resource_id, tenant_id)
   if not value:
       value = await fetch_from_db(resource_id)
       if value:
           await CacheManager.set(data_type, resource_id, value, tenant_id)
   
   # CORRECTO - Usando el patrón implementado
   value, _ = await get_with_cache_aside(
       data_type=data_type,
       resource_id=resource_id,
       tenant_id=tenant_id,
       fetch_from_db_func=fetch_from_db
   )
   ```

## Ejemplos Completos por Servicio

### Servicio de Ingestion

#### Procesamiento de Colas con Locking

```python
# Adquirir lock para procesamiento exclusivo
lock_acquired = await acquire_job_lock(job_id, tenant_id)
if not lock_acquired:
    logger.info(f"Trabajo {job_id} ya está siendo procesado por otra instancia")
    return False

try:
    # Procesamiento del trabajo
    await process_job(job_id, tenant_id)
finally:
    # Liberar lock en cualquier caso
    await release_job_lock(job_id, tenant_id)
```

#### Implementación de Locks

```python
async def acquire_job_lock(job_id: str, tenant_id: str, expiry_seconds: int = 600) -> bool:
    """Adquiere un lock para un trabajo usando CacheManager."""
    lock_key = f"lock:{job_id}"
    lock_value = str(time.time())
    
    # Usar CacheManager para set con NX (only if not exists)
    result = await CacheManager.get_instance().set_nx(
        key=f"{tenant_id}:job:{lock_key}",
        value=lock_value,
        ex=expiry_seconds
    )
    
    return result is True
```

### Servicio de Embedding

#### Generación de Embeddings con Caché

```python
async def generate_embeddings_for_chunks(chunks, tenant_id, model, collection_id):
    # Preparar textos y IDs para batch
    texts = [chunk["text"] for chunk in chunks]
    chunk_ids = [chunk.get("id") or hashlib.md5(chunk["text"].encode()).hexdigest()[:10] 
                 for chunk in chunks]
    
    # Llamar al servicio centralizado
    response = await call_embedding_service(texts, model, tenant_id)
    
    # Registrar uso de tokens con idempotencia
    idempotency_key = f"{tenant_id}:{model}:{collection_id}:{','.join(chunk_ids)}"
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=response.get("token_usage", 0),
        model=model,
        collection_id=collection_id,
        token_type=TOKEN_TYPE_EMBEDDING,
        operation=OPERATION_EMBEDDING,
        metadata={"chunk_count": len(chunks)},
        idempotency_key=idempotency_key
    )
    
    # Añadir embeddings a los chunks
    for i, chunk in enumerate(chunks):
        chunk["embedding"] = response["embeddings"][i]
    
    return chunks
```

### Servicio de Query

#### Búsqueda Semántica con Cache-Aside

```python
async def search_collection(query, collection_id, tenant_id, top_k=5):
    # Generar ID único para esta consulta
    query_id = generate_resource_id_hash(f"{query}:{collection_id}:{top_k}")
    
    # Usar el patrón Cache-Aside para búsquedas
    result, metrics = await get_with_cache_aside(
        data_type="query_result",
        resource_id=query_id,
        tenant_id=tenant_id,
        fetch_from_db_func=None,  # No hay búsqueda en BD
        generate_func=lambda *args: perform_vector_search(query, collection_id, tenant_id, top_k),
        collection_id=collection_id,
        ttl=TTL_SHORT  # Resultados de búsqueda expiran rápido
    )
    
    return result
```

## Diagnóstico y Solución de Problemas

### Síntomas Comunes y Soluciones

1. **Problema**: Valores esperados no están en caché
   **Solución**: Verificar que TTL no sea demasiado corto, que la clave de caché sea consistente, y que Redis esté funcionando

2. **Problema**: Errores al acceder a métodos de Redis
   **Solución**: Verificar que se está usando la interfaz correcta (instancia vs. estática)

3. **Problema**: Metadatos inconsistentes entre servicios
   **Solución**: Verificar que se está usando `standardize_llama_metadata` en todos los servicios

### Añadiendo Nuevas Funcionalidades

Para añadir nuevas funcionalidades al sistema de caché:

1. **Añadir método de instancia**: Implementar en la clase CacheManager
2. **Añadir método estático**: Crear wrapper estático que llama al método de instancia
3. **Añadir funciones helper**: Para patrones complejos, añadir al módulo helpers.py
4. **Documentar**: Actualizar este manual con ejemplos y guías

## Conclusión

Este sistema de caché proporciona una base sólida para todas las operaciones de caché en el sistema RAG. Siguiendo estas guías, podrás implementar de forma consistente y eficiente las operaciones de caché en todos los servicios, manteniendo un enfoque unificado que garantiza rendimiento, escalabilidad y mantenibilidad.
