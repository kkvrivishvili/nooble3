# Métricas y Monitoreo - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Métricas y Monitoreo - Agent Management Service](#métricas-y-monitoreo---agent-management-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. KPIs del Servicio](#2-kpis-del-servicio)
  - [3. Endpoints de Monitoreo](#3-endpoints-de-monitoreo)
  - [4. Métricas Específicas](#4-métricas-específicas)
    - [4.1 Métricas de Rendimiento](#41-métricas-de-rendimiento)
    - [4.2 Métricas de Uso](#42-métricas-de-uso)
    - [4.3 Métricas de Disponibilidad](#43-métricas-de-disponibilidad)
    - [4.4 Métricas de Negocio](#44-métricas-de-negocio)
  - [5. Integración con Sistemas de Telemetría](#5-integración-con-sistemas-de-telemetría)
  - [6. Alertas y Umbrales](#6-alertas-y-umbrales)
  - [7. Registro de Cambios](#7-registro-de-cambios)

## 1. Visión General

Este documento detalla las métricas y capacidades de monitoreo del Agent Management Service. Estas métricas son fundamentales para entender el rendimiento, uso y estado general del servicio, así como para identificar problemas potenciales antes de que afecten a los usuarios.

## 2. KPIs del Servicio

Los indicadores clave de rendimiento (KPIs) para el Agent Management Service son:

| KPI | Descripción | Objetivo | 
|-----|-------------|----------|
| Disponibilidad | Porcentaje de tiempo que el servicio está operativo | 99.95% |
| Latencia P95 | Percentil 95 del tiempo de respuesta para operaciones CRUD | < 300ms |
| Tasa de Errores | Porcentaje de solicitudes que resultan en error | < 0.5% |
| Tasa de Utilización | Porcentaje de recursos utilizados (CPU, memoria) | < 70% |
| Agentes Creados | Número de nuevos agentes creados por día | Crecimiento > 5% semanal |
| Tasa de Activación | Porcentaje de agentes que pasan a estado activo | > 60% |
| Uso de Templates | Porcentaje de agentes creados desde plantillas | > 40% |
| Validaciones Exitosas | Porcentaje de configuraciones que pasan validación | > 95% |

## 3. Endpoints de Monitoreo

El servicio expone los siguientes endpoints para monitoreo:

- **Health Check**: `/health`
  - Verifica la salud general del servicio y sus dependencias
  - Formato: JSON con estado y detalles de componentes
  - Códigos de estado: 200 (OK), 503 (Degraded/Unavailable)

- **Readiness Check**: `/ready`
  - Confirma que el servicio está listo para recibir tráfico
  - Formato: JSON con estado de preparación
  - Códigos de estado: 200 (Ready), 503 (Not Ready)

- **Métricas Prometheus**: `/metrics`
  - Expone métricas en formato Prometheus
  - Incluye métricas estándar y personalizadas
  - Sin autenticación (debe estar protegido a nivel de red)

**Ejemplo de respuesta de Health Check**:

```json
{
  "status": "healthy",
  "version": "1.5.2",
  "timestamp": "2025-06-03T15:45:22Z",
  "uptime_seconds": 86400,
  "components": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis_queue": {
      "status": "healthy",
      "message_rate": 42,
      "pending_tasks": 8
    },
    "redis_pubsub": {
      "status": "healthy",
      "channels": 15,
      "subscribers": 3
    },
    "tool_registry": {
      "status": "degraded",
      "details": "Increased latency (300ms)"
    },
    "orchestrator_websocket": {
      "status": "healthy",
      "last_heartbeat_ms": 520
    }
  }
}
```

## 4. Métricas Específicas

### 4.1 Métricas de Rendimiento

| Métrica | Tipo | Descripción | Etiquetas |
|---------|------|-------------|-----------|
| `ams_request_duration_seconds` | Histogram | Duración de solicitudes HTTP | `endpoint`, `method`, `status_code` |
| `ams_database_operation_duration_seconds` | Histogram | Duración de operaciones de BD | `operation_type`, `table` |
| `ams_queue_operation_duration_seconds` | Histogram | Duración de operaciones de cola | `queue`, `operation` |
| `ams_api_request_size_bytes` | Histogram | Tamaño de solicitudes API | `endpoint` |
| `ams_api_response_size_bytes` | Histogram | Tamaño de respuestas API | `endpoint` |

### 4.2 Métricas de Uso

| Métrica | Tipo | Descripción | Etiquetas |
|---------|------|-------------|-----------|
| `ams_active_websocket_connections` | Gauge | Conexiones WebSocket activas | `tenant_id` |
| `ams_request_count_total` | Counter | Total de solicitudes API | `endpoint`, `method`, `status_code` |
| `ams_agent_count` | Gauge | Número total de agentes | `tenant_id`, `status` |
| `ams_agent_version_count` | Gauge | Número de versiones de agentes | `tenant_id` |
| `ams_database_connection_pool_usage` | Gauge | Uso del pool de conexiones | `pool_name` |
| `ams_rate_limit_reached_total` | Counter | Veces que se alcanzó el límite de tasa | `tenant_id`, `endpoint` |

### 4.3 Métricas de Disponibilidad

| Métrica | Tipo | Descripción | Etiquetas |
|---------|------|-------------|-----------|
| `ams_service_uptime_seconds` | Counter | Tiempo de actividad del servicio | - |
| `ams_dependency_up` | Gauge | Estado de dependencias (1=up, 0=down) | `dependency_name` |
| `ams_healthcheck_failures_total` | Counter | Fallos de verificación de estado | `component` |
| `ams_last_successful_healthcheck_timestamp` | Gauge | Timestamp del último healthcheck exitoso | `component` |

### 4.4 Métricas de Negocio

Estas métricas reflejan las funciones clave del servicio mencionadas en el README: CRUD de agentes, gestión de plantillas, validación de configuraciones y notificaciones.

| Métrica | Tipo | Descripción | Etiquetas |
|---------|------|-------------|----------|
| `ams_agent_creation_count_total` | Counter | Agentes creados | `tenant_id`, `template_used` |
| `ams_agent_activation_count_total` | Counter | Activaciones de agentes | `tenant_id`, `agent_type` |
| `ams_agent_update_count_total` | Counter | Actualizaciones de agentes | `tenant_id`, `update_type` |
| `ams_agent_tool_usage_count` | Counter | Asignaciones de herramientas a agentes | `tool_id`, `tenant_id` |
| `ams_agent_template_usage_count` | Counter | Uso de plantillas | `template_id`, `tenant_id` |
| `ams_agent_validation_count_total` | Counter | Validaciones de configuraciones | `tenant_id`, `tier`, `result` |
| `ams_agent_validation_time_seconds` | Histogram | Tiempo de validación de configuraciones | `tenant_id`, `tier` |
| `ams_notification_sent_total` | Counter | Notificaciones enviadas | `tenant_id`, `event_type`, `channel` |
| `ams_websocket_messages_sent_total` | Counter | Mensajes WebSocket enviados | `tenant_id`, `event_type` |

## 5. Integración con Sistemas de Telemetría

El Agent Management Service se integra con los siguientes sistemas:

- **Prometheus**: Recolección de métricas
- **Grafana**: Visualización de dashboards
- **Jaeger/Zipkin**: Trazabilidad distribuida
- **Elasticsearch/Fluentd/Kibana (EFK)**: Logging centralizado
- **PagerDuty**: Gestión de alertas y notificaciones

**Ejemplo de configuración de traza distribuida**:

```python
@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    tracer = opentracing.global_tracer()
    span_context = tracer.extract(
        format=opentracing.Format.HTTP_HEADERS,
        carrier=request.headers
    )
    
    span = tracer.start_span(
        operation_name=f"{request.method} {request.url.path}",
        child_of=span_context
    )
    
    span.set_tag("http.method", request.method)
    span.set_tag("http.url", str(request.url))
    span.set_tag("tenant_id", request.headers.get("X-Tenant-ID"))
    
    try:
        response = await call_next(request)
        span.set_tag("http.status_code", response.status_code)
        return response
    except Exception as e:
        span.set_tag("error", True)
        span.set_tag("error.message", str(e))
        raise
    finally:
        span.finish()
```

## 6. Alertas y Umbrales

| Alerta | Condición | Severidad | Acción |
|--------|-----------|-----------|--------|
| AMS_HighErrorRate | Tasa de error > 2% en 5 min | High | Notificar equipo on-call |
| AMS_APILatencyHigh | Latencia P95 > 500ms en 10 min | Medium | Notificar equipo on-call |
| AMS_ServiceDown | Health check fallido > 1 min | Critical | Notificar equipo on-call + Escalar |
| AMS_DatabaseConnectionIssue | Fallos de conexión BD > 3 en 1 min | High | Notificar equipo on-call |
| AMS_QueueBacklog | Cola con > 1000 mensajes pendientes | Medium | Notificar equipo on-call |
| AMS_HighCPUUsage | Uso de CPU > 85% por 5 min | Medium | Notificar equipo y revisar auto-scaling |
| AMS_RateLimitAbuse | Tenant alcanza límite > 5 veces en 1 hora | Low | Notificar equipo de seguridad |

## 7. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
