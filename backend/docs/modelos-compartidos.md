# Modelos Compartidos para Comunicación entre Servicios

## Introducción

Este documento detalla los patrones estándar para la comunicación entre los diferentes servicios de la plataforma (query, embedding, ingestion, etc.). Seguir estos patrones garantiza interoperabilidad, facilita el mantenimiento y reduce la duplicación de código.

## Modelos Base

### `BaseModel` (common/models/base.py)

Todos los modelos de datos deben heredar de `BaseModel`, que proporciona configuración común:

```python
class BaseModel(PydanticBaseModel):
    """Modelo base del que heredan todos los modelos."""
    
    class Config:
        from_attributes = True  # Antes era orm_mode = True en Pydantic V1
        arbitrary_types_allowed = True
        extra = "ignore"  # Ignorar campos extra
```

### `BaseResponse` (common/models/base.py)

Base para todos los modelos de respuesta, garantiza consistencia en las respuestas API:

```python
class BaseResponse(BaseModel):
    """Modelo base para todas las respuestas API para garantizar consistencia."""
    success: bool
    message: str
```

## Patrones de Comunicación entre Servicios

### 1. Comunicación API Externa (Usuario → Servicio)

Para endpoints públicos expuestos a usuarios, utilizar modelos específicos que hereden de `BaseResponse`:

- `CollectionsListResponse`, `DocumentListResponse`, etc. en `common/models/`
- Estos modelos deben proporcionar información estructurada con campos específicos

### 2. Comunicación API Interna (Servicio → Servicio)

Para endpoints internos utilizados entre servicios, seguir el patrón implementado en `InternalEmbeddingResponse`:

```python
class InternalEmbeddingResponse(CommonBaseModel):
    """Formato de respuesta para el endpoint interno de embedding."""
    success: bool
    message: str
    data: Optional[List[List[float]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
```

Este formato estándar debe seguirse en todos los endpoints internos, manteniendo la misma estructura:

- `success`: Booleano indicando éxito/fallo
- `message`: Descripción del resultado
- `data`: Datos principales (tipados según el contexto)
- `metadata`: Información adicional relevante
- `error`: Detalles del error (solo presente cuando success=False)

## Guía de Implementación por Servicio

### Servicio de Embedding

- Utiliza `InternalEmbeddingResponse` para `/internal/embed`
- Utiliza `EmbeddingResponse` para endpoints públicos

### Servicio de Query

- Para `/internal/query` y `/internal/search`, sigue el formato estándar:
  ```python
  {
      "success": True,
      "message": "Operación completada",
      "data": {...},  # Los datos principales de la respuesta
      "metadata": {...}  # Metadatos adicionales
  }
  ```
- Para endpoints públicos, utiliza `QueryResponse`

### Servicio de Ingestion

- Utiliza `DocumentUploadMetadata` para metadatos de ingestion
- Sigue el mismo patrón para respuestas internas

## Mejores Prácticas

1. **No Crear Modelos Duplicados**:
   - Antes de crear un modelo nuevo, verificar si ya existe uno adecuado
   - Favorecer la reutilización sobre la duplicación

2. **Usar `response_model=None` con `@with_context`**:
   - Cuando un endpoint utiliza el decorador `@with_context`, configurar `response_model=None`
   - Esto evita problemas de validación con el objeto `Context`

3. **Validar el Objeto Context**:
   - Siempre verificar que `ctx` no sea `None` antes de utilizarlo:
   ```python
   if ctx:
       ctx.add_metric("model_downgraded", True)
   ```

4. **Centralizar Modelos Compartidos**:
   - Todos los modelos compartidos deben estar en `common/models/`
   - Clasificar adecuadamente en archivos según su función (documents.py, embeddings.py, etc.)

5. **Exportar Modelos en `__init__.py`**:
   - Asegurar que todos los modelos estén correctamente exportados en `common/models/__init__.py`
   - Esto facilita la importación desde otros módulos

## Ejemplos de Implementación

### Endpoint Interno con Formato Estándar

```python
@router.post("/internal/search", response_model=None)
@with_context(tenant=True, collection=True)
async def internal_search(...):
    # Procesamiento...
    
    return {
        "success": True,
        "message": "Búsqueda procesada correctamente",
        "data": resultados,
        "metadata": {
            "processing_time": tiempo_procesamiento,
            # Otros metadatos relevantes
        }
    }
```

### Manejo de Errores

```python
try:
    # Procesamiento...
except Exception as e:
    return {
        "success": False,
        "message": f"Error: {str(e)}",
        "data": None,
        "error": {
            "type": type(e).__name__,
            "details": {...}
        },
        "metadata": {...}
    }
```
