# Patrón Cache-Aside en el Sistema RAG

## Introducción

Este documento describe la implementación del patrón Cache-Aside para optimizar el rendimiento y la escalabilidad del sistema RAG (Retrieval Augmented Generation) a través de sus cuatro servicios principales: ingestion, embedding, query y agent.

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
2. **Uso estricto de funciones comunes**: Utilizar functions como `get_table_name()` y `get_supabase_client()`
3. **Jerarquía de búsqueda en caché**: De lo más específico a lo más general
4. **Fallback a Supabase**: Cuando no hay datos en caché, buscar en la base de datos
5. **Métricas unificadas**: Seguimiento consistente del rendimiento de caché

### 2. Estructura del Código

Cada implementación del patrón sigue esta estructura:

```python
async def get_data(resource_id, tenant_id, ctx=None):
    # 1. Verificar caché primero
    start_time = time.time()
    cached_data = await CacheManager.get(
        data_type="data_type", 
        resource_id=resource_id,
        tenant_id=tenant_id
    )
    
    if cached_data:
        # Registrar hit y métrica
        await track_cache_hit("data_type", tenant_id, True)
        return cached_data
    
    # Registrar miss
    await track_cache_hit("data_type", tenant_id, False)
        
    # 2. Si no está en caché, recuperar de Supabase
    supabase = get_supabase_client()
    table_name = get_table_name("table_name")
    
    result = await supabase.table(table_name)
        .select("*")
        .eq("id", resource_id)
        .execute()
    
    if result.data:
        data = result.data[0]
        
        # 3. Guardar en caché para futuras consultas
        await CacheManager.set(
            data_type="data_type",
            resource_id=resource_id,
            tenant_id=tenant_id,
            value=data,
            ttl=CacheManager.ttl_standard
        )
        
        return data
        
    # 4. Si no existe, generar si es posible
    # (específico para ciertos tipos de datos como embeddings)
```

### 3. Estándares de TTL por Tipo de Dato

Para mantener consistencia en todo el sistema, se utilizan los siguientes TTL estandarizados:

| Tipo de Dato | TTL Constante | Duración |
|--------------|---------------|----------|
| Embeddings | `CacheManager.ttl_extended` | 24 horas |
| Vector Stores | `CacheManager.ttl_standard` | 1 hora |
| Query Results | `CacheManager.ttl_short` | 15 minutos |
| Agent Configs | `CacheManager.ttl_standard` | 1 hora |

### 4. Métricas y Monitoreo

Cada implementación del patrón registra métricas para analizar rendimiento:

1. **Hit/Miss Rate**: Porcentaje de aciertos vs fallos en caché
2. **Latencia**: Tiempo para recuperar datos de diferentes fuentes
3. **Tamaño**: Espacio ocupado en caché por tipo de dato

Funciones auxiliares para métricas:

```python
async def track_cache_hit(data_type, tenant_id, hit):
    """Registra aciertos/fallos de caché"""
    
async def track_cache_metric(data_type, tenant_id, source, latency_ms):
    """Registra latencia de acceso a datos"""
    
async def track_cache_size(data_type, tenant_id, size_bytes):
    """Registra el tamaño en caché"""
```

## Implementación Específica por Servicio

### Embedding Service

- **Caso de uso**: Generación eficiente de embeddings vectoriales
- **Peculiaridades**: Verificación en tres niveles (caché, base de datos, generación)
- **Beneficio principal**: Reducción significativa de llamadas a APIs de embeddings

```python
# Ejemplo simplificado de llama_index_utils.generate_embeddings_with_llama_index()
```

### Query Service

- **Caso de uso**: Acceso rápido a vector stores para consultas
- **Peculiaridades**: Invalidación coordinada entre vector stores y queries relacionadas
- **Beneficio principal**: Respuestas más rápidas para consultas similares

```python
# Ejemplo simplificado de vector_store.get_vector_store_for_collection()
```

### Agent Service

- **Caso de uso**: Configuración eficiente de agentes
- **Peculiaridades**: Enfoque en la seguridad y aislamiento por tenant
- **Beneficio principal**: Inicialización más rápida de agentes

```python
# Ejemplo simplificado de agent_executor.get_agent_config()
```

## Invalidación de Caché

La invalidación se realiza de manera coordinada para mantener consistencia:

1. **Invalidación por modificación**: Cuando se modifica un recurso, se invalida su caché
2. **Invalidación en cascada**: Se invalidan también recursos relacionados
3. **Invalidación por TTL**: Expiración automática según el TTL configurado

Ejemplo:

```python
async def invalidate_vector_store_cache(tenant_id, collection_id):
    # 1. Invalidar vector store
    await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="vector_store",
        resource_id=collection_id
    )
    
    # 2. Invalidar consultas relacionadas
    await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="query_result",
        collection_id=collection_id
    )
```

## Mejores Prácticas

1. **Siempre verificar caché primero**: Reducir latencia y carga en la base de datos
2. **Usar TTL adecuados**: Balancear frescura de datos vs rendimiento
3. **Registrar métricas**: Monitorear rendimiento para optimizar configuración
4. **Manejar fallos graciosamente**: Contemplar fallos en caché sin afectar funcionalidad
5. **Aislamiento por tenant**: Asegurar que cada tenant solo acceda a sus datos
6. **Serialización consistente**: Especialmente importante para datos como embeddings vectoriales

## Conclusión

El patrón Cache-Aside proporciona un equilibrio óptimo entre rendimiento y consistencia en el sistema RAG. Su implementación uniforme a través de los cuatro servicios garantiza un comportamiento predecible y facilita el mantenimiento.

## Referencias

- [Common/Cache/Manager.py](../common/cache/manager.py): Implementación central del CacheManager
- [Martin Fowler - Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/cacheAside.html)
- [Microsoft - Cache-Aside Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
