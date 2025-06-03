# Embedding Service

## Descripción
Microservicio optimizado que proporciona capacidades de generación de embeddings vectoriales para el sistema RAG (Retrieval Augmented Generation), utilizando exclusivamente modelos de OpenAI. Este servicio es fundamental para transformar texto en representaciones numéricas que permiten la búsqueda semántica en el sistema.

## 🏗️ Ecosistema de Servicios

La arquitectura se organiza en 3 niveles jerárquicos:

### Nivel 1: Orquestación

- **Agent Orchestrator**: Punto de entrada único, gestión de sesiones y coordinación global

### Nivel 2: Servicios Funcionales

- **Conversation Service**: Historial y contexto de conversaciones
- **Workflow Engine**: Flujos de trabajo complejos multi-etapa
- **Agent Execution**: Lógica específica del agente
- **Tool Registry**: Registro y ejecución de herramientas

### Nivel 3: Servicios de Infraestructura

- **Query Service**: Procesamiento RAG y LLM
- **Embedding Service**: Generación de embeddings vectoriales
- **Ingestion Service**: Procesamiento de documentos

> 📌 **Este documento describe el Embedding Service**, ubicado en el Nivel 3 como servicio de infraestructura especializado en la generación de vectores semánticos

## Características

- Generación de embeddings de alta calidad utilizando modelos de OpenAI
- Único endpoint optimizado para facilitar la integración
- Soporte para tracking centralizado de tokens
- Validaciones de seguridad y límites de uso
- Manejo de errores estandarizado

## Arquitectura

El servicio sigue una arquitectura simplificada:

```
Agent Service
    ↓
EnhancedEmbeddingRequest
    ↓
Embedding Service (validate)
    ↓
OpenAI Provider (generate)
    ↓
EnhancedEmbeddingResponse
    ↓
Agent Service → Query Service
```

## 🔄 Flujos de Trabajo Principales

### 1. Consulta Normal (Participación del Embedding Service)
```
Cliente → Orchestrator → Agent Execution → Embedding Service → Query → Respuesta
```

### 2. Ingestión de Documentos
```
Cliente → Orchestrator → Workflow Engine → Ingestion Service → Embedding Service → Notificación de completado
```

> 🔍 **Rol del Embedding Service**: Transformar texto en representaciones vectoriales que permiten búsquedas semánticas y contextualmente relevantes en el sistema RAG.

## Estructura

```
embedding-service/
├── models/
│   ├── __init__.py
│   └── embeddings.py          # EmbeddingRequest, EmbeddingResponse
├── provider/
│   ├── __init__.py
│   └── openai.py              # Implementación del proveedor de OpenAI
├── routes/
│   ├── __init__.py
│   ├── embeddings.py          # Endpoint único de API
│   └── health.py              # Health check
├── config/
│   ├── __init__.py
│   └── settings.py            # Configuraciones centralizadas
├── queue/                   # Sistema de cola de trabajo (para implementar)
│   ├── __init__.py             # Inicialización del módulo
│   ├── worker.py               # Configuración de workers
│   ├── producer.py             # Métodos para encolar tareas
│   └── tasks.py                # Definición de tareas asíncronas
├── main.py                 # Punto de entrada de la aplicación FastAPI
├── requirements.txt
├── Dockerfile
└── README.md
```

## Instalación

```bash
# Clonar el repositorio
git clone <repositorio>

# Instalar dependencias
cd embedding-service
pip install -r requirements.txt

# Ejecutar el servicio
uvicorn main:app --host 0.0.0.0 --port 8001
```

## Configuración

El servicio utiliza variables de entorno para la configuración:

- `EMBEDDING_OPENAI_API_KEY`: Clave de API para OpenAI (requerida)
- `EMBEDDING_DEFAULT_EMBEDDING_MODEL`: Modelo predeterminado (default: "text-embedding-3-small")
- `EMBEDDING_MAX_BATCH_SIZE`: Tamaño máximo de lote (default: 100)
- `EMBEDDING_MAX_TEXT_LENGTH`: Longitud máxima de texto (default: 8000)
- `EMBEDDING_OPENAI_TIMEOUT_SECONDS`: Timeout para llamadas a OpenAI (default: 30)

## Funciones Clave
1. Generación de embeddings de alta calidad utilizando modelos de OpenAI
2. Procesamiento por lotes de textos para optimizar rendimiento
3. Tracking de uso de tokens por tenant y operación
4. Validación y normalización de textos para embeddings

## Sistema de Cola de Trabajo

Para manejar de manera eficiente las solicitudes de embeddings por lotes, especialmente para operaciones de ingestado de documentos, el Embedding Service implementa un sistema simple de cola de trabajo basado en Redis Queue (RQ).

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Embedding Service

```
+-------------------------------------+
|          COLAS DE EMBEDDING         |
+-------------------------------------+
|                                     |
| embedding_tasks:{tenant_id}         | → Cola principal de tareas
| embedding_results:{tenant_id}:{id}  | → Resultados temporales
| embedding_batch:{tenant_id}:{batch} | → Procesos de ingestado
|                                     |
+-------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Procesamiento por lotes**: Optimización para grandes volúmenes de texto
- **Priorización de tareas**: Consultas interactivas priorizadas sobre ingestado masivo
- **Tracking de tokens**: Monitoreo detallado del uso por tenant

### Implementación del Sistema de Colas:

```python
# queue/job_manager.py
import uuid
from redis import Redis
from rq import Queue

# Configuración de Redis y cola única
redis_conn = Redis(host=os.getenv('REDIS_HOST', 'redis'), 
                  port=int(os.getenv('REDIS_PORT', 6379)), 
                  db=int(os.getenv('REDIS_DB', 0)))
embedding_queue = Queue('embedding_tasks', connection=redis_conn)

# Registro simple de trabajos
job_registry = {}

def enqueue_embedding_task(texts, tenant_id, collection_id=None, metadata=None):
    """Encola una tarea de generación de embeddings y devuelve un job_id"""
    from provider.openai import generate_embeddings
    
    job_id = str(uuid.uuid4())
    job_data = {
        "texts": texts,
        "tenant_id": tenant_id,
        "collection_id": collection_id,
        "metadata": metadata or {}
    }
    
    # Registrar trabajo
    job_registry[job_id] = {"status": "pending"}
    
    # Encolar tarea
    job = embedding_queue.enqueue(
        generate_embeddings,
        job_data,
        job_id=job_id,
        result_ttl=3600  # Mantener resultado 1 hora
    )
    
    # Callback cuando finalice (empleando meta)
    job.meta['job_id'] = job_id
    job.meta['tenant_id'] = tenant_id
    job.save_meta()
    
    return {"job_id": job_id}
```

### Worker Simple:

```python
# queue/worker.py
import os
from redis import Redis
from rq import Worker, Queue, Connection
from websocket.notifier import notify_job_completed

def process_result(job, connection, result, exception=None):
    """Maneja el resultado del trabajo y notifica al orquestador"""
    job_id = job.meta.get('job_id')
    tenant_id = job.meta.get('tenant_id')
    
    if exception is None and job_id:
        # Notificar éxito vía WebSocket
        notify_job_completed(job_id, result, tenant_id)

# Configuración del worker
redis_conn = Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0))
)

def run_worker():
    with Connection(redis_conn):
        worker = Worker(['embedding_tasks'], exception_handlers=[process_result])
        worker.work(with_scheduler=True)

if __name__ == '__main__':
    run_worker()
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Hub de conexión**: Integración con el servidor WebSocket centralizado del Agent Orchestrator
- **Notificación automática**: Actualización en tiempo real cuando los embeddings están listos
- **Reconexión inteligente**: Mecanismo de backoff exponencial para conexiones robustas
- **Autenticación por token**: Seguridad en las comunicaciones inter-servicio

### Eventos Específicos del Embedding Service

- `embeddings_generated`: Vectores generados exitosamente
- `batch_progress_update`: Actualización de progreso en procesos por lotes
- `embedding_failed`: Error en la generación de embeddings

### Integración con WebSocket para Notificaciones:

```python
# websocket/notifier.py
import asyncio
import websockets
import json

ORCHESTRATOR_WS_URL = "ws://agent-orchestrator:8000/ws/task_updates"

async def notify_job_completed(job_id, result, tenant_id):
    """Notifica al orquestador que un trabajo ha terminado"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "job_completed",
                "service": "embedding",
                "job_id": job_id,
                "tenant_id": tenant_id,
                "result": result
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        print(f"Error al notificar via WebSocket: {e}")
```

### Adición al requirements.txt:
```
rq==1.15.1
redis>=4.5.1
websockets>=10.0
```

## Comunicación
- **HTTP**: API REST para iniciar tareas (endpoints síncronos y asíncronos)
- **WebSocket**: Notificaciones en tiempo real al Agent Orchestrator cuando se completan tareas asíncronas
- **Comunicación Centralizada**: Toda comunicación pasa a través del Agent Orchestrator Service

## Integración con otros Servicios
El Embedding Service se comunica **principalmente** con:

1. **Agent Orchestrator Service**: Como punto de entrada principal para solicitudes de embeddings.
2. **Ingestion Service**: Única excepción que puede comunicarse directamente para procesar documentos durante la ingestión.

Aspectos clave de la integración:
- No se comunica directamente con Query Service (esta comunicación es gestionada por el orquestador)
- Mantiene un tracking centralizado de uso de tokens OpenAI
- Opera exclusivamente con modelos de embeddings de OpenAI para mantener consistencia

## API

### Endpoint: `/api/v1/internal/enhanced_embed`

**Método**: POST

**Descripción**: Genera embeddings para los textos proporcionados.

**Request Body**:

```json
{
  "texts": ["Texto para generar embedding"],
  "model": "text-embedding-3-large",  // Opcional
  "tenant_id": "tenant123",
  "collection_id": "collection456",  // Opcional, para tracking
  "chunk_ids": ["chunk1", "chunk2"],  // Opcional, para tracking
  "metadata": {                       // Opcional
    "source": "agent_service",
    "purpose": "query"
  }
}
```

**Response**:

```json
{
  "success": true,
  "message": "Embeddings generados correctamente",
  "embeddings": [[0.1, 0.2, ...]],
  "model": "text-embedding-3-large",
  "dimensions": 3072,
  "processing_time": 0.156,
  "total_tokens": 10
}
```

## Integración con Agent Service

El Agent Service utiliza este servicio como herramienta para generar embeddings de consultas y respuestas en el flujo RAG. La integración típica es:

### Ejemplo de Código de Integración:

```python
import httpx
from models import EnhancedEmbeddingRequest

async def get_embeddings_for_query(query_text, tenant_id, collection_id=None):
    """Obtiene embeddings para una consulta de usuario."""
    
    request = EnhancedEmbeddingRequest(
        texts=[query_text],
        tenant_id=tenant_id,
        collection_id=collection_id,
        metadata={"source": "agent_service", "purpose": "query"}
    )
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://embedding-service:8001/api/v1/internal/enhanced_embed",
            json=request.dict(exclude_none=True)
        )
        
    if response.status_code == 200:
        result = response.json()
        return result["embeddings"][0]  # Primer embedding
    else:
        raise ValueError(f"Error en embedding service: {response.text}")
```

## 🌐 Integración en el Ecosistema

### Formato Estandarizado de Mensajes

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "service": "embedding",
  "metadata": {
    "collection_id": "optional-collection-id",
    "model": "text-embedding-3-small|text-embedding-3-large",
    "source": "query|ingestion|batch",
    "priority": 0-9
  },
  "payload": {
    "texts": ["texto1", "texto2"],
    "dimensions": 1536,
    "batch_size": 100
  }
}
```

### Flujo de Trabajo en el Sistema RAG

1. **Agent Service** recibe consulta del usuario
2. **Agent Service** solicita embeddings al **Embedding Service**
3. **Embedding Service** genera vectores utilizando OpenAI
4. **Agent Service** utiliza embeddings para buscar en el **Query Service**
5. **Query Service** encuentra documentos relevantes
6. **Agent Service** genera respuesta con contexto enriquecido

### Beneficios de la Arquitectura

- **Escalabilidad**: Servicio especializado que puede escalarse independientemente
- **Resilencia**: Fallos aislados no afectan a todo el sistema
- **Optimización**: Procesamiento por lotes para eficiencia en costos y rendimiento
- **Flexibilidad**: Fácil cambio de proveedor de embeddings sin afectar otros servicios

## Monitoreo y Métricas

El servicio registra automáticamente:
- Uso de tokens por tenant y modelo
- Tiempos de respuesta
- Errores y excepciones

## Soporte de Modelos

El servicio soporta los siguientes modelos de OpenAI:

| Modelo | Dimensiones | Recomendado para |
|--------|------------|------------------|
| text-embedding-3-small | 1536 | Uso general, mejor balance costo/rendimiento |
| text-embedding-3-large | 3072 | Alta precisión, tareas complejas |
| text-embedding-ada-002 | 1536 | Compatibilidad con sistemas legacy |

## Buenas Prácticas

1. **Batch de solicitudes**: Cuando sea posible, enviar múltiples textos en una sola solicitud.
2. **Tamaño de texto**: Mantener textos dentro de límites razonables (<8000 caracteres).
3. **Tenant ID**: Siempre especificar un tenant_id válido para tracking correcto.
4. **Manejo de errores**: Implementar reintentos con backoff exponencial para errores transitorios.
