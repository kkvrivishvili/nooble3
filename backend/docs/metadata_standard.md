# Estándar de Metadatos para LlamaIndex

## Introducción

Este documento describe el estándar implementado para la gestión de metadatos en todos los componentes que utilizan LlamaIndex en el sistema RAG. La estandarización garantiza consistencia, eficiencia y compatibilidad con los mecanismos de caché existentes.

## Campos Obligatorios

| Campo | Descripción | Obligatoriedad |
|-------|-------------|----------------|
| `tenant_id` | ID del tenant | Obligatorio |
| `document_id` | ID del documento original | Obligatorio para chunks |
| `chunk_id` | ID único del chunk | Obligatorio para chunks |
| `collection_id` | ID de la colección | Recomendado |
| `created_at` | Timestamp de creación | Auto-generado si no existe |

## Función Central: `standardize_llama_metadata`

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

## Implementación por Servicio

### Servicio de Ingestion

El servicio de ingestion aplica la estandarización durante la fase de chunking:

```python
# En ingestion-service/services/chunking.py
from common.cache import standardize_llama_metadata

# Al crear nodos durante chunking
for i, node in enumerate(nodes):
    # Generar chunk_id consistente
    chunk_id = f"{document_id}_{i}"
            
    # Estandarizar metadatos con nuestra función
    node_metadata = standardize_llama_metadata(
        metadata=dict(node.metadata),
        tenant_id=tenant_id,
        document_id=document_id,
        chunk_id=chunk_id,
        collection_id=collection_id,
        ctx=ctx
    )
    
    # Añadir el chunk con metadatos estandarizados
    chunks.append({
        "id": node_metadata["chunk_id"],
        "text": node_text,
        "metadata": node_metadata
    })
```

### Servicio de Embedding

El servicio de embedding aplica la estandarización durante la generación de embeddings:

```python
# En embedding-service/services/llama_index_utils.py
from common.cache import standardize_llama_metadata

# Crear metadatos base estandarizados una sola vez para todo el lote
base_metadata = standardize_llama_metadata(
    metadata={},
    tenant_id=tenant_id,
    collection_id=collection_id,
    ctx=ctx
)

# Para cada chunk en el procesamiento
chunk_metadata = dict(base_metadata)
chunk_metadata["chunk_id"] = chunk_id[i]

# Usar en tracking y registro
await track_chunk_cache_metrics(
    tenant_id=tenant_id,
    chunk_id=chunk_id[i],
    metric_type=METRIC_CHUNK_CACHE_HIT,
    collection_id=collection_id,
    model_name=model_name,
    extra_metadata=chunk_metadata  # Usar metadatos estandarizados
)
```

### Servicio de Query

El servicio de query aplica la estandarización en los resultados de búsqueda y consultas:

```python
# En query-service/services/query_engine.py
from common.cache import standardize_llama_metadata

# Al procesar resultados de consultas
for node_with_score in query_result.source_nodes:
    source_text = node_with_score.node.get_content()
    source_meta = node_with_score.node.metadata.copy()
    source_score = node_with_score.score
    
    # Limpiar metadatos (opcional)
    if "embedding" in source_meta:
        del source_meta["embedding"]
    
    # Estandarizar metadatos para asegurar consistencia entre servicios
    source_meta = standardize_llama_metadata(
        metadata=source_meta,
        tenant_id=tenant_id,
        collection_id=collection_id,
        ctx=ctx
    )

# En rutas para búsqueda interna
for node in results:
    # Estandarizar metadatos para asegurar consistencia entre servicios
    standardized_metadata = standardize_llama_metadata(
        metadata=node.metadata,
        tenant_id=tenant_id,
        collection_id=request.collection_id,
        ctx=ctx
    )
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

## Beneficios de la Estandarización

1. **Consistencia**: Todos los metadatos siguen el mismo formato en todos los servicios
2. **Eficiencia de Caché**: Optimiza el uso del patrón Cache-Aside al garantizar claves coherentes
3. **Trazabilidad**: Facilita el seguimiento entre documentos, chunks y resultados
4. **Compatibilidad**: Mantiene compatibilidad con código preexistente
5. **Facilidad de Mantenimiento**: Centraliza la lógica de metadatos en una sola función

## Recomendaciones de Uso

1. **Importación Correcta**: Siempre importar del módulo principal
   ```python
   from common.cache import standardize_llama_metadata  # Correcto
   ```
   
2. **Validar Tenant ID**: Siempre proporcionar un `tenant_id` válido, ya sea explícitamente o a través del contexto

3. **Formato de chunk_id**: Para nuevos chunks, usar el formato `{document_id}_{index}` para mantener consistencia

## Últimas Actualizaciones

El estándar de metadatos fue implementado en mayo 2025, como parte de la optimización del sistema de caché y la preparación para futuras refactorizaciones del proyecto.

---

*Última actualización: 2025-05-09*
