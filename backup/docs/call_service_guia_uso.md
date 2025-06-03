# Guía de Uso: Función `call_service`

## Introducción

La función `call_service` es el método centralizado y estandarizado para toda comunicación HTTP entre servicios en nuestra plataforma. Esta guía detalla el uso correcto de esta función para garantizar consistencia, manejo de errores apropiado y beneficiarse de todas sus características.

## Características Principales

- **Propagación automática de contexto**: Tenant ID, Agent ID, Conversation ID y Collection ID
- **Reintentos con backoff exponencial**: Manejo inteligente de fallos temporales
- **Circuit breaker**: Prevención de cascadas de fallos
- **Timeouts específicos** según el tipo de operación
- **Soporte para caché**: Caché de respuestas configurable
- **Manejo estandarizado de errores**: Errores tipo y mensajes consistentes
- **Tracing y observabilidad**: Logs unificados con metadatos de contexto

## Firma de la Función

```python
async def call_service(
    url: str,                                 # URL completa del endpoint destino
    data: Dict[str, Any],                     # Datos a enviar (para GET serán parámetros, para POST será el cuerpo)
    tenant_id: Optional[str] = None,          # ID del tenant (opcional, usa contexto actual si no se especifica)
    agent_id: Optional[str] = None,           # ID del agente (opcional)
    conversation_id: Optional[str] = None,    # ID de la conversación (opcional)
    collection_id: Optional[str] = None,      # ID de la colección (opcional)
    operation_type: str = "default",          # Tipo de operación para determinar timeouts
    headers: Optional[Dict[str, str]] = None, # Headers HTTP adicionales
    max_retries: int = 3,                     # Número máximo de reintentos
    custom_timeout: Optional[float] = None,   # Timeout personalizado (opcional)
    use_cache: bool = False,                  # Si se debe utilizar caché para esta llamada
    cache_ttl: Optional[int] = None,          # Tiempo de vida en segundos para la caché
    method: str = "POST"                      # Método HTTP (POST, GET, etc.)
) -> Dict[str, Any]:                          # Respuesta estandarizada
```

## Formato de Respuesta

Todas las respuestas siguen un formato estandarizado:

```python
{
    "success": bool,              # Éxito/fallo de la operación
    "data": Dict[str, Any],       # Datos de respuesta (JSON original del servicio)
    "error": Optional[Dict],      # Detalles del error (solo si success=False)
    "metadata": Optional[Dict]    # Metadatos adicionales de la operación
}
```

## Ejemplos de Uso Correcto

### 1. Solicitud POST básica

```python
from common.utils.http import call_service

# Forma correcta (usando 'data' para el cuerpo)
result = await call_service(
    url="http://embedding-service/internal/embed",
    data={
        "texts": ["Texto a codificar"],
        "model": "nomic-embed-text"
    },
    operation_type="embedding_generation"
)

# ⚠️ INCORRECTO: No usar 'json' como parámetro
# result = await call_service(
#     url="http://embedding-service/internal/embed",
#     json={"texts": ["Texto"]}  # ❌ INCORRECTO: usar 'data' en lugar de 'json'
# )

# Acceso correcto a los resultados
if result.get("success", False):
    # Extraer datos de la respuesta original
    embeddings = result.get("data", {}).get("embeddings", [])
else:
    # Manejo de error
    error_msg = result.get("error", {}).get("message", "Error desconocido")
    logger.error(f"Error en servicio: {error_msg}")
```

### 2. Solicitud GET con parámetros

```python
# En GET, los datos van como parámetros de query
status_result = await call_service(
    url="http://embedding-service/status",
    data={},  # Vacío o con parámetros de query
    method="GET",
    custom_timeout=2.0
)

if status_result.get("success", False):
    components = status_result.get("data", {}).get("components", {})
```

### 3. Uso con propagación de contexto

```python
# Propagación automática del contexto actual
result = await call_service(
    url="http://query-service/internal/query",
    data={
        "query": "¿Cómo configurar?",
        "collection_id": "docs-collection"
    }
    # No necesita especificar tenant_id, agent_id, etc. si ya están en el contexto
)

# Especificando contexto explícitamente
result = await call_service(
    url="http://query-service/internal/query",
    data={"query": "¿Cómo configurar?"},
    tenant_id="tenant123",
    collection_id="docs-collection"
)
```

### 4. Uso con caché

```python
# Con caché habilitada
cached_result = await call_service(
    url="http://embedding-service/internal/embed",
    data={"texts": ["Texto frecuente"]},
    use_cache=True,
    cache_ttl=3600,  # 1 hora
    tenant_id="tenant123"
)
```

### 5. Configuración de timeouts específicos

```python
# Timeout personalizado para operaciones costosas
result = await call_service(
    url="http://llm-service/generate",
    data={"prompt": "Texto largo para generar contenido..."},
    custom_timeout=60.0  # 60 segundos
)

# Usando tipos de operación pre-configurados
result = await call_service(
    url="http://embedding-service/internal/embed",
    data={"texts": ["Texto para embeddings"]},
    operation_type="embedding_generation"  # Usa timeout pre-configurado
)
```

## Manejo de Errores

La función `call_service` ya gestiona errores HTTP, timeouts y errores de conexión. Lo único que necesitas es verificar el resultado:

```python
result = await call_service(url=service_url, data=request_data)

if result.get("success", False):
    # Operación exitosa
    return process_result(result.get("data", {}))
else:
    # Gestión de error
    error = result.get("error", {})
    error_type = error.get("type", "UNKNOWN_ERROR")
    error_message = error.get("message", "Error desconocido")
    
    # Log estructurado
    logger.error(
        f"Error llamando a servicio: {error_message}",
        extra={
            "error_type": error_type,
            "service_url": service_url,
            "details": error.get("details")
        }
    )
    
    # Opcional: Reinterpretación del error para el cliente
    raise ServiceError(
        message=f"Error en operación: {error_message}",
        details={"original_error": error}
    )
```

## Tipos de Operaciones y Timeouts

La función `call_service` utiliza timeouts diferentes según el tipo de operación especificado en el parámetro `operation_type`:

| Tipo de Operación | Descripción | Timeout | TTL Recomendado |
|-------------------|-------------|---------|----------------|
| `default` | Operación genérica | 30.0s | 300 (5 min) |
| `embedding_generation` | Generación de embeddings | 60.0s | 86400 (24 horas) |
| `llm_generation` | Generación con LLM | 60.0s | 3600 (1 hora) |
| `rag_query` | Consultas RAG completas | 45.0s | 3600 (1 hora) |
| `rag_search` | Búsqueda simple sin generación | 20.0s | 1800 (30 min) |
| `agent_response` | Respuestas de agentes | 45.0s | 1800 (30 min) |
| `agent_config` | Configuraciones de agentes | 10.0s | 300 (5 min) |
| `batch_processing` | Procesamiento por lotes | 120.0s | 3600 (1 hora) |
| `health_check` | Verificación de salud | 5.0s | 60 (1 min) |

## Nomenclatura de Endpoints Internos

Los endpoints destinados exclusivamente a comunicaciones entre servicios (no expuestos al usuario) siguen el patrón:

```
/internal/<nombre-operación>
```

Ejemplos:
- `/internal/query`: Consultas RAG desde Agent Service a Query Service
- `/internal/embed`: Generación de embeddings desde otros servicios a Embedding Service
- `/internal/search`: Búsqueda rápida de documentos desde Context Manager a Query Service

## Mejores Prácticas

1. **Siempre utilizar `call_service`**: Nunca implementar llamadas HTTP directas entre servicios

2. **Usar siempre `data` para los parámetros**:
   - En POST: `data` se envía como JSON en el cuerpo
   - En GET: `data` se convierte en parámetros de query

3. **Verificar siempre `success` antes de acceder a los datos**:
   ```python
   if result.get("success", False):
       # Acceder a los datos
   ```

4. **Diseñar para reintentos idempotentes**: Asegurar que las operaciones son seguras para reintentar

5. **Propagar el contexto completo**: Pasar siempre tenant_id, agent_id, conversation_id y collection_id cuando estén disponibles:
   ```python
   # Implícito (usando el contexto actual)
   result = await call_service(url=service_url, data=data)
   
   # Explícito (especificando todos los IDs)
   result = await call_service(
       url=service_url, 
       data=data,
       tenant_id=tenant_id,
       agent_id=agent_id,
       conversation_id=conversation_id,
       collection_id=collection_id
   )
   ```

6. **Utilizar operation_type apropiado**: Elegir el tipo adecuado según la operación (ver tabla arriba)

7. **Activar caché para llamadas repetitivas**: Especialmente para operaciones costosas o frecuentes

8. **Documentar endpoints internos**: Proporcionar documentación clara de todos los endpoints internos

9. **Monitorizar latencia**: Registrar y analizar los tiempos de respuesta entre servicios

10. **Validar respuestas recibidas**: Verificar formato y contenido de las respuestas

## Casos de Uso Comunes

### Llamada a servicio de embeddings

```python
result = await call_service(
    url=f"{settings.embedding_service_url}/internal/embed",
    data={
        "texts": texts_to_embed,
        "model": model_name
    },
    custom_timeout=30.0,
    operation_type="embedding_generation"
)

if result.get("success", False):
    embeddings = result.get("data", {}).get("embeddings", [])
    return embeddings
else:
    # Fallback o error
    return None
```

### Consulta a vector store

```python
result = await call_service(
    url=f"{settings.query_service_url}/internal/query",
    data={
        "query": user_query,
        "collection_id": collection_id,
        "top_k": 5
    },
    tenant_id=tenant_id,
    operation_type="rag_query"
)

if result.get("success", False):
    response = result.get("data", {}).get("response", "")
    sources = result.get("data", {}).get("sources", [])
    return response, sources
```

### Verificación de salud

```python
health_result = await call_service(
    url=f"{service_url}/health",
    data={},
    method="GET",
    custom_timeout=2.0,
    operation_type="health_check",
    max_retries=1  # Menos reintentos para health checks
)

is_healthy = health_result.get("success", False)
```

## Operaciones Streaming

Para operaciones con streaming, como generación de texto con LLMs, se debe usar otro mecanismo:

```python
from common.utils.streaming import stream_from_service

async for chunk in stream_from_service(
    url=f"{settings.llm_service_url}/generate_stream",
    data={"prompt": user_prompt},
    tenant_id=tenant_id
):
    yield chunk
```

## Expansión del Sistema

### Añadir Nuevos Tipos de Operaciones

Para añadir un nuevo tipo de operación:

1. Actualizar `OPERATION_TIMEOUTS` en `common.utils.http` con el nuevo tipo y su timeout recomendado
2. Documentar el nuevo tipo y su uso recomendado en este documento
3. Implementar cualquier lógica especializada en `get_timeout_for_operation` si es necesario

### Añadir Nuevos Campos a la Respuesta Estándar

Si se necesita expandir el formato de respuesta estándar:

1. Actualizar la función `standardize_response` en `common.utils.http`
2. Mantener compatibilidad con el formato básico (`success`, `message`, `data`, `metadata`, `error`)
3. Documentar el nuevo campo y su propósito en este documento
4. Actualizar los endpoints existentes de forma incremental

## Integración con Estructura de Proyecto

```
common/
  utils/
    http.py          # Implementación de call_service
  context/
    vars.py          # Variables de contexto (tenant_id, etc.)
  errors/
    exceptions.py    # Definiciones de errores
  cache/
    manager.py       # Caché para call_service
```

## Resolución de Problemas

### Problemas comunes

1. **Timeout muy corto**:
   - Usar `custom_timeout` o `operation_type` adecuado
   - Los timeouts varían según tipo de operación

2. **No se propaga el contexto**:
   - Verificar que el contexto existe en el request actual
   - O proporcionar explícitamente tenant_id, agent_id, etc.

3. **Error "Tenant ID required"**:
   - Siempre proporcionar tenant_id para operaciones por tenant
   - O asegurar que está en el contexto actual
