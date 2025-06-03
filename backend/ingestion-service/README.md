# Ingestion Service

## Descripción

Ingestion Service es un microservicio especializado responsable de todo el proceso de ingesta de documentos para el sistema RAG (Retrieval Augmented Generation). El servicio maneja la recepción, procesamiento, extracción de texto, chunking y orquestación del almacenamiento de documentos y sus embeddings correspondientes.

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

> 📌 **Este documento describe el Ingestion Service**, ubicado en el Nivel 3 como servicio de infraestructura especializado en el procesamiento y preparación de documentos para el sistema RAG

## Características

- Soporte para múltiples formatos de documentos (PDF, Word, Excel, texto, HTML, imágenes, etc.)
- Procesamiento asíncrono mediante sistema de colas
- Chunking inteligente optimizado para RAG
- Extracción de texto con reconocimiento de estructura
- Gestión de colecciones de documentos
- Ingesta desde múltiples fuentes (archivos, URLs, texto plano)
- Soporte para procesamiento por lotes
- Tracking centralizado de tokens y uso de recursos

## 🔄 Flujos de Trabajo Principales

### 1. Ingestión de Documentos (Flujo principal)
```
Cliente → Orchestrator → Workflow Engine → Ingestion Service → Embedding Service → Notificación de completado
```

### 2. Actualización de Colecciones
```
Cliente → Orchestrator → Ingestion Service → Actualización de metadatos → Notificación
```

> 🔍 **Rol del Ingestion Service**: Procesar documentos en diversos formatos, extraer texto estructurado, dividirlo en chunks optimizados para RAG y coordinar la generación de embeddings y almacenamiento.

## Arquitectura

El servicio sigue una arquitectura de procesamiento modular:

```
Cliente → Ingestion Service → Cola de procesamiento
                ↓
           Validación
                ↓
      Extracción de texto
                ↓
      Chunking inteligente
                ↓
      Embedding Service ← Solicitud de embeddings
                ↓
      Almacenamiento en BD vectorial
                ↓
      Notificación de completado
```

### Componentes Principales

- **routes/ingestion.py**: Endpoints principales para carga de documentos
- **routes/documents.py**: Gestión de documentos existentes
- **routes/collections.py**: Gestión de colecciones de documentos
- **routes/jobs.py**: Monitoreo de trabajos de procesamiento
- **services/chunking.py**: Procesamiento y división de documentos
- **services/embedding.py**: Cliente del servicio de embeddings
- **services/queue.py**: Sistema de colas para procesamiento asíncrono
- **services/storage.py**: Gestión de almacenamiento de archivos
- **services/worker.py**: Workers para procesamiento en segundo plano

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Ingestion Service

```
+--------------------------------------------------+
|             COLAS DE INGESTION                   |
+--------------------------------------------------+
|                                                  |
| ingestion_tasks:{tenant_id}                      | → Cola principal de tareas
| ingestion_batch:{tenant_id}:{batch_id}           | → Lotes de documentos
| ingestion_status:{tenant_id}:{job_id}            | → Estado de procesamiento
| ingestion_collection:{tenant_id}:{collection_id} | → Metadatos de colección 
|                                                  |
+--------------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Procesamiento por lotes**: Optimización para grandes volúmenes de documentos
- **Tracking detallado**: Seguimiento granular del estado de cada documento
- **Reintentos automáticos**: Recuperación ante fallos en procesamiento

### Formato de Mensaje Estandarizado

```json
{
  "job_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "collection_id": "collection-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "document_ingestion|metadata_update|collection_management",
  "priority": 0-9,
  "metadata": {
    "source": "upload|url|text|batch",
    "document_type": "pdf|docx|txt|html|...",
    "workflow_id": "optional-workflow-id"
  },
  "payload": {
    "file_path": "path/to/document", 
    "document_id": "optional-document-id",
    "chunking_strategy": "recursive|sentence|paragraph|...",
    "chunk_size": 1000,
    "chunk_overlap": 200
  }
}
```

## Instalación

```bash
# Clonar el repositorio
git clone <repositorio>

# Instalar dependencias
cd ingestion-service
pip install -r requirements.txt

# Ejecutar el servicio
python main.py
```

## Configuración

El servicio utiliza variables de entorno para su configuración:

```bash
# Configuración del servicio
SERVICE_NAME=ingestion-service
SERVICE_VERSION=1.0.0
LOG_LEVEL=INFO

# Conexiones externas
SUPABASE_URL=
SUPABASE_KEY=
REDIS_URL=redis://redis:6379/0

# Configuración de procesamiento
MAX_WORKERS=4
MAX_QUEUE_SIZE=1000
MAX_DOC_SIZE_MB=20
DEFAULT_CHUNK_SIZE=1000
DEFAULT_CHUNK_OVERLAP=200

# URL del servicio de embeddings
EMBEDDING_SERVICE_URL=http://embedding-service:8000
```

## API

### Endpoints Principales

#### Ingesta de Documentos

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/upload` | POST | Carga y procesa un archivo de documento |
| `/ingest/url` | POST | Procesa y extrae contenido de una URL |
| `/ingest/text` | POST | Procesa texto plano como documento |
| `/ingest/batch/urls` | POST | Procesa un lote de URLs en segundo plano |

#### Gestión de Documentos

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/documents` | GET | Lista documentos por colección |
| `/documents/{document_id}` | GET | Obtiene metadatos de un documento |
| `/documents/{document_id}` | DELETE | Elimina un documento |
| `/documents/{document_id}/content` | GET | Obtiene el contenido de un documento |

#### Gestión de Colecciones

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/collections` | GET | Lista colecciones disponibles |
| `/collections` | POST | Crea una nueva colección |
| `/collections/{collection_id}` | GET | Obtiene detalles de una colección |
| `/collections/{collection_id}` | DELETE | Elimina una colección y sus documentos |

#### Monitoreo de Trabajos

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/jobs/{job_id}` | GET | Obtiene estado de un trabajo de procesamiento |
| `/jobs` | GET | Lista trabajos recientes por tenant |

### Ejemplo de Uso

#### Carga de Documento

```python
import requests

# Datos del documento
files = {"file": open("documento.pdf", "rb")}
data = {
    "collection_id": "mi-coleccion",
    "title": "Mi Documento",
    "description": "Descripción del documento",
    "tags": "tag1,tag2"
}

# Enviar solicitud
response = requests.post(
    "http://ingestion-service:8000/upload",
    files=files,
    data=data,
    headers={"x-tenant-id": "tenant123"}
)

# Verificar resultado
if response.status_code == 202:
    job_id = response.json().get("job_id")
    print(f"Documento en procesamiento. Job ID: {job_id}")
```

#### Verificar Estado del Trabajo

```python
import requests

job_id = "job_123456"

response = requests.get(
    f"http://ingestion-service:8000/jobs/{job_id}",
    headers={"x-tenant-id": "tenant123"}
)

status = response.json()
print(f"Estado: {status['status']}")
print(f"Progreso: {status['progress']}%")
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Comunicación bidireccional con Agent Orchestrator
- **Notificaciones de progreso**: Actualización en tiempo real del estado de procesamiento
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Ingestion Service

- `document_ingestion_started`: Inicio del procesamiento de un documento
- `ingestion_progress_update`: Actualización de progreso con porcentaje
- `document_processing_completed`: Documento completamente procesado
- `document_ingestion_failed`: Error en el procesamiento del documento

### Implementación WebSocket para Notificaciones:

```python
# websocket/notifier.py
import asyncio
import websockets
import json
import logging
from datetime import datetime

ORCHESTRATOR_WS_URL = "ws://agent-orchestrator:8000/ws/task_updates"

logger = logging.getLogger(__name__)

async def notify_ingestion_progress(job_id, tenant_id, progress_percentage, global_task_id=None):
    """Notifica el progreso de un trabajo de ingestión"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "ingestion_progress_update",
                "service": "ingestion",
                "task_id": job_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "progress_percentage": progress_percentage,
                    "status": "processing" if progress_percentage < 100 else "completed"
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar progreso via WebSocket: {e}")

async def notify_ingestion_completed(job_id, tenant_id, result, global_task_id=None):
    """Notifica la finalización de un trabajo de ingestión"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "document_processing_completed",
                "service": "ingestion",
                "task_id": job_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": result
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar completado via WebSocket: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Procesamiento especializado**: Optimización para diferentes tipos de documentos
- **Escalabilidad independiente**: El servicio puede escalarse según la demanda de ingestión
- **Asincronía completa**: Procesamiento en background sin bloquear otras operaciones
- **Flexibilidad en estrategias**: Fácil adaptación a diferentes necesidades de chunking y extracción

## Mejores Prácticas

### Chunking Optimizado

El servicio implementa estrategias avanzadas de chunking:

1. **Chunking por fragmentos semánticos**: Divide el texto respetando la estructura semántica
2. **Solapamiento configurable**: Mantiene contexto entre fragmentos
3. **Metadatos enriquecidos**: Incluye información sobre origen, posición y relaciones

### Procesamiento Eficiente

Para un procesamiento óptimo:

1. **Tamaño de documentos**: Los documentos no deben exceder el límite configurado (por defecto 20MB)
2. **Formato de documentos**: Preferir formatos estructurados como PDF, DOCX o HTML
3. **Colecciones**: Organizar documentos en colecciones temáticas para mejor recuperación
4. **Metadatos**: Proporcionar metadatos descriptivos (título, tags, descripción)

### Ingesta por Lotes

Para ingesta masiva:

1. **Endpoint de lotes**: Utilizar `/ingest/batch/urls` para procesar múltiples URLs
2. **Monitoreo de trabajos**: Verificar el estado mediante el endpoint `/jobs/{job_id}`
3. **Reintentos**: Implementar lógica de reintentos en el cliente para documentos fallidos

## Flujo de Procesamiento

1. **Recepción**: El documento se recibe a través de un endpoint
2. **Validación**: Se verifica formato, tamaño y permisos
3. **Encolado**: Se crea un trabajo asíncrono y se encola
4. **Extracción**: Un worker extrae el texto del documento
5. **Chunking**: El texto se divide en fragmentos óptimos
6. **Embeddings**: Se solicitan embeddings al embedding-service
7. **Almacenamiento**: Los fragmentos con embeddings se almacenan en la base de datos
8. **Notificación**: Se actualiza el estado del trabajo a completado

## Resolución de Problemas

### Problemas Comunes

| Problema | Posible Causa | Solución |
|----------|---------------|----------|
| Error 413 | Documento demasiado grande | Reducir tamaño o dividir documento |
| Error 415 | Formato no soportado | Convertir a formato soportado (PDF, DOCX) |
| Error 429 | Límite de rate excedido | Implementar backoff exponencial |
| Error 500 en extracción | Documento dañado o protegido | Verificar integridad y permisos |
| Timeout en procesamiento | Documento muy complejo | Aumentar timeout o dividir documento |

### Logs y Monitoreo

El servicio emite logs detallados sobre el proceso de ingesta:

- **INFO**: Eventos normales de procesamiento
- **WARNING**: Problemas no críticos (reintentos, degradación)
- **ERROR**: Fallos en procesamiento, conexiones o almacenamiento

## Integración con Otros Servicios

- **Embedding Service**: Para generación de embeddings
- **Query Service**: Utiliza los documentos procesados para responder consultas
- **Agent Service**: Orquesta el proceso completo de RAG

## Seguridad

- **Validación de tenant**: Todos los endpoints requieren un tenant válido
- **Sanitización de contenido**: Limpieza de contenido malicioso
- **Límites por tier**: Restricciones según el plan del tenant
- **Aislamiento de datos**: Estricta separación entre tenants
