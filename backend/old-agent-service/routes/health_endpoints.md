# Endpoints de salud para Agent Service

Este documento describe los endpoints de verificación de salud y estado implementados en el servicio de agentes.

## Endpoints disponibles

### 1. `/health` - Verificación básica de disponibilidad

**Descripción**: Proporciona una verificación rápida del estado operativo del servicio y sus componentes críticos (liveness check).

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "agent-service",
  "version": "x.y.z",
  "status": "available",
  "components": {
    "cache": "available",
    "database": "available",
    "query_service": "available",
    "embedding_service": "available",
    "llm_service": "available",
    "tools": "available"
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

**Descripción**: Proporciona información completa sobre el estado del servicio, sus componentes, métricas operacionales y configuración de LLM y herramientas.

**Método HTTP**: GET

**Respuesta**:
```json
{
  "service": "agent-service",
  "version": "x.y.z",
  "status": "available",
  "uptime_seconds": 12345,
  "start_time": "2023-06-01T12:00:00Z",
  "components": {
    "cache": "available", 
    "database": "available",
    "query_service": "available",
    "embedding_service": "available",
    "llm_service": "available",
    "tools": "available"
  },
  "metrics": {
    "llm": {
      "provider": "openai",
      "default_model": "gpt-4",
      "available_models": ["gpt-4", "gpt-3.5-turbo"],
      "metrics": {
        "avg_latency_ms": 850.45,
        "p95_latency_ms": 1500.25,
        "error_count": 12,
        "error_rate": 0.8,
        "total_calls": 1500,
        "samples_count": 850,
        "status": "healthy"
      }
    },
    "tools": {
      "enabled": ["search", "calculator", "rag", "code_interpreter"],
      "usage_stats": {
        "most_used": "rag",
        "total_uses": 415,
        "tools": {
          "search": {
            "count": 120,
            "percentage": 28.92
          },
          "rag": {
            "count": 250,
            "percentage": 60.24
          },
          "calculator": {
            "count": 30,
            "percentage": 7.23
          },
          "code_interpreter": {
            "count": 15,
            "percentage": 3.61
          }
        }
      }
    },
    "limits": {
      "max_agents_per_tenant": 10,
      "max_tokens_per_request": 4096,
      "max_parallel_requests": 10
    },
    "dependencies": {
      "calls": {
        "query_service": {
          "calls": 985,
          "last_status": "available"
        },
        "embedding_service": {
          "calls": 1240,
          "last_status": "available"
        },
        "llm_service": {
          "calls": 1500,
          "last_status": "available"
        }
      },
      "total_external_calls": 3725
    }
  }
}
```

**Componentes verificados**:
- `cache`: Disponibilidad de la caché Redis
- `database`: Conectividad con Supabase
- `query_service`: Estado del servicio de consultas
- `embedding_service`: Estado del servicio de embeddings
- `llm_service`: Estado del modelo de lenguaje
- `tools`: Disponibilidad de herramientas configuradas

**Métricas disponibles**:
- Configuración y métricas de LLM (proveedor, modelos, latencia)
- Estadísticas de uso de herramientas
- Límites y cuotas del servicio
- Métricas de dependencias (llamadas a servicios externos)

**Recomendación de uso**: Útil para dashboards operacionales, diagnóstico de problemas y observabilidad detallada del sistema.

## Componentes internos

El endpoint utiliza los siguientes componentes internos para realizar verificaciones:

- `check_query_service()`: Verifica el estado del servicio de consultas
- `check_embedding_service()`: Verifica el estado del servicio de embeddings
- `check_llm_service()`: Verifica el estado del proveedor de LLM
- `check_tools_availability()`: Verifica la disponibilidad de las herramientas configuradas

## Métricas recopiladas

El servicio recopila las siguientes métricas para mostrar en el endpoint `/status`:

- `llm_latency_ms`: Latencia del LLM en milisegundos
- `llm_error_count`: Contador de errores del LLM
- `service_call_counts`: Contadores de llamadas a servicios
- `tool_usage_counts`: Contador de uso de herramientas

## Integración

Estos endpoints están diseñados para integrarse con:
- Sistemas de monitoreo como Prometheus/Grafana
- Health checks de Kubernetes
- Dashboards operacionales
- Herramientas de alerta

---

*Última actualización: 2 de mayo de 2025*
