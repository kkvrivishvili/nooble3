# Ingestion Service

## Descripción

Ingestion Service es un microservicio especializado responsable de todo el proceso de ingesta de documentos para el sistema RAG (Retrieval Augmented Generation). El servicio maneja la recepción, procesamiento, extracción de texto, chunking y orquestación del almacenamiento de documentos y sus embeddings correspondientes.

## Características

- Soporte para múltiples formatos de documentos (PDF, Word, Excel, texto, HTML, imágenes, etc.)
- Procesamiento asíncrono mediante sistema de colas
- Chunking inteligente optimizado para RAG
- Extracción de texto con reconocimiento de estructura
- Gestión de colecciones de documentos
- Ingesta desde múltiples fuentes (archivos, URLs, texto plano)
- Soporte para procesamiento por lotes
- Tracking centralizado de tokens y uso de recursos

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
