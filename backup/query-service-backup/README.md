# Servicio de Consultas (Query Service)

Microservicio especializado para realizar consultas basadas en documentos utilizando modelos LLM de Groq, diseñado como parte del ecosistema Nooble.

## Descripción General

El servicio de consultas proporciona una interfaz unificada para interactuar con documentos y colecciones mediante consultas en lenguaje natural. Utiliza modelos LLM de Groq para generar respuestas contextuales basadas en documentos almacenados en colecciones vectoriales.

### Características Principales

- Consultas en lenguaje natural sobre colecciones de documentos
- Generación de respuestas contextuales usando modelos avanzados de Groq
- Soporte para streaming de respuestas
- Manejo optimizado de contexto y relevancia
- Integración con servicio de embeddings para recuperación semántica
- Monitoreo de uso de tokens y rendimiento

## Arquitectura

El servicio sigue una arquitectura de microservicios con las siguientes capas:

1. **Capa de API (routes)**: Endpoints para consultas, gestión de colecciones y monitoreo
2. **Capa de Servicio (services)**: Lógica de negocio para consultas y generación de respuestas
3. **Capa de Proveedor (provider)**: Integración con modelos LLM de Groq
4. **Capa de Configuración (config)**: Ajustes y constantes del servicio

## Endpoints Principales

### Consultas sobre Colecciones

```
POST /api/query/collection/{collection_id}
```

**Parámetros:**
- `query` (string): Consulta en lenguaje natural
- `model` (string, opcional): Modelo LLM a utilizar
- `temperature` (float, opcional): Temperatura para generación (0.0-1.0)
- `similarity_top_k` (int, opcional): Número de fragmentos similares a recuperar
- `response_mode` (string, opcional): Modo de respuesta (compact, refine, tree_summarize)

**Respuesta:**
```json
{
  "success": true,
  "message": "Consulta procesada correctamente",
  "data": {
    "response": "Lorem ipsum dolor sit amet...",
    "context": {
      "sources": [
        {
          "document_id": "doc123",
          "chunk_id": "chunk456",
          "content": "Fragmento relevante del documento",
          "similarity": 0.92
        }
      ]
    }
  },
  "metadata": {
    "model": "llama3-70b-8192",
    "provider": "groq",
    "token_usage": {
      "prompt_tokens": 256,
      "completion_tokens": 128,
      "total_tokens": 384
    },
    "latency_ms": 235
  }
}
```

### Streaming de Respuestas

```
POST /api/query/collection/{collection_id}/stream
```

**Parámetros:** (Mismos que endpoint no-streaming)

**Respuesta:** Stream de eventos SSE (Server-Sent Events) con formato:

```
event: data
data: {"text": "fragmento de texto generado", "done": false}

event: data
data: {"text": "otro fragmento", "done": false}

...

event: data
data: {"text": "último fragmento", "done": true, "metadata": {...}}
```

## Modelos LLM de Groq Soportados

El servicio utiliza modelos LLM alojados en Groq Cloud, optimizados para inferencia de alta velocidad:

| Modelo | Contexto | Descripción | Caso de Uso | Tokens Máx. |
|--------|----------|-------------|-------------|-------------|
| llama3-8b-8192 | 8192 | Llama 3 8B | General, eficiente en recursos | 4096 |
| llama3-70b-8192 | 8192 | Llama 3 70B | Alta calidad, conocimientos generales | 4096 |
| llama-3.3-70b-versatile | 8192 | Llama 3.3 70B Versatile | Tareas complejas, mayor coherencia | 4096 |
| llama-3.1-8b-instant | 8192 | Llama 3.1 8B Instant | Respuestas rápidas, menos recursos | 4096 |
| gemma-2-9b-it | 8192 | Gemma 2 9B Instruction Tuned | Precisión en instrucciones específicas | 4096 |

### Comparación de Rendimiento

| Modelo | Latencia Promedio | Tokens/segundo | Uso recomendado |
|--------|-------------------|----------------|-----------------|
| llama3-8b-8192 | Baja | ~80-120 | Bots de chat, respuestas rápidas |
| llama3-70b-8192 | Media | ~60-90 | Consultas con conocimiento extenso |
| llama-3.3-70b-versatile | Media-Alta | ~50-80 | Análisis de documentos complejos |
| llama-3.1-8b-instant | Muy Baja | ~90-140 | Interacciones en tiempo real |
| gemma-2-9b-it | Baja | ~70-110 | Tareas con instrucciones específicas |

## Integración con Groq

El servicio implementa una integración optimizada con la API de Groq mediante la clase `GroqLLM` en `provider/groq.py`:

```python
from provider.groq import GroqLLM

# Inicializar modelo LLM de Groq
llm = GroqLLM(
    model="llama3-70b-8192",
    temperature=0.7,
    max_tokens=4096
)

# Generar respuesta
response = await llm.predict(
    prompt="Explica la historia de la IA",
    system_prompt="Responde de manera concisa y educativa"
)

# Soporte para streaming
async for chunk in llm.stream_generate(
    prompt="Explica la historia de la IA", 
    system_prompt="Sé conciso"
):
    print(chunk, end="", flush=True)
```

### Manejo de Errores de Groq

El servicio implementa un sistema robusto de manejo de errores específicos para Groq:

- `GroqAuthenticationError`: Problemas con API key 
- `GroqRateLimitError`: Límites de tasa excedidos
- `GroqModelNotFoundError`: Modelo solicitado no disponible
- `GroqError`: Errores generales de API

## Gestión de Tokens y Optimización

El servicio implementa estrategias específicas para optimizar el uso de tokens con los modelos de Groq:

1. **Estimación Precisa de Tokens**
   - Conteo específico según modelo (Llama vs Gemma)
   - Monitoreo y registro por tenant y operación

2. **Estrategias de Optimización**
   - Truncado inteligente de contexto para mantener información relevante
   - Filtrado semántico para incluir solo fragmentos de alta relevancia
   - Reutilización de respuestas para consultas similares

3. **Control de Costos**
   - Seguimiento de uso por tenant y modelo
   - Límites configurables por tier de suscripción
   - Alertas de uso excesivo

## Configuración

Principales variables de configuración en `config/settings.py` y `.env`:

- `GROQ_API_KEY` - Clave API para Groq (obligatoria)
- `DEFAULT_GROQ_MODEL` - Modelo predeterminado ("llama3-70b-8192")
- `LLM_DEFAULT_TEMPERATURE` - Temperatura por defecto (0.7)
- `LLM_MAX_TOKENS` - Tokens máximos para respuestas (2048)
- `DEFAULT_SIMILARITY_TOP_K` - Número de fragmentos similares (4)
- `MAX_SIMILARITY_TOP_K` - Límite máximo de fragmentos (10)
- `SIMILARITY_THRESHOLD` - Umbral mínimo de similitud (0.7)

## Buenas Prácticas

1. **Uso Óptimo del Servicio**
   - Proporcionar consultas específicas y concisas
   - Utilizar streaming para respuestas largas
   - Ajustar `similarity_top_k` según la complejidad de la consulta
   - Mantener consultas enfocadas a un tema/dominio específico

2. **Selección de Modelos**
   - Usar `llama3-8b-8192` para consultas simples o cuando la latencia es crítica
   - Usar `llama3-70b-8192` para respuestas de alta calidad o conocimiento general
   - Usar `llama-3.3-70b-versatile` para análisis de documentos complejos
   - Usar `gemma-2-9b-it` para seguimiento preciso de instrucciones específicas

3. **Optimización de Contexto**
   - Limitar el número de documentos en colecciones para mejor relevancia
   - Estructurar documentos con metadatos informativos
   - Utilizar técnicas de fragmentación consistentes

## Monitoreo y Métricas

El servicio registra métricas detalladas para optimización continua:

- **Latencia** - Desglosada por fase (recuperación, generación)
- **Tokens** - Uso por tenant, modelo y tipo de operación
- **Calidad** - Relevancia de fragmentos recuperados
- **Errores** - Seguimiento específico por tipo y causa

## Limitaciones Conocidas

1. La API de Groq puede tener variaciones en latencia según carga del servicio
2. Los modelos tienen una ventana de contexto máxima de 8192 tokens
3. La disponibilidad de modelos específicos depende del servicio de Groq
4. Límites de tasa pueden afectar operaciones de alto volumen

## Evolución y Roadmap

Posibles mejoras futuras:

1. **Adaptación a Nuevos Modelos de Groq**
   - Soporte para futuros modelos con mayores capacidades
   - Ajustes dinámicos según capacidades específicas de cada modelo

2. **Optimizaciones de Rendimiento**
   - Implementación de caché avanzada para respuestas frecuentes
   - Optimización de paralelismo en consultas por lotes

3. **Funcionalidades Avanzadas**
   - Soporte para consultas multi-documento y multi-colección
   - Herramientas de análisis de calidad de respuestas
   - Integración con feedback de usuarios para mejora continua
