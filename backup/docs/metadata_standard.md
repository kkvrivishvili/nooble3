# Estándar de Metadatos para LlamaIndex

## Introducción

Este documento describe el estándar implementado para la gestión de metadatos en todos los componentes que utilizan LlamaIndex en el sistema RAG. La estandarización garantiza consistencia, eficiencia y compatibilidad con los mecanismos de caché existentes.

La implementación actual proporciona manejo de errores robusto, preservación de campos críticos y documentación inline completa en todos los servicios (ingestion, embedding, query).

## Campos Obligatorios

| Campo | Descripción | Obligatoriedad | Implicancia |
|-------|-------------|----------------|-------------|
| `tenant_id` | ID del tenant | Obligatorio | Crítico para multitenancy y jerarquía de caché |
| `document_id` | ID del documento original | Obligatorio para chunks | Esencial para trazabilidad entre documento y chunks |
| `chunk_id` | ID único del chunk | Obligatorio para chunks | Identificador único con formato estandarizado `document_id_índice` |
| `collection_id` | ID de la colección | Recomendado | Mejora búsqueda jerárquica en caché y agrupación |
| `created_at` | Timestamp de creación | Auto-generado | Asegura capacidad de ordenamiento cronológico |

## Función Central: `standardize_llama_metadata`

La función centralizada se define en `common/cache/helpers.py` y se exporta a través de `common.cache` para uso en todos los servicios:

```python
def standardize_llama_metadata(
    metadata: Dict[str, Any], 
    tenant_id: str = None,
    document_id: str = None,
    chunk_id: str = None,
    collection_id: str = None,
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """
    Estandariza los metadatos para documentos y chunks de LlamaIndex.
    
    Garantiza consistencia entre servicios y compatibilidad total con get_with_cache_aside.
    Mantiene todos los campos existentes y añade los obligatorios faltantes.
    
    Args:
        metadata: Metadatos originales a estandarizar
        tenant_id: ID de tenant explícito (obligatorio)
        document_id: ID de documento explícito (requerido para chunks)
        chunk_id: ID de chunk explícito
        collection_id: ID de colección explícito
        ctx: Contexto de la operación para valores por defecto
        
    Returns:
        Dict[str, Any]: Metadatos estandarizados
        
    Raises:
        ValueError: Si falta tenant_id o campos obligatorios
    """
```

### Importación Correcta

Para usar esta función en cualquier servicio, importarla así:

```python
from common.cache import standardize_llama_metadata
```

### Manejo de Errores Robusto

La implementación en los servicios ahora incluye manejo de errores completo y consistente:

```python
try:
    standardized_metadata = standardize_llama_metadata(
        metadata=node.metadata,
        tenant_id=tenant_id,
        document_id=document_id,
        chunk_id=chunk_id,
        collection_id=collection_id,
        ctx=ctx
    )
except ValueError as ve:
    # Errores de validación específicos
    logger.warning(f"Error en estandarización de metadatos: {str(ve)}")
    # Aplicar estrategia de recuperación (mínimos metadatos funcionales)
    standardized_metadata = standardize_llama_metadata(
        metadata={},  # Metadatos mínimos
        tenant_id=tenant_id
    )
except Exception as e:
    # Errores inesperados
    logger.error(f"Error inesperado en estandarización: {str(e)}")
    # Estrategia para preservar el servicio
```

## Implementación por Servicio

### Servicio de Ingestion

El servicio de ingestion aplica la estandarización durante la fase de chunking, con manejo de errores robusto:

```python
# En ingestion-service/services/chunking.py
from common.cache import standardize_llama_metadata

# Al crear nodos durante chunking
for i, node in enumerate(nodes):
    # Generar chunk_id consistente (formato estandarizado: document_id_índice)
    chunk_id = f"{document_id}_{i}"
            
    # CRÍTICO: Estandarizar metadatos para garantizar consistencia en caché y tracking
    try:
        node_metadata = standardize_llama_metadata(
            metadata=dict(node.metadata),
            tenant_id=tenant_id,  # Campo crítico para multitenancy
            document_id=document_id,  # Obligatorio para chunks, permite trazabilidad
            chunk_id=chunk_id,  # Identificador único para este fragmento
            collection_id=collection_id,  # Necesario para caché jerárquica
            ctx=ctx  # Contexto para valores por defecto si faltan campos
        )
    except ValueError as ve:
        # Errores específicos de metadatos (campos faltantes o formato incorrecto)
        logger.error(f"Error en estandarización de metadatos: {str(ve)}",
                   extra={"document_id": document_id, "chunk_id": chunk_id})
        # Reintentar con metadatos básicos para evitar fallo total
        node_metadata = standardize_llama_metadata(
            metadata={},  # Metadatos mínimos
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_id=chunk_id
        )
    
    # Añadir el chunk con metadatos estandarizados
    chunks.append({
        "id": node_metadata["chunk_id"],
        "text": node_text,
        "metadata": node_metadata
    })
```

### Servicio de Embedding

El servicio de embedding aplica la estandarización durante la generación de embeddings, con optimizaciones y manejo de errores:

```python
# En embedding-service/services/llama_index_utils.py
from common.cache import standardize_llama_metadata

# CRÍTICO: Estandarizar metadatos base para todo el lote
try:
    base_metadata = standardize_llama_metadata(
        metadata={},
        tenant_id=tenant_id,  # Campo obligatorio para multitenancy
        collection_id=collection_id,  # Para búsqueda jerárquica en caché
        ctx=ctx  # Contexto para valores por defecto
    )
except ValueError as e:
    # Errores específicos de validación de metadatos
    logger.error(f"Error en estandarización de metadatos base: {str(e)}",
              extra={"tenant_id": tenant_id, "collection_id": collection_id})
    # Crear metadatos mínimos para no fallar completamente
    base_metadata = {
        "tenant_id": tenant_id,
        "created_at": int(time.time())
    }

# Para cada chunk en el procesamiento, optimizado con reutilización de metadata base
chunk_specific_metadata = dict(base_metadata)
chunk_specific_metadata["chunk_id"] = chunk_id[i]

# Usar en get_with_cache_aside centralizado para caché optimizada
embedding, text_metrics = await get_with_cache_aside(
    data_type="embedding",
    resource_id=resource_id,
    tenant_id=tenant_id,
    collection_id=collection_id,
    ctx=ctx
)
```

### Servicio de Query

El servicio de query aplica la estandarización en los resultados de búsqueda y consultas, con preservación de campos originales:

```python
# En query-service/services/query_engine.py
from common.cache import standardize_llama_metadata

# Al procesar resultados de consultas
for node_with_score in query_result.source_nodes:
    source_text = node_with_score.node.get_content()
    source_meta = node_with_score.node.metadata.copy()
    source_score = node_with_score.score
    
    # Limpiar metadatos pesados antes de estandarizar
    if "embedding" in source_meta:
        del source_meta["embedding"]
    
    # CRÍTICO: Estandarizar metadatos para asegurar consistencia con otros servicios
    try:
        source_meta = standardize_llama_metadata(
            metadata=source_meta,
            tenant_id=tenant_id,  # Obligatorio para multitenancy
            collection_id=collection_id,  # Para agrupación por colección
            # Preservar document_id y chunk_id si existen en los metadatos originales
            document_id=source_meta.get("document_id"),
            chunk_id=source_meta.get("chunk_id"),
            ctx=ctx  # Contexto para valores por defecto
        )
    except ValueError as ve:
        # Errores de validación específicos (campos faltantes o formato incorrecto)
        logger.warning(f"Error en estandarización de metadatos: {str(ve)}")
        # Garantizar metadatos mínimos para evitar fallos completos
        source_meta = standardize_llama_metadata(
            metadata={},  # Metadatos mínimos
            tenant_id=tenant_id
        )
```

#### En Rutas Internas

```python
# En query-service/routes/internal.py 
for node in results:
    # Extraer valores existentes para preservarlos si es posible
    document_id = node.metadata.get("document_id")
    chunk_id = node.metadata.get("chunk_id")
    
    try:
        standardized_metadata = standardize_llama_metadata(
            metadata=node.metadata,
            tenant_id=tenant_id,  # Obligatorio para multitenancy
            collection_id=request.collection_id,  # Agrupación jerárquica
            document_id=document_id,  # Preservar relación con documento original
            chunk_id=chunk_id,  # Mantener identificador único del chunk
            ctx=ctx  # Contexto para valores por defecto
        )
    except Exception as e:
        # Manejar errores para preservar el servicio
        logger.error(f"Error en estandarización: {str(e)}")
        # ... estrategia de recuperación ...
```

## Comportamiento del Formato de `chunk_id`

La función `standardize_llama_metadata` implementa una lógica para asegurar el formato consistente de `chunk_id`:

- Si el `chunk_id` es numérico o parece ser un índice simple
- Y existe un `document_id` asociado
- Y el `chunk_id` no ya incluye el formato compuesto

Entonces se formatea automáticamente a `document_id_chunk_id` para garantizar la trazabilidad entre chunks y documentos originales.

## Integración con el Sistema de Contexto

La función de estandarización se integra con el sistema de `Context` del proyecto:

- Puede extraer valores como `tenant_id` y `collection_id` del contexto si no se proporcionan explícitamente
- También admite valores adicionales del contexto como `agent_id` y `conversation_id`
- Mantiene consistencia con la jerarquía de caché establecida en el patrón Cache-Aside

## Manejo Robusto de Errores

La implementación actual proporciona manejo de errores estandarizado para garantizar la continuidad del servicio:

1. **Validación de Campos Obligatorios**: Se valida estrictamente la presencia de `tenant_id` y otros campos críticos

2. **Estrategia de Recuperación**: En caso de error, se intenta continuar con metadatos mínimos válidos

3. **Preservación del Servicio**: Los errores de metadatos no interrumpen los flujos críticos del sistema

4. **Logging Consistente**: Todos los errores se registran con contexto enriquecido para facilitar depuración

## Beneficios de la Estandarización

1. **Consistencia Total**: Todos los metadatos siguen el mismo formato en todos los servicios

2. **Eficiencia de Caché**: Optimiza el uso del patrón Cache-Aside al garantizar claves coherentes, resultando en mayor tasa de aciertos (cache hits)

3. **Trazabilidad Completa**: Facilita el seguimiento entre documentos, chunks y resultados en todo el flujo RAG

4. **Compatibilidad**: Mantiene compatibilidad tanto con código preexistente como con sistemas externos

5. **Mantenibilidad Mejorada**: Centraliza la lógica de metadatos en una sola función exportada correctamente

6. **Robustez ante Fallos**: El manejo de errores estandarizado garantiza la continuidad del servicio

## Mejores Prácticas

1. **Importación Correcta**: Siempre importar del módulo principal
   ```python
   from common.cache import standardize_llama_metadata  # Correcto
   ```
   
2. **Manejo de Errores**: Implementar manejo de excepciones adecuado
   ```python
   try:
       metadata = standardize_llama_metadata(...)
   except ValueError as ve:
       # Manejar errores específicos de validación
   except Exception as e:
       # Manejar errores generales
   ```

3. **Preservación de Campos**: Siempre extraer y preservar campos críticos de los metadatos originales
   ```python
   document_id = original_metadata.get("document_id")
   standardized = standardize_llama_metadata(
       metadata=original_metadata,
       document_id=document_id,  # Preservar valor original
       ...
   )
   ```

4. **Formato de chunk_id**: Para nuevos chunks, siempre usar el formato `{document_id}_{index}` para mantener consistencia

5. **Documentación Inline**: Incluir comentarios explicativos sobre la importancia de la estandarización
   ```python
   # CRÍTICO: Estandarizar metadatos para garantizar consistencia en caché y tracking
   ```

## Últimas Actualizaciones

El estándar de metadatos fue implementado en mayo 2025, como parte de la optimización del sistema de caché. La versión actual incluye manejo de errores robusto, preservación de campos críticos y documentación mejorada en todos los servicios.

### Exportación Centralizada

La función ahora se exporta correctamente a través del módulo `common.cache` para garantizar acceso consistente en toda la aplicación:

```python
# En common/cache/__init__.py
__all__ = [
    ...
    "standardize_llama_metadata",
    ...
]
```

---

*Última actualización: 2025-05-09*
