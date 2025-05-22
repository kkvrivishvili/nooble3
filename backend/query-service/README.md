# Query Service (Refactorizado)

Microservicio especializado para procesamiento RAG (Retrieval Augmented Generation) optimizado para trabajar exclusivamente con modelos LLM de Groq. Esta versión representa una refactorización completa que elimina dependencias innecesarias, simplifica la arquitectura y mejora la mantenibilidad del código.

## Descripción General

El Query Service es un componente fundamental en la arquitectura de backend de Nooble, responsable de procesar consultas utilizando técnicas de RAG (Retrieval Augmented Generation). El servicio recibe solicitudes del Agent Service, que incluyen consultas de usuario y embeddings pre-calculados, procesa estas solicitudes mediante búsquedas vectoriales en Supabase, y genera respuestas contextuales utilizando los modelos de lenguaje de Groq.

### Características Principales

- **Procesamiento RAG simplificado**: Implementación eficiente sin dependencias de frameworks externos como LlamaIndex
- **Arquitectura centrada en Groq**: Optimización exclusiva para modelos LLM de Groq
- **Manejo inteligente de fallbacks**: Sistema sofisticado para manejar casos donde no hay resultados relevantes
- **Sistema centralizado de manejo de errores**: Gestión consistente de excepciones en toda la aplicación
- **Tracking preciso de tokens**: Métricas detalladas sobre uso de tokens directamente desde la API de Groq
- **Estructura modular y limpia**: Código organizado siguiendo principios de responsabilidad única

## Arquitectura y Componentes

El servicio sigue una arquitectura de capas bien definida que prioriza la simplicidad y la separación de responsabilidades:

### Capas Principales

1. **API (routes/)**: 
   - Maneja los endpoints HTTP y la validación de solicitudes
   - Implementa middleware para autenticación y manejo de errores
   - Traduce solicitudes HTTP a llamadas de servicio

2. **Servicios (services/)**: 
   - Contiene la lógica de negocio principal
   - Implementa el procesador de consultas RAG (`query_processor.py`)
   - Gestiona la búsqueda vectorial (`vector_store.py`)

3. **Proveedor (provider/)**: 
   - Encapsula la integración con Groq LLM
   - Implementa cliente optimizado con manejo de conexiones
   - Ofrece funcionalidades para respuestas síncronas y streaming

4. **Modelos (models/)**: 
   - Define estructuras de datos para solicitudes y respuestas
   - Implementa validación mediante Pydantic
   - Estandariza la comunicación entre componentes

5. **Configuración (config/)**: 
   - Centraliza ajustes y parámetros del servicio
   - Implementa carga de variables de entorno
   - Define constantes y valores predeterminados

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────┐
│                  Agent Service                      │
└───────────────────────┬─────────────────────────────┘
                        │ Solicitudes RAG (query + embeddings)
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Query Service                     │
│                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────┐  │
│  │  API Routes │───▶│  Servicios  │───▶│ Groq LLM│  │
│  └─────────────┘    └──────┬──────┘    └─────────┘  │
│                           │                          │
│                           ▼                          │
│                   ┌─────────────┐                    │
│                   │  Supabase   │                    │
│                   │ Vector DB   │                    │
│                   └─────────────┘                    │
└─────────────────────────────────────────────────────┘
```

## Flujo de Procesamiento RAG

El flujo de trabajo para procesar consultas RAG sigue estos pasos:

1. **Recepción de la solicitud**:
   - El Agent Service envía una consulta junto con su embedding pre-calculado
   - Se incluyen metadatos como tenant_id, agent_id y collection_id

2. **Búsqueda vectorial**:
   - El servicio busca documentos similares en Supabase usando el embedding
   - Se aplican filtros de metadatos si se especifican en la solicitud
   - Se recuperan los N documentos más similares (configurable)

3. **Evaluación de relevancia**:
   - Se analiza la calidad de los resultados obtenidos
   - Se determina si los documentos superan el umbral de relevancia

4. **Preparación del contexto**:
   - Se construye un prompt con los documentos relevantes
   - Se estructura la información para maximizar el rendimiento del LLM

5. **Generación de respuesta**:
   - Se envía el prompt al modelo de Groq
   - Se procesan los parámetros como temperatura y longitud máxima

6. **Manejo de fallbacks**:
   - Si no hay documentos relevantes, se utiliza la estrategia de fallback configurada
   - Opciones: respuesta basada en conocimiento del agente, rechazo de consulta, o respuesta genérica

7. **Devolución de resultados**:
   - Se estructura la respuesta con el texto generado y metadatos
   - Se incluyen fuentes utilizadas si se solicitó
   - Se agregan estadísticas de procesamiento

## API de Servicio

El Query Service expone endpoints internos diseñados para ser consumidos exclusivamente por el Agent Service. Estos endpoints siguen un diseño RESTful y utilizan JSON para la comunicación.

### Endpoints Principales

#### Consultas RAG Internas

```
POST /api/v1/internal/query
```

Procesa una consulta RAG completa, buscando documentos relevantes y generando una respuesta basada en el contexto recuperado.

**Cabeceras requeridas:**
- `Authorization`: Token de autenticación interno
- `Content-Type`: application/json

**Cuerpo de la solicitud:**
```json
{
  "tenant_id": "tenant_abc123",
  "query": "¿Cuál es la política de devoluciones?",
  "query_embedding": [0.123, 0.456, ...], // Vector de 1536 dimensiones
  "collection_id": "policies_collection",
  "agent_id": "agent_123",
  "conversation_id": "conv_456",
  "similarity_top_k": 4,
  "llm_model": "llama3-70b-8192",
  "include_sources": true,
  "max_sources": 3,
  "agent_description": "Asistente de servicio al cliente especializado en políticas de la tienda",
  "fallback_behavior": "agent_knowledge",
  "relevance_threshold": 0.75
}
```

**Parámetros detallados:**
- `tenant_id` (string, requerido): Identificador del tenant para aislamiento de datos
- `query` (string, requerido): Consulta en lenguaje natural del usuario final
- `query_embedding` (array, requerido): Vector de embedding pre-calculado de la consulta
- `collection_id` (string, requerido): Identificador de la colección vectorial a consultar
- `agent_id` (string, opcional): Identificador del agente para tracking y personalización
- `conversation_id` (string, opcional): Identificador de la conversación para tracking y contexto
- `similarity_top_k` (int, opcional): Número de documentos similares a recuperar (default: 4)
- `llm_model` (string, opcional): Modelo específico de Groq a utilizar (default: configuración global)
- `include_sources` (bool, opcional): Si incluir fuentes de información en la respuesta (default: true)
- `max_sources` (int, opcional): Número máximo de fuentes a incluir en la respuesta (default: 3)
- `agent_description` (string, opcional): Descripción del agente para casos de fallback
- `fallback_behavior` (string, opcional): Estrategia para casos sin resultados relevantes (default: "agent_knowledge")
- `relevance_threshold` (float, opcional): Umbral para considerar documentos realmente relevantes (default: 0.75)

**Respuesta exitosa (200 OK):**
```json
{
  "success": true,
  "message": "Consulta procesada correctamente",
  "data": {
    "query": "¿Cuál es la política de devoluciones?",
    "response": "Según la información proporcionada, las devoluciones de productos no abiertos se aceptan dentro de los 30 días posteriores a la compra con el recibo original. Los productos abiertos pueden recibir un reembolso parcial o crédito de tienda según el estado del producto.",
    "sources": [
      {
        "content": "Las devoluciones de productos no abiertos se aceptan dentro de los 30 días posteriores a la compra con el recibo original...",
        "metadata": { 
          "doc_id": "policy_returns_001", 
          "title": "Política de Devoluciones",
          "section": "General",
          "last_updated": "2025-01-15"
        },
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

**Respuesta de error (4xx/5xx):**
```json
{
  "success": false,
  "message": "Error procesando consulta",
  "data": {},
  "metadata": {
    "error_time": 0.123
  },
  "error": {
    "type": "ServiceError",
    "code": "DOCUMENT_NOT_FOUND",
    "message": "No se encontró la colección especificada"
  }
}
```

#### Búsqueda de Documentos

```
POST /api/v1/internal/search
```

Realiza una búsqueda vectorial sin generación de respuesta, útil para implementar funcionalidades como sugerencias o navegación de documentos.

**Cabeceras requeridas:**
- `Authorization`: Token de autenticación interno
- `Content-Type`: application/json

**Cuerpo de la solicitud:**
```json
{
  "tenant_id": "tenant_abc123",
  "query_embedding": [0.123, 0.456, ...],
  "collection_id": "policies_collection",
  "limit": 5,
  "similarity_threshold": 0.7,
  "metadata_filter": {
    "document_type": "manual"
  }
}
```

**Parámetros detallados:**
- `tenant_id` (string, requerido): Identificador del tenant para aislamiento de datos
- `query_embedding` (array, requerido): Vector de embedding pre-calculado
- `collection_id` (string, requerido): Identificador de la colección vectorial
- `limit` (int, opcional): Número máximo de resultados (default: 5)
- `similarity_threshold` (float, opcional): Umbral mínimo de similitud (default: 0.7)
- `metadata_filter` (object, opcional): Filtros adicionales basados en metadatos

**Respuesta exitosa (200 OK):**
```json
{
  "success": true,
  "message": "Búsqueda completada",
  "data": {
    "documents": [
      {
        "id": "doc123",
        "content": "Las devoluciones de productos no abiertos se aceptan dentro de los 30 días...",
        "metadata": { 
          "source": "manual.pdf", 
          "page": 5,
          "document_type": "manual"
        },
        "similarity": 0.92
      }
    ]
  },
  "metadata": {
    "total_time": 0.123,
    "threshold": 0.7,
    "filter_applied": true
  }
}
```

### Verificación de Estado

```
GET /api/v1/health
```

Endpoint de health check para monitoreo y verificación de disponibilidad del servicio.

**Respuesta (200 OK):**
```json
{
  "status": "ok",
  "version": "1.2.0",
  "environment": "production",
  "timestamp": "2025-05-22T22:51:39Z",
  "components": {
    "supabase": "ok",
    "groq": "ok"
  }
}
```

## Sistema de Manejo de Fallbacks

Una de las características más avanzadas del Query Service refactorizado es su sofisticado sistema de manejo de fallbacks. Este sistema está diseñado para proporcionar respuestas útiles incluso cuando la búsqueda vectorial no produce resultados relevantes.

### Niveles de Calidad de Fuentes

El servicio clasifica los resultados de búsqueda en tres niveles de calidad:

- **Alta calidad** (`source_quality: "high"`): Al menos un documento supera el umbral de relevancia configurado
- **Baja calidad** (`source_quality: "low"`): Se encontraron documentos pero ninguno supera el umbral de relevancia
- **Sin resultados** (`source_quality: "none"`): No se encontraron documentos que coincidan con la consulta

### Estrategias de Fallback

El servicio implementa tres estrategias principales para manejar casos donde no hay resultados suficientemente relevantes:

#### 1. Conocimiento del Agente (`fallback_behavior: "agent_knowledge"`)

Cuando se configura esta estrategia (predeterminada), el servicio genera una respuesta basada en:

- La descripción del agente proporcionada en la solicitud
- El conocimiento general incorporado en el modelo LLM
- Contexto parcialmente relevante (si existe)

**Ejemplo de system prompt para esta estrategia:**
```
Eres un asistente útil que representa a un agente. 
{agent_description}
Si no puedes responder con confianza, indícalo claramente.
```

#### 2. Rechazo de Consulta (`fallback_behavior: "reject_query"`)

Esta estrategia es más conservadora y rechaza directamente consultas para las que no hay información relevante disponible:

```json
{
  "response": "No dispongo de información para responder a esta pregunta.",
  "sources": [],
  "metadata": {
    "found_documents": 0,
    "source_quality": "none"
  }
}
```

#### 3. Respuesta Genérica (`fallback_behavior: "generic_response"`)

Esta estrategia proporciona una respuesta genérica sin utilizar ni la descripción del agente ni datos parcialmente relevantes:

**Ejemplo de system prompt para esta estrategia:**
```
Eres un asistente útil que puede responder preguntas generales.
Esta consulta está fuera del ámbito de conocimiento específico disponible.
Proporciona una respuesta genérica útil.
```

### Implementación Técnica

La implementación se encuentra en `services/query_processor.py` y utiliza diferentes templates de prompts según la estrategia y la calidad de las fuentes. El módulo determina automáticamente qué estrategia aplicar basándose en:

1. El parámetro `fallback_behavior` de la solicitud
2. La disponibilidad de documentos relevantes
3. La comparación de puntuaciones de similitud con el umbral configurado

## Estructura de Archivos

El servicio sigue una estructura de directorios clara y modular:

```
/query-service
├── config/                # Configuraciones del servicio
│   ├── __init__.py         # Exportación de configuraciones
│   └── settings.py         # Definiciones de configuración
├── models/                # Estructuras de datos
│   ├── __init__.py         # Exportación de modelos
│   └── query.py            # Definiciones de modelos de consulta
├── provider/              # Integración con proveedores LLM
│   ├── __init__.py         # Exportación de proveedores
│   └── groq.py             # Cliente Groq optimizado
├── routes/                # Endpoints API
│   ├── __init__.py         # Exportación de rutas
│   ├── collections.py      # Operaciones sobre colecciones
│   └── internal.py         # Endpoints internos para Agent Service
├── services/              # Lógica de negocio
│   ├── __init__.py         # Exportación de servicios
│   ├── query_processor.py  # Procesador de consultas RAG
│   └── vector_store.py     # Interfaz con almacenamiento vectorial
├── utils/                 # Utilidades comunes
│   └── __init__.py         # Exportación de utilidades
├── main.py                # Punto de entrada de la aplicación
├── requirements.txt       # Dependencias del proyecto
└── README.md              # Documentación del servicio
```

## Dependencias Principales

El servicio ha sido optimizado para mantener un conjunto mínimo de dependencias:

### Core
- **FastAPI**: Framework web de alto rendimiento para APIs
- **Uvicorn**: Servidor ASGI para FastAPI
- **Pydantic**: Validación de datos y serialización

### LLM
- **Groq**: Cliente oficial para interactuar con modelos LLM de Groq

### Almacenamiento
- **Supabase**: Cliente para PostgreSQL con extensión pgvector
- **Redis**: Para caché opcional y operaciones de alta velocidad

### Utilidades
- **Python-dotenv**: Carga de variables de entorno
- **Tenacity**: Mecanismos de reintentos y resiliencia
- **aiohttp**: Cliente HTTP asíncrono

## Configuración y Despliegue

### Variables de Entorno

Crea un archivo `.env` en el directorio raíz con las siguientes variables:

```env
# Configuración general
ENVIRONMENT=development  # development, staging, production
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
SERVICE_NAME=query-service
SERVICE_VERSION=1.0.0

# Credenciales Groq
GROQ_API_KEY=gsk_your_api_key
DEFAULT_GROQ_MODEL=llama3-70b-8192

# Configuración Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-key
SUPABASE_VECTOR_TABLE=documents

# Parámetros RAG
DEFAULT_SIMILARITY_THRESHOLD=0.7
DEFAULT_TOP_K=4
```

### Instalación y Ejecución

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/your-org/nooble-backend.git
   cd nooble-backend/query-service
   ```

2. **Crear entorno virtual (opcional pero recomendado):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecutar el servicio:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8002 --reload
   ```
   El flag `--reload` es útil durante desarrollo para recargar automáticamente cuando se modifican archivos.

### Despliegue en Producción

Para entornos de producción, se recomienda:

1. **Utilizar Gunicorn como gestor de procesos:**
   ```bash
   gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8002
   ```

2. **Configurar un proxy inverso** (Nginx o similar) delante del servicio.

3. **Implementar monitoreo** con Prometheus y Grafana para seguimiento de métricas.

## Próximos Pasos

El Query Service ha sido significativamente refactorizado para mejorar su mantenibilidad y rendimiento. Sin embargo, hay varias mejoras potenciales que podrían implementarse en el futuro:

### 1. Optimizaciones de Rendimiento

- **Implementación de Caché**: Agregar caché de consultas frecuentes para reducir llamadas a la base de datos y al LLM.
- **Agrupamiento de Consultas (Batching)**: Procesar múltiples consultas en paralelo para mejorar el throughput.
- **Streaming Optimizado**: Mejorar el streaming de respuestas para reducir la latencia percibida.

### 2. Mejoras Funcionales

- **Reranking de Resultados**: Implementar un paso adicional de reordenamiento para mejorar la relevancia.
- **Modos de Respuesta Adicionales**: Agregar opciones como respuestas estructuradas (JSON), extractivas o conversacionales.
- **Logging Avanzado**: Mejorar el sistema de logging para facilitar el análisis y depuración.

### 3. Integraciones

- **Expandir Conectores de Vector Store**: Agregar soporte para otras bases de datos vectoriales como Pinecone o Qdrant.
- **Soporte Multi-Proveedor**: Facilitar la adición de otros proveedores LLM manteniendo la arquitectura simplificada.

### 4. Seguridad y Gobernanza

- **Autenticación Más Robusta**: Implementar esquemas de autenticación más sofisticados para endpoints internos.
- **Auditoria de Consultas**: Agregar capacidades de auditoria y seguimiento de consultas para cumplimiento normativo.
- **Rate Limiting Avanzado**: Implementar control de tasas más granular por tenant y tipo de operación.

## Contribuciones

Si deseas contribuir al desarrollo del Query Service, por favor sigue estas pautas:

1. Crea un fork del repositorio
2. Crea una rama para tu funcionalidad (`git checkout -b feature/amazing-feature`)
3. Realiza tus cambios siguiendo el estilo de código establecido
4. Ejecuta las pruebas locales
5. Envía un pull request

## Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo LICENSE.
