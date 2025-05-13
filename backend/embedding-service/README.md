# Servicio de Embeddings

## Descripción General

El Servicio de Embeddings es un componente central de la arquitectura RAG de la plataforma, responsable de generar representaciones vectoriales de textos que permiten búsquedas semánticas, comparaciones de similitud y otras operaciones basadas en significado.

Este servicio proporciona:
- Generación de embeddings mediante modelos modernos de OpenAI (text-embedding-3-small y text-embedding-3-large)
- Implementación del patrón Cache-Aside unificado siguiendo los estándares del proyecto
- Validación de acceso basada en tier de tenant con soporte para multitenancy
- Tracking detallado de uso y rendimiento con metadatos enriquecidos
- Políticas optimizadas de rate limiting y manejo de errores centralizado

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
Cliente → API → CachedEmbeddingProvider → OpenAIEmbeddingProvider → API OpenAI → Cache → Cliente
```

1. Cliente envía texto(s) para embedding
2. API valida la solicitud y permisos (tier del tenant)
3. CachedEmbeddingProvider determina modelo apropiado según tier
4. Se busca en caché usando el patrón Cache-Aside unificado
5. Si no hay hit en caché, OpenAIEmbeddingProvider genera embedding
6. Se aplica tracking de tokens y costos a nivel tenant
7. Se almacena en caché con TTL estandarizado y se devuelve al cliente

### Modelos Soportados

| Modelo | Dimensiones | Tokens Máximos | Tiers Soportados | Uso Recomendado |
|--------|------------|----------------|-----------------|------------------|
| text-embedding-3-small | 1536 | 8191 | free, standard, pro, business, enterprise | Uso general, balance rendimiento/costo |
| text-embedding-3-large | 3072 | 8191 | pro, business, enterprise | Alta precisión, tareas complejas |

Los modelos de OpenAI proporcionan vectores de alta calidad para búsqueda semántica, clustering y clasificación de texto. La versión "small" ofrece un excelente balance entre costo y rendimiento, mientras que "large" proporciona máxima precisión para casos que requieren mayor fidelidad.

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
    "model": "text-embedding-3-small",
    "dimensions": 1536
  },
  "metadata": {
    "source": "cache|generation",
    "latency_ms": 123,
    "token_usage": {
      "prompt_tokens": 8,
      "total_tokens": 8
    },
    "tenant_id": "t123",
    "collection_id": "col456"
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
    "model": "text-embedding-3-small",
    "dimensions": 1536,
    "cached_count": 7,
    "processed_count": 10
  },
  "metadata": {
    "metrics": {
      "total_texts": 10,
      "cached": 7,
      "generated": 3,
      "total_time_ms": 156,
      "token_usage": {
        "prompt_tokens": 124,
        "total_tokens": 124
      }
    },
    "provider": "openai",
    "tenant_id": "t123"
  }
}
```

### Estado del Servicio

```
GET /health
GET /status
```

## Modelos Soportados

El servicio soporta los siguientes modelos de OpenAI según el tier del tenant:

| Modelo | Dimensiones | Tiers Permitidos | Rendimiento |
|--------|-------------|------------------|-------------|
| text-embedding-3-small | 1536 | standard, free | Buena calidad para casos de uso general |
| text-embedding-3-large | 3072 | premium, business, enterprise | Calidad superior para búsquedas semánticas y tareas complejas |

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

## Tolerancia a Fallos y Manejo de Errores

El servicio implementa mecanismos robustos para garantizar disponibilidad y resiliencia:

1. **Manejo de Errores de API**
   - Manejo específico para cada tipo de error de la API de OpenAI
   - Clasificación de errores por tipo: autenticación, límites de tasa, indisponibilidad, etc.
   - Respuestas claras al cliente sobre la naturaleza del error

2. **Timeouts y Reintentos**
   - Timeout principal para embeddings: 60s
   - Timeouts reducidos para health checks: 5s
   - Estrategia de reintentos con backoff exponencial y jitter
   - Máximo de reintentos configurables según política de servicio

3. **Monitoreo de Estado**
   - Health checks periódicos para detectar problemas con la API de OpenAI
   - Alertas automáticas al detectar degradación
   - Métricas detalladas de latencia, uso de tokens y tasa de éxito

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

El servicio registra métricas detalladas para monitoreo y optimización:

- **Latencia** - Tiempo de generación de embeddings, desglosado por fases (red, procesamiento, etc.)
- **Eficiencia de caché** - Hit rate, miss rate, tiempo de respuesta de caché
- **Uso de API de OpenAI** - Tokens consumidos por tenant/colección, solicitudes exitosas/fallidas
- **Reintentos** - Patrones de reintentos, backoff, y recuperación exitosa
- **Tasa de errores** - Clasificación por códigos HTTP y tipos de error de OpenAI API

## Gestión de Tokens OpenAI

El servicio implementa un sistema robusto de seguimiento y gestión de tokens:

1. **Registro de Uso**
   - Contabilización exacta de tokens por solicitud (prompt_tokens)
   - Agrupación por tenant, colección y modelo
   - Agregación diaria, semanal y mensual

2. **Optimizaciones de Eficiencia**
   - Estrategias de truncado y preparación de texto para minimizar tokens
   - Batch processing para maximizar eficiencia de API
   - Priorización de caché para textos frecuentes

## Configuración

Principales variables de configuración en `config/settings.py`:

- `OPENAI_API_KEY` - Clave API para OpenAI (obligatoria)
- `OPENAI_ORGANIZATION` - ID de la organización en OpenAI (opcional)
- `default_embedding_model` - Modelo predeterminado ("text-embedding-3-small")
- `embedding_batch_size` - Tamaño por defecto para processing por lotes
- `max_token_length_per_text` - Límite de tokens por texto (8191 para text-embedding-3-small)
- `max_batch_size` - Límite de textos en un batch (2048 por API de OpenAI)
- `use_memory_cache` - Habilitar/deshabilitar caché en memoria (mejora rendimiento)
- `openai_timeout_seconds` - Timeout para solicitudes a OpenAI (60s predeterminado)
- `openai_max_retries` - Número máximo de reintentos para solicitudes fallidas
- `cache_ttl` - Tiempo de vida en caché para embeddings

## Buenas Prácticas

1. **Uso Óptimo del Servicio**
   - Utilizar procesamiento por lotes (batch) para maximizar eficiencia de API
   - Proporcionar siempre `collection_id` para mejorar especificidad de caché
   - Incluir metadatos como `tenant_id` y `chunk_id` para mejor tracking y auditoria
   - Mantener textos dentro de los límites de tokens (8191 para text-embedding-3-small)

2. **Desarrollo y Mantenimiento**
   - Adherirse a los estándares de manejo de errores de OpenAI API
   - Seguir estrictamente el patrón Cache-Aside centralizado para minimizar costos
   - Utilizar las herramientas de monitoreo para detectar cambios en uso de tokens
   - Mantener actualizadas las versiones SDK de OpenAI para acceder a mejoras

## Evolución y Roadmap

Posibles mejoras futuras:

1. **Adaptaciones a Nuevos Modelos de OpenAI**
   - Soporte para futuros modelos de embeddings con mayores dimensiones
   - Adaptación a modelos multimodales cuando estén disponibles en OpenAI
   - Ajustes dinámicos de dimensionalidad según caso de uso

2. **Optimizaciones de Rendimiento**
   - Implementación de estrategias de paralelización para batches grandes
   - Compresión de embeddings para reducir uso de memoria y almacenamiento
   - Optimización de streaming para procesar textos extensos

3. **Funcionalidades Avanzadas**
   - API para cálculo de similitud entre embeddings directamente en el servicio
   - Implementación de pre-computación en background para textos frecuentes
   - Integración con servicios de análisis para retroalimentación sobre calidad de embeddings
