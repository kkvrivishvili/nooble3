# Query Service Health Endpoints

Esta documentación describe los endpoints de health check implementados en el servicio de consultas (query-service).

## Endpoint: `/health`

**Propósito**: Verificación rápida de disponibilidad del servicio (liveness probe)

**Método**: GET

**Formato de Respuesta**:
```json
{
  "service": "query-service",
  "version": "1.0.0",
  "status": "available|degraded|unavailable",
  "timestamp": "2025-05-02T12:48:14-03:00",
  "components": {
    "cache": "available|degraded|unavailable",
    "database": "available|degraded|unavailable",
    "embedding_service": "available|unavailable",
    "vector_stores": "available|degraded|unavailable"
  }
}
```

**Descripción**: Este endpoint proporciona una verificación ligera que confirma los componentes esenciales del servicio. Está optimizado para Kubernetes liveness probes y responde rápidamente con un uso mínimo de recursos.

**Posibles estados**:
- `available`: Todos los componentes funcionan correctamente
- `degraded`: Al menos un componente presenta problemas pero el servicio sigue operando
- `unavailable`: El servicio no puede operar correctamente

## Endpoint: `/status`

**Propósito**: Estado detallado del servicio con métricas e información de dependencias

**Método**: GET

**Formato de Respuesta**:
```json
{
  "service": "query-service",
  "version": "1.0.0",
  "status": "available|degraded|unavailable",
  "uptime_seconds": 3600,
  "components": {
    "cache": "available|degraded|unavailable",
    "database": "available|degraded|unavailable",
    "embedding_service": "available|degraded|unavailable",
    "vector_stores": "available|degraded|unavailable",
    "indices": "available|degraded|unavailable"
  },
  "metrics": {
    "vector_databases": ["supabase", "redis"],
    "supported_query_types": ["similarity", "hybrid", "mmr"],
    "max_similarity_top_k": 10,
    "performance": {
      "latencies_ms": {
        "avg": 120,
        "p50": 100,
        "p90": 200,
        "p99": 350,
        "min": 50,
        "max": 500,
        "samples": 100
      }
    },
    "vector_store_metrics": {
      "total_collections": 15,
      "total_documents": 1250,
      "total_chunks": 8750,
      "unique_tenants": 5,
      "vector_dimensions": 1536
    },
    "embedding_dimensions": 1536,
    "default_response_mode": "compact"
  },
  "timestamp": "2025-05-02T12:48:14-03:00"
}
```

**Descripción**: Este endpoint proporciona información completa sobre el estado del servicio para observabilidad y monitoreo. Incluye métricas de rendimiento, estado de dependencias e información detallada sobre los almacenes vectoriales. Este endpoint consume más recursos y está destinado a sistemas de monitoreo y dashboards.

## Implementación

La implementación de estos endpoints sigue el patrón centralizado de configuración del servicio. Los endpoints utilizan:

- Configuración centralizada en `config/settings.py` y `config/constants.py`
- Verificación centralizada de componentes individuales (cache, base de datos, etc.)
- Manejo consistente de errores y tiempos de espera

## Monitoreo Recomendado

Se recomienda:

1. Monitoreo del endpoint `/health` para verificaciones de disponibilidad (cada 30 segundos)
2. Monitoreo del endpoint `/status` para métricas detalladas (cada 5 minutos)
3. Configurar alertas para:
   - Cambios en el estado general (de `available` a `degraded` o `unavailable`)
   - Latencias superiores a los umbrales definidos en `QUALITY_THRESHOLDS`
   - Problemas con componentes específicos

## Última Actualización

Fecha: 2025-05-02
