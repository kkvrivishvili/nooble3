# Servicio de Embeddings

## Descripción General

El Servicio de Embeddings es un componente central de la arquitectura RAG de la plataforma, responsable de generar representaciones vectoriales de textos que permiten búsquedas semánticas, comparaciones de similitud y otras operaciones basadas en significado.

Este servicio proporciona:
- Generación de embeddings mediante modelos de OpenAI
- Caché multinivel optimizada
- Validación de acceso basada en tier de tenant
- Tracking detallado de uso y rendimiento
- Políticas de rate limiting y degradación controlada

## Arquitectura

### Componentes Principales

1. **API Layer** - `routes/`
   - Endpoints RESTful para generación de embeddings
   - Manejo de autenticación y autorización
   - Validación de parámetros de entrada
   - Endpoints de health check y monitoreo

2. **Service Layer** - `services/`
   - `embedding_provider.py` - Interfaz principal para generación de embeddings
   - `llama_index_utils.py` - Integración con LlamaIndex para generación de embeddings
   - Implementación del patrón Cache-Aside optimizado
   - Políticas de fallback y degradación controlada

3. **Configuration** - `config/`
   - Parámetros y constantes del servicio
   - Configuración de modelos y dimensiones
   - Umbrales de calidad y rendimiento
   - Timeouts y políticas de retry

### Flujo de Datos

```
Cliente → API → CachedEmbeddingProvider → LlamaIndexUtils → Modelo (OpenAI) → Cache → Cliente
```

1. Cliente envía texto(s) para embedding
2. API valida la solicitud y la pasa al servicio
3. CachedEmbeddingProvider verifica acceso y políticas
4. Se busca en caché usando el patrón Cache-Aside centralizado
5. Si no existe, se consulta en base de datos
6. Si no existe, se genera con el modelo apropiado
7. Se almacena en caché y se devuelve al cliente

## Endpoints Principales

### Generación de Embeddings

```
POST /api/embedding/generate
```

**Parámetros:**
- `text` (string): Texto para generar embedding
- `model` (string, opcional): Modelo a utilizar, default configurado en settings
- `collection_id` (string, opcional): ID de colección para contexto de caché

**Respuesta:**
```json
{
  "success": true,
  "message": "Embedding generado correctamente",
  "data": {
    "embedding": [0.123, 0.456, ...],
    "model": "text-embedding-ada-002",
    "dimensions": 1536
  },
  "metadata": {
    "source": "cache|db|generation",
    "latency_ms": 123
  }
}
```

### Generación por Lotes

```
POST /api/embedding/batch
```

**Parámetros:**
- `texts` (array): Lista de textos para generar embeddings
- `model` (string, opcional): Modelo a utilizar
- `collection_id` (string, opcional): ID de colección para contexto
- `chunk_id` (array, opcional): IDs de chunks para referencia específica

**Respuesta:**
```json
{
  "success": true,
  "message": "Embeddings generados correctamente",
  "data": {
    "embeddings": [[0.123, ...], [0.456, ...], ...],
    "model": "text-embedding-ada-002",
    "dimensions": 1536
  },
  "metadata": {
    "metrics": {
      "total_texts": 10,
      "cached": 7,
      "db_retrieved": 2,
      "generated": 1,
      "total_time_ms": 156
    }
  }
}
```

### Estado del Servicio

```
GET /health
GET /status
```

## Modelos Soportados

El servicio soporta diferentes modelos según el tier del tenant:

| Modelo | Dimensiones | Tiers Permitidos | Notas |
|--------|-------------|------------------|-------|
| text-embedding-ada-002 | 1536 | premium, standard, free | OpenAI (legacy) |
| text-embedding-3-small | 1536 | standard, free | OpenAI |
| text-embedding-3-large | 3072 | premium, business, enterprise | OpenAI |

## Patrón Cache-Aside Optimizado

El servicio implementa el patrón Cache-Aside optimizado y centralizado:

1. **Verificación de Caché**
   - Busca primero en caché en memoria (ultra-rápido)
   - Si no está, busca en caché de Redis
   - Usa identificadores deterministas basados en hashes de contenido

2. **Consulta en Base de Datos**
   - Si no está en caché, intenta recuperar de la base de datos
   - Busca por hash de contenido en tabla `document_chunks`
   - Almacena en caché si se encuentra

3. **Generación con API**
   - Si no está en DB, genera nuevo embedding con el modelo configurado
   - Implementa tracking de tokens y latencia
   - Almacena en caché y opcionalmente en DB

## Integración con Sistemas Centralizados

### Sistema de Contexto

```python
@with_context(tenant=True, validate_tenant=True)
async def get_embedding(text: str, ctx: Context = None):
    # El contexto proporciona tenant_id, agent_id, etc.
    # ...
```

### Sistema de Caché

```python
from common.cache import get_with_cache_aside

embedding, metrics = await get_with_cache_aside(
    data_type="embedding",
    resource_id=resource_id,
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_from_db,
    generate_func=generate_embedding
)
```

### Sistema de Tracking

```python
from common.tracking import track_token_usage

await track_token_usage(
    tenant_id=tenant_id,
    tokens=input_tokens,
    model=model_name,
    token_type="embedding"
)
```

## Tolerancia a Fallos y Degradación

El servicio implementa mecanismos de degradación controlada:

1. **Fallback de modelos**
   - Si un modelo premium no está disponible, cae a modelos de menor capacidad
   - Mantiene servicio disponible con modelos alternativos

2. **Timeouts adaptables**
   - Timeout principal para embeddings: 60s
   - Timeouts reducidos para health checks: 5s
   - Backoff exponencial con jitter para reintentos

3. **Circuit breaker**
   - Detecta cuando un proveedor está degradado o indisponible
   - Reduce presión en sistemas ya sobrecargados
   - Permite recuperación gradual

## Políticas de Seguridad

1. **Validación de tenant**
   - Todas las operaciones verifican el tenant_id
   - Si validate_tenant=True, se verifica existencia real del tenant

2. **Validación de modelo**
   - Verifica que el tenant tenga acceso al modelo solicitado
   - Restricciones según tier del tenant

3. **Límites de tamaño**
   - Validación de longitud máxima de textos
   - Límites de tamaño para batch processing

## Métricas y Monitoreo

El servicio registra métricas detalladas:

- **Latencia** - Tiempo de generación de embeddings
- **Eficiencia de caché** - Hit rate, miss rate
- **Uso de API** - Tokens consumidos, solicitudes realizadas
- **Degradación** - Downgrade de modelos, reintentos
- **Tasa de errores** - Por tipo y causa

## Configuración

Principales variables de configuración en `config/settings.py`:

- `default_embedding_model` - Modelo predeterminado
- `embedding_batch_size` - Tamaño por defecto para processing por lotes
- `max_token_length_per_text` - Límite de tokens por texto
- `max_batch_size` - Límite de textos en un batch
- `use_memory_cache` - Habilitar/deshabilitar caché en memoria (rapid)
- `cache_ttl` - Tiempo de vida en caché para embeddings

## Buenas Prácticas

1. **Uso del servicio**
   - Preferir procesamiento por lotes sobre llamadas individuales
   - Proporcionar collection_id para mejorar especificidad de caché
   - Proporcionar chunk_id para tracking específico

2. **Desarrollo y mantenimiento**
   - Seguir estrictamente el patrón Cache-Aside centralizado
   - Mantener compatibilidad con el servicio de ingestión
   - Actualizar tests para nuevos modelos

## Evolución y Roadmap

Posibles mejoras futuras:

1. **Soporte para nuevos modelos**
   - Modelos multimodales (imagen-texto)
   - Embeddings específicos por dominio

2. **Optimizaciones de rendimiento**
   - Procesamiento en GPU para modelos locales
   - Compresión de embeddings para reducir uso de memoria

3. **Funcionalidades extendidas**
   - API para similitud directa entre embeddings
   - Pre-computación en background para textos frecuentes
