# Implementación del Patrón Cache-Aside en el Servicio de Ingestion

## Visión General

El servicio de ingestion implementa el patrón Cache-Aside siguiendo los principios establecidos en la documentación central del sistema. Este documento describe cómo el servicio utiliza el patrón para optimizar el rendimiento, reducir la carga en la base de datos y mantener la coherencia con los otros servicios del sistema RAG.

## Tipos de Datos Cacheados

| Tipo de Dato | TTL | Descripción |
|--------------|-----|-------------|
| `document` | TTL_STANDARD (1 hora) | Información de documentos almacenados en el sistema |
| `embedding` | TTL_EXTENDED (24 horas) | Embeddings generados para textos específicos |
| `vector_store` | TTL_STANDARD (1 hora) | Estado y configuración de vector stores para colecciones |
| `job_status` | TTL_STANDARD (1 hora) | Estado y progreso de trabajos de procesamiento |

## Implementaciones Clave

### 1. Generación de Embeddings

El servicio implementa la generación de embeddings con caché utilizando la función centralizada `get_with_cache_aside()` para cada texto individual, o la función especializada `get_embeddings_batch_with_cache()` para procesamiento por lotes más eficiente.

```python
# Generación de embeddings con patrón Cache-Aside centralizado
embedding, metrics = await get_with_cache_aside(
    data_type="embedding",
    resource_id=resource_id,
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_embedding_from_db,
    generate_func=generate_embedding,
    agent_id=agent_id
)
```

### 2. Recuperación de Documentos

Para recuperar documentos, el servicio utiliza la implementación centralizada del patrón:

```python
# Recuperación de documentos con caché
document, metrics = await get_with_cache_aside(
    data_type="document",
    resource_id=document_id,
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_document_from_db,
    generate_func=None
)
```

### 3. Almacenamiento en Vector Store

Cuando se almacenan nuevos chunks con sus embeddings, el servicio aplica la invalidación coordinada siguiendo el patrón establecido:

```python
# Almacenamiento con invalidación coordinada
await invalidate_document_update(
    tenant_id=tenant_id,
    document_id=document_id,
    collection_id=collection_id
)
```

## Invalidación Coordinada

Cuando se actualiza un documento o se agregan nuevos chunks a una colección, el servicio de ingestion aplica el patrón de invalidación coordinada para mantener la coherencia del sistema:

1. Invalidación del documento actualizado
2. Invalidación del vector store de la colección
3. Invalidación de consultas relacionadas con el documento o la colección

Este mecanismo garantiza que todas las partes del sistema trabajen con los datos más actualizados, evitando inconsistencias entre la caché y la base de datos.

## Integración con Métricas

El servicio integra el registro de métricas de caché para monitorear el rendimiento:

- Cache Hits/Misses: Para medir la eficacia de la estrategia de caché
- Tamaño de objetos: Para controlar el uso de memoria en la caché
- Tiempos de latencia: Para evaluar la mejora de rendimiento
- Invalidaciones: Para monitorear la frecuencia de actualizaciones

## Optimizaciones Específicas

### Procesamiento por Lotes de Embeddings

El servicio implementa una optimización para el procesamiento por lotes de embeddings, utilizando la función centralizada `get_embeddings_batch_with_cache()` que:

1. Consulta la caché para todos los textos del lote
2. Identifica sólo aquellos que necesitan generación
3. Genera embeddings únicamente para los textos no encontrados en caché
4. Combina los resultados de caché y de generación
5. Almacena los nuevos embeddings en caché con el TTL apropiado

### TTL Estratificados

El servicio aplica diferentes TTL según la estabilidad de los datos:

- Embeddings: TTL extendido (24 horas) ya que son muy estables
- Documentos y vector stores: TTL estándar (1 hora) para balance entre actualidad y rendimiento
- Estados de trabajo: TTL corto (5-15 minutos) para datos más volátiles

## Mejores Prácticas

1. **Usar siempre `get_with_cache_aside()`**: Para mantener consistencia con otros servicios
2. **Implementar la invalidación coordinada**: Al actualizar documentos o collections
3. **Utilizar las constantes de TTL**: En lugar de hardcodear valores
4. **Registrar métricas de rendimiento**: Para análisis y optimización continua
5. **Considerar el procesamiento por lotes**: Para operaciones intensivas como embeddings

## Conclusiones

La implementación del patrón Cache-Aside en el servicio de ingestion sigue los principios establecidos en la documentación central, asegurando:

- Rendimiento óptimo mediante el uso efectivo de caché
- Coherencia de datos a través de la invalidación coordinada
- Monitoreo y métricas para evaluación continua
- Estrategias de caché apropiadas para cada tipo de dato
