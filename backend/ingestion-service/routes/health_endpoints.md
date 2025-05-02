# Endpoints de salud para Ingestion Service

Este documento describe los endpoints de verificación de salud y estado implementados en el servicio de ingestión.

## Endpoints disponibles

### 1. `/health` - Verificación básica de disponibilidad

**Descripción**: Proporciona una verificación rápida del estado operativo del servicio (liveness check).

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "ingestion-service",
  "version": "x.y.z",
  "status": "available",
  "components": {
    "cache": "available",
    "database": "available",
    "embedding_service": "available",
    "jobs_queue": "available",
    "document_processors": "available",
    "storage": "available"
  }
}
```

**Estados posibles**:
- `available`: El servicio está completamente operativo.
- `degraded`: El servicio está funcionando, pero uno o más componentes no están al 100%.
- `unavailable`: El servicio no está operativo.

**Recomendación de uso**: Ideal para health checks de Kubernetes, balanceadores de carga y sistemas de monitoreo automatizados que requieren respuestas rápidas.

---

### 2. `/status` - Estado detallado con métricas

**Descripción**: Proporciona información completa sobre el estado del servicio, sus componentes y métricas operacionales.

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "ingestion-service",
  "version": "x.y.z",
  "status": "available",
  "uptime_seconds": 12345,
  "start_time": "2023-06-01T12:00:00Z",
  "components": {
    "cache": "available",
    "database": "available",
    "embedding_service": "available",
    "jobs_queue": "available",
    "document_processors": "available",
    "storage": "available"
  },
  "metrics": {
    "supported_file_types": ["pdf", "docx", "txt", "html", "markdown", "csv", "json"],
    "max_file_size_mb": 50,
    "chunking_strategies": ["fixed", "paragraph", "semantic", "recursive"],
    "supports_batch_processing": true,
    "worker_concurrency": 5,
    "queue": {
      "current_backlog": 12,
      "processing_jobs": 3,
      "failed_jobs": 2,
      "avg_backlog": 8.5,
      "queue_health": "healthy",
      "backlog_trend": "decreasing"
    },
    "processing": {
      "processed_jobs": 150,
      "error_count": 5,
      "error_rate": 3.33,
      "avg_processing_time_ms": 2500,
      "p95_processing_time_ms": 4800
    },
    "storage": {
      "temp_directory": "/tmp",
      "total_mb": 10240,
      "free_mb": 5120,
      "used_mb": 5120,
      "percent_used": 50,
      "status": "healthy"
    },
    "ingestion_statistics": {
      "documents_ingested_24h": 50,
      "chunks_generated_24h": 500,
      "avg_chunks_per_document": 10,
      "ingestion_success_rate": 95,
      "most_common_file_types": {
        "pdf": 60,
        "docx": 30,
        "txt": 10
      }
    },
    "estimated_throughput": {
      "docs_per_minute": 12.5,
      "max_concurrent_uploads": 10
    }
  }
}
```

**Componentes verificados**:
- `cache`: Disponibilidad de la caché Redis
- `database`: Conectividad con Supabase
- `embedding_service`: Estado del servicio de embeddings
- `jobs_queue`: Estado de la cola de trabajos
- `document_processors`: Disponibilidad de procesadores de documentos
- `storage`: Espacio de almacenamiento temporal

**Métricas disponibles**:
- Tipos de archivos soportados
- Estadísticas de cola (backlog, trabajos en proceso, fallidos)
- Métricas de procesamiento (tiempos, tasas de error)
- Estadísticas de ingestión (documentos procesados, chunks generados)
- Métricas de almacenamiento (espacio usado/disponible)
- Capacidad estimada de procesamiento

**Recomendación de uso**: Útil para dashboards operacionales, diagnóstico de problemas y observabilidad detallada del sistema.

## Componentes internos

El endpoint utiliza los siguientes componentes internos para realizar verificaciones:

- `check_jobs_queue()`: Verifica el estado de la cola de trabajos en Redis
- `check_embedding_service_status()`: Verifica la disponibilidad del servicio de embeddings
- `check_document_processors()`: Verifica la disponibilidad de los procesadores de documentos
- `check_storage_space()`: Verifica el espacio disponible en almacenamiento temporal

## Métricas recopiladas

El servicio recopila las siguientes métricas para mostrar en el endpoint `/status`:

- `job_processing_times`: Tiempos de procesamiento de trabajos
- `queue_backlog_history`: Historial de backlog en la cola
- `job_error_count`: Contador de errores en trabajos

## Integración

Estos endpoints están diseñados para integrarse con:
- Sistemas de monitoreo como Prometheus/Grafana
- Health checks de Kubernetes
- Dashboards operacionales
- Herramientas de alerta

---

*Última actualización: 2 de mayo de 2025*
