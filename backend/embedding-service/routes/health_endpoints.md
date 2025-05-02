# Endpoints de salud para Embedding Service

Este documento describe los endpoints de verificación de salud y estado implementados en el servicio de embeddings.

## Endpoints disponibles

### 1. `/health` - Verificación básica de disponibilidad

**Descripción**: Proporciona una verificación rápida del estado operativo del servicio y sus componentes críticos (liveness check).

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "embedding-service",
  "version": "x.y.z",
  "status": "available",
  "components": {
    "cache": "available",
    "database": "available",
    "embedding_provider": "available",
    "cache_efficiency": "available"
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

**Descripción**: Proporciona información completa sobre el estado del servicio, sus componentes, métricas operacionales y configuración del proveedor de embeddings.

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "embedding-service",
  "version": "x.y.z",
  "status": "available",
  "uptime_seconds": 12345,
  "start_time": "2023-06-01T12:00:00Z",
  "components": {
    "cache": "available",
    "database": "available",
    "embedding_provider": "available",
    "cache_efficiency": "available",
    "api_rate_limits": "available"
  },
  "metrics": {
    "embedding_model": "text-embedding-ada-002",
    "provider": "openai",
    "embedding_dimensions": 1536,
    "model_statistics": {
      "requests_last_24h": 12500,
      "avg_token_count": 250,
      "most_used_models": {
        "text-embedding-ada-002": 98.5,
        "text-embedding-3-small": 1.5
      },
      "total_embeddings_generated": 1250000
    },
    "performance": {
      "avg_latency_ms": 185.45,
      "p95_latency_ms": 350.75,
      "max_latency_ms": 980.25,
      "min_latency_ms": 95.12,
      "success_rate": 99.8,
      "error_rate": 0.2,
      "throughput_per_min": 400
    },
    "cache": {
      "hit_ratio": 0.75,
      "miss_ratio": 0.25,
      "hit_count": 9375,
      "miss_count": 3125,
      "size_bytes": 25000000,
      "size_count": 15000,
      "avg_entry_size_bytes": 1667,
      "entries_per_model": {
        "text-embedding-ada-002": 14500,
        "text-embedding-3-small": 500
      }
    },
    "api_limits": {
      "rate_limit_per_min": 3000,
      "current_usage_per_min": 400,
      "limit_percentage": 13.33,
      "quota_reset": "2023-06-02T00:00:00Z",
      "status": "healthy"
    },
    "max_input_length": 8192,
    "allows_batch_processing": true,
    "system_resources": {
      "memory_usage": "normal",
      "cpu_usage_percent": 35,
      "disk_space_percent": 45
    }
  }
}
```

**Componentes verificados**:
- `cache`: Disponibilidad de la caché Redis
- `database`: Conectividad con Supabase
- `embedding_provider`: Estado del proveedor de embeddings (OpenAI/Ollama)
- `cache_efficiency`: Eficiencia de la caché de embeddings
- `api_rate_limits`: Estado de los límites de API (OpenAI)

**Métricas disponibles**:
- Información del modelo de embedding (proveedor, dimensiones)
- Estadísticas de uso de modelos
- Métricas de rendimiento (latencia, tasa de éxito)
- Métricas de caché (hit ratio, tamaño)
- Límites de API (cuotas, uso actual)
- Recursos del sistema (uso de memoria)

**Recomendación de uso**: Útil para dashboards operacionales, diagnóstico de problemas y observabilidad detallada del sistema.

## Componentes internos

El endpoint utiliza los siguientes componentes internos para realizar verificaciones:

- `check_embedding_provider()`: Verifica el proveedor de embeddings (OpenAI u Ollama)
- `check_cache_efficiency()`: Verifica la eficiencia de la caché de embeddings
- `check_api_rate_limits()`: Verifica el estado de los límites de API
- `check_ollama_service()`: Verifica que el servicio Ollama esté disponible (si se usa Ollama)
- `check_ollama_model()`: Verifica que el modelo específico esté disponible en Ollama
- `check_memory_usage()`: Verifica el uso de memoria del sistema (para modelos locales)
- `verify_embedding_quality()`: Evalúa la calidad del embedding generado

## Métricas recopiladas

El servicio recopila las siguientes métricas para mostrar en el endpoint `/status`:

- `embedding_latencies`: Latencias de generación de embeddings
- `embedding_cache_hits`: Contador de hits en caché
- `embedding_cache_misses`: Contador de misses en caché

## Verificaciones de calidad

El servicio incluye verificaciones avanzadas para asegurar la calidad de los embeddings:

1. **Validación de dimensiones**: Asegura que el embedding tenga la dimensionalidad esperada
2. **Detección de embeddings degenerados**: Verifica que no tenga todos valores iguales
3. **Control de valores extremos**: Monitoriza embeddings con valores fuera de rango normal
4. **Verificación de normalización**: Comprueba que la norma del vector sea cercana a 1

## Integración

Estos endpoints están diseñados para integrarse con:
- Sistemas de monitoreo como Prometheus/Grafana
- Health checks de Kubernetes
- Dashboards operacionales
- Herramientas de alerta

---

*Última actualización: 2 de mayo de 2025*
