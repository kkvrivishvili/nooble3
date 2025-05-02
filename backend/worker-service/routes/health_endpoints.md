# Endpoints de Health y Status - Worker Service

Este documento describe los endpoints de verificación de salud y estado del Worker Service, su implementación, componentes monitoreados y ejemplos de respuestas.

## Endpoints Disponibles

### 1. `/health` - Verificación Básica de Salud

**Método HTTP:** GET  
**Descripción:** Verificación rápida de la disponibilidad del servicio (liveness check).  
**Uso:** Ideal para health checks de Kubernetes, balanceadores de carga y monitoreo básico.

### 2. `/status` - Estado Detallado del Servicio

**Método HTTP:** GET  
**Descripción:** Información completa sobre el estado del servicio, incluyendo métricas detalladas y dependencias.  
**Uso:** Para monitoreo avanzado, depuración, observabilidad y análisis de rendimiento.

## Componentes Monitoreados

El Worker Service verifica los siguientes componentes:

### Componentes Básicos (en `/health`):
- **Cache:** Verifica la conectividad con Redis
- **Database:** Verifica la conectividad con Supabase
- **Scheduler:** Verifica el estado del programador de tareas

### Componentes Detallados (en `/status`):
- **Todos los componentes básicos**
- **Tareas programadas:** Estado, errores, tiempos de ejecución
- **Recursos del sistema:** CPU, memoria, disco, red
- **Métricas del proceso:** Uso de memoria, CPU, hilos

## Detalles de Implementación

El Worker Service utiliza los siguientes mecanismos para las verificaciones:

1. **Helpers centralizados:** Funciones reutilizables de `common.helpers.health`
2. **Monitoreo del scheduler:** Verificación de estado, tareas programadas y métricas
3. **Análisis de tareas:** Tiempos de ejecución, tasas de error, estado de salud
4. **Listeners de eventos:** Captura de eventos de ejecución y errores de tareas
5. **Métricas de sistema:** Monitoreo de recursos mediante la biblioteca `psutil`

## Ejemplos de Respuestas

### Ejemplo de respuesta de `/health`:

```json
{
  "status": "available",
  "components": {
    "cache": "available",
    "database": "available",
    "scheduler": "available"
  },
  "timestamp": "2023-06-15T10:30:45.123456Z",
  "service": "worker-service"
}
```

### Ejemplo de respuesta parcial de `/status`:

```json
{
  "status": "available",
  "components": {
    "cache": "available",
    "database": "available",
    "scheduler": "available"
  },
  "metrics": {
    "service_type": "worker",
    "uptime_seconds": 86420,
    "uptime_formatted": "1d 0h 0m",
    "scheduler_status": {
      "running": true,
      "timezone": "UTC"
    },
    "jobs_analysis": {
      "total_jobs": 3,
      "active_jobs": 3,
      "paused_jobs": 0,
      "critical_jobs": 2,
      "jobs_with_errors": 0,
      "avg_execution_times": {
        "sync_accounts": 1.25,
        "cleanup_temporary_files": 0.35,
        "reconcile_database": 5.67
      },
      "error_rates": {},
      "job_health": {
        "sync_accounts": {
          "status": "healthy",
          "is_active": true,
          "is_critical": true,
          "error_count": 0,
          "success_count": 24,
          "last_execution": {
            "timestamp": "2023-06-15T10:20:45.123456Z",
            "time_ago_seconds": 600
          },
          "next_execution": "2023-06-15T10:50:45.123456Z"
        }
        // Otros trabajos omitidos por brevedad
      }
    },
    "scheduled_jobs": [
      {
        "id": "sync_accounts",
        "name": "Sincronización de cuentas",
        "next_run_time": "2023-06-15T10:50:45.123456Z",
        "trigger": "interval[0:30:00]",
        "misfire_grace_time": 300,
        "max_instances": 1,
        "executor": "default",
        "avg_execution_time": 1.25,
        "min_execution_time": 0.98,
        "max_execution_time": 1.87,
        "error_count": 0,
        "success_count": 24
      }
      // Otros trabajos omitidos por brevedad
    ],
    "system_resources": {
      "cpu": {
        "percent": 23.5,
        "count": 8
      },
      "memory": {
        "total_gb": 16.0,
        "used_gb": 8.2,
        "percent": 51.25
      },
      "disk": {
        "total_gb": 500.0,
        "used_gb": 250.0,
        "percent": 50.0
      },
      "network": {
        "bytes_sent_mb": 128.5,
        "bytes_recv_mb": 345.2,
        "packets_sent": 10240,
        "packets_recv": 25600
      },
      "process": {
        "memory_mb": 156.8,
        "cpu_percent": 2.3,
        "threads": 8,
        "open_files": 12
      }
    }
  },
  "timestamp": "2023-06-15T10:30:46.123456Z",
  "service": "worker-service"
}
```

## Casos de Uso

- **Monitoreo de Alta Disponibilidad:** Utilice `/health` para verificaciones frecuentes (cada 5-10 segundos)
- **Observabilidad y Métricas:** Utilice `/status` para recopilación de métricas (cada 1-5 minutos)
- **Alertas:** Configure alertas basadas en la disponibilidad de componentes críticos y métricas
- **Análisis de Rendimiento:** Use las métricas de tareas para identificar problemas de rendimiento

## Diseño y Beneficios

Este diseño de endpoints de health y status proporciona:

1. **Detección temprana de problemas:** Permite identificar fallos antes de que afecten al servicio
2. **Monitoreo granular:** Proporciona visibilidad detallada de cada componente
3. **Métricas procesables:** Ofrece datos para tomar decisiones informadas
4. **Observabilidad completa:** Integra con sistemas de monitoreo externo
5. **Alertas proactivas:** Permite configurar alertas antes de fallos críticos
