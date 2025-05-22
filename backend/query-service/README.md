# Query Service (Refactorizado)

Microservicio especializado para procesamiento RAG (Retrieval Augmented Generation) optimizado para trabajar exclusivamente con modelos LLM de Groq. Esta versión es una refactorización simplificada que elimina dependencias innecesarias y optimiza el flujo de trabajo.

## Descripción General

El Query Service procesa consultas RAG recibiendo embeddings pre-calculados desde el Agent Service. Realiza búsquedas vectoriales eficientes en Supabase y utiliza Groq para generar respuestas contextuales basadas en los documentos recuperados.

### Características Principales

- Procesamiento RAG simplificado y eficiente
- Integración optimizada con Groq como único proveedor LLM
- Manejo inteligente de fallbacks cuando no hay resultados relevantes
- Sistema centralizado de manejo de errores
- Tracking de tokens a través de las respuestas de Groq

## Arquitectura Simplificada

El servicio sigue una arquitectura minimalista con las siguientes capas:

1. **API (routes)**: Endpoints internos para el Agent Service
2. **Servicios (services)**: Procesador de consultas y búsqueda vectorial
3. **Proveedor (provider)**: Cliente Groq optimizado
4. **Modelos (models)**: Estructuras de datos para consultas y respuestas
5. **Configuración (config)**: Ajustes simplificados

## Endpoints Principales

### Consultas RAG Internas

```
POST /api/v1/internal/query
```

**Parámetros:**
- `tenant_id` (string): ID del tenant
- `query` (string): Consulta en lenguaje natural
- `query_embedding` (array): Vector de embedding pre-calculado
- `collection_id` (string): ID de la colección a consultar
- `agent_id` (string, opcional): ID del agente
- `conversation_id` (string, opcional): ID de la conversación
- `similarity_top_k` (int, opcional): Número de documentos a recuperar (default: 4)
- `llm_model` (string, opcional): Modelo Groq específico
- `agent_description` (string, opcional): Descripción del agente para respuestas fallback
- `fallback_behavior` (string, opcional): Estrategia para casos sin resultados relevantes
- `relevance_threshold` (float, opcional): Umbral para determinar documentos relevantes

**Respuesta:**
```json
{
  "success": true,
  "message": "Consulta procesada correctamente",
  "data": {
    "query": "¿Cuál es la política de devoluciones?",
    "response": "Según la información proporcionada, las devoluciones...",
    "sources": [
      {
        "content": "Fragmento del documento relevante...",
        "metadata": { "doc_id": "abc123", "title": "Políticas" },
        "similarity": 0.89
      }
    ]
  },
  "metadata": {
    "model": "llama3-70b-8192",
    "found_documents": 8,
    "used_documents": 4,
    "source_quality": "high", 
    "processing_time": 0.543,
    "total_time": 0.672,
    "token_usage": {
      "prompt_tokens": 256,
      "completion_tokens": 128,
      "total_tokens": 384
    }
  }
}
```

### Búsqueda de Documentos

```
POST /api/v1/internal/search
```

**Parámetros:**
- `tenant_id` (string): ID del tenant
- `query_embedding` (array): Vector de embedding pre-calculado
- `collection_id` (string): ID de la colección
- `limit` (int, opcional): Número máximo de resultados (default: 5)
- `similarity_threshold` (float, opcional): Umbral de similitud (default: 0.7)

**Respuesta:**
```json
{
  "success": true,
  "message": "Búsqueda completada",
  "data": {
    "documents": [
      {
        "id": "doc123",
        "content": "Contenido del documento...",
        "metadata": { "source": "manual.pdf", "page": 5 },
        "similarity": 0.92
      }
    ]
  },
  "metadata": {
    "total_time": 0.123,
    "threshold": 0.7
  }
}
```

## Estrategias de Fallback

El servicio implementa manejo inteligente de casos donde la búsqueda vectorial no produce resultados relevantes:

1. **Con documentos relevantes**: Utiliza el flujo RAG tradicional
2. **Con documentos poco relevantes**: Combina contexto parcial con conocimiento del agente
3. **Sin documentos**: Genera respuesta basada en la descripción del agente

## Estructura de Archivos

```
/query-service
├── config/                # Configuraciones simplificadas
├── models/                # Estructuras de datos
├── provider/              # Cliente Groq
├── routes/                # Endpoints de API
├── services/              # Lógica de negocio
├── main.py                # Punto de entrada
└── requirements.txt       # Dependencias optimizadas
```

## Dependencias Principales

- FastAPI: Framework web
- Groq: Cliente para modelos LLM
- Supabase: Almacenamiento vectorial
- Redis: Caché opcional

## Configuración y Despliegue

1. Instalar dependencias: `pip install -r requirements.txt`
2. Configurar variables de entorno:
   - `GROQ_API_KEY`: Clave API de Groq
   - `SUPABASE_URL`: URL de la instancia Supabase
   - `SUPABASE_KEY`: Clave de servicio Supabase
3. Iniciar servicio: `uvicorn main:app --host 0.0.0.0 --port 8002`
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
