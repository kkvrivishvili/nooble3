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

## Integración con Proveedores LLM

### 1. Soporte para Groq

El sistema ahora incluye soporte completo para modelos de Groq (Llama 3, Mixtral) a través de los siguientes componentes:

```python
# Importar funcionalidades de Groq
from common.llm import (
    get_groq_llm_model,     # Para obtener un modelo configurado
    stream_groq_response,   # Para streaming de respuestas
    is_groq_model,          # Para comprobar si un nombre de modelo pertenece a Groq
    GROQ_MODELS             # Diccionario con información de modelos disponibles
)

# Uso básico
llm = get_groq_llm_model(model="llama3-70b-8192", temperature=0.7)
response = await llm.chat(messages=[{"role": "user", "content": query}])
```

### 2. Sistema Unificado de Tracking

Para registrar uso de tokens con cualquier proveedor (OpenAI, Groq, Ollama), usar la función centralizada:

```python
from common.tracking import (
    track_token_usage,
    TOKEN_TYPE_LLM,           # Para LLMs
    TOKEN_TYPE_EMBEDDING,      # Para embeddings
    OPERATION_QUERY,           # Para consultas normales
    OPERATION_BATCH,           # Para operaciones en lote
    OPERATION_INTERNAL         # Para llamadas internas entre servicios
)

# Ejemplo de uso con idempotencia
await track_token_usage(
    tenant_id=tenant_id,
    tokens=total_tokens,
    model=model_name,
    token_type=TOKEN_TYPE_LLM,
    operation=OPERATION_QUERY,
    idempotency_key=f"{operation}:{tenant_id}:{uuid.uuid4()}",
    metadata={
        "provider": "groq",  # o "openai", "ollama", etc.
        "input_tokens": input_tokens,
        "output_tokens": output_tokens
    }
)
```
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
