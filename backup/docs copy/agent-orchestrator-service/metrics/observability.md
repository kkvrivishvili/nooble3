# Métricas y Observabilidad - Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Métricas y Observabilidad - Agent Orchestrator Service](#métricas-y-observabilidad---agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Métricas Clave](#2-métricas-clave)
  - [3. Distributed Tracing](#3-distributed-tracing)
  - [4. Logging](#4-logging)
  - [5. Alerting](#5-alerting)
  - [6. Dashboards](#6-dashboards)
  - [7. Implementación](#7-implementación)

## 1. Introducción

Este documento define las estrategias de observabilidad y monitoreo para el Agent Orchestrator Service. Como componente central de la plataforma Nooble, es esencial tener una visibilidad completa de su comportamiento para garantizar la fiabilidad, rendimiento y disponibilidad del sistema.

## 2. Métricas Clave

### 2.1 Métricas de Sesión

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_orchestrator_sessions_active` | Gauge | tenant_id | Número de sesiones activas |
| `nooble_orchestrator_sessions_created_total` | Counter | tenant_id, agent_id | Total de sesiones creadas |
| `nooble_orchestrator_sessions_completed_total` | Counter | tenant_id, agent_id, status | Total de sesiones completadas |
| `nooble_orchestrator_session_duration_seconds` | Histogram | tenant_id, agent_id | Duración de sesiones |

### 2.2 Métricas de Mensajes

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_orchestrator_messages_processed_total` | Counter | tenant_id, role | Total de mensajes procesados |
| `nooble_orchestrator_message_processing_seconds` | Histogram | tenant_id, role | Tiempo de procesamiento de mensajes |
| `nooble_orchestrator_tokens_total` | Counter | tenant_id, agent_id, type | Tokens consumidos (entrada/salida) |

### 2.3 Métricas de Orquestación

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_orchestrator_service_call_total` | Counter | tenant_id, service, operation | Llamadas a servicios |
| `nooble_orchestrator_service_call_seconds` | Histogram | tenant_id, service, operation | Duración de llamadas a servicios |
| `nooble_orchestrator_service_call_failures_total` | Counter | tenant_id, service, operation, error_code | Fallos en llamadas a servicios |

### 2.4 Métricas de Colas

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_orchestrator_queue_depth` | Gauge | tenant_id, queue | Profundidad de las colas |
| `nooble_orchestrator_queue_lag_seconds` | Gauge | tenant_id, queue | Retraso en procesamiento de colas |
| `nooble_orchestrator_task_processing_seconds` | Histogram | tenant_id, task_type | Tiempo de procesamiento de tareas |

### 2.5 Métricas de Sistema

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_orchestrator_http_requests_total` | Counter | method, endpoint, status | Total de peticiones HTTP |
| `nooble_orchestrator_http_request_duration_seconds` | Histogram | method, endpoint | Duración de peticiones HTTP |
| `nooble_orchestrator_websocket_connections_active` | Gauge | tenant_id | Conexiones WebSocket activas |

## 3. Distributed Tracing

### 3.1 Configuración

El Agent Orchestrator Service implementa trazado distribuido utilizando OpenTelemetry para rastrear el flujo de solicitudes a través de los diferentes servicios.

```python
# tracing/setup.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_tracing():
    """Configura el trazado distribuido"""
    resource = Resource(attributes={SERVICE_NAME: "agent-orchestrator"})
    
    trace.set_tracer_provider(TracerProvider(resource=resource))
    
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTLP_ENDPOINT", "otel-collector:4317"),
        insecure=True
    )
    
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )
```

### 3.2 Propagación de Contexto

```python
# middleware/context.py
from fastapi import Request
from opentelemetry import trace
from opentelemetry.propagate import extract

async def trace_middleware(request: Request, call_next):
    """Middleware para extraer y propagar contexto de trazado"""
    token = request.headers.get("traceparent")
    if token:
        ctx = extract(request.headers)
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=ctx,
            kind=trace.SpanKind.SERVER
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.tenant_id", request.headers.get("X-Tenant-ID", "unknown"))
            
            response = await call_next(request)
            
            span.set_attribute("http.status_code", response.status_code)
            return response
    else:
        return await call_next(request)
```

### 3.3 Convención de Trazado

Cada flujo de orquestación debe estar correctamente trazado con:

- Span principal para la orquestación completa
- Sub-spans para cada llamada a servicio
- Propagación de span_id y trace_id a todos los servicios
- Atributos estándar de tenant_id, session_id, task_id

## 4. Logging

### 4.1 Formato de Logs

Todos los logs siguen un formato JSON estructurado:

```json
{
  "timestamp": "2025-06-04T00:15:23.123Z",
  "level": "INFO",
  "service": "agent-orchestrator",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "tenant_id": "acme-corp",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "cc7a93c1-074f-48b9-8ea7-56001d0bb453",
  "message": "Sesión inicializada correctamente",
  "context": {
    "agent_id": "customer-support-agent",
    "user_id": "user-123"
  }
}
```

### 4.2 Niveles de Log

| Nivel | Uso |
|-------|-----|
| DEBUG | Información detallada para diagnóstico de desarrollo |
| INFO | Eventos operacionales normales |
| WARNING | Situaciones no ideales pero recuperables |
| ERROR | Errores que afectan a una operación específica |
| CRITICAL | Errores que afectan al funcionamiento global del servicio |

### 4.3 Implementación

```python
# logging/setup.py
import json
import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    """Configura logging estructurado"""
    logger = logging.getLogger("agent-orchestrator")
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '%(timestamp)s %(level)s %(service)s %(trace_id)s %(span_id)s '
        '%(tenant_id)s %(session_id)s %(request_id)s %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger
```

## 5. Alerting

### 5.1 Condiciones de Alerta

| Alerta | Condición | Severidad | Acción |
|--------|-----------|-----------|--------|
| HighErrorRate | Error rate > 5% en 5min | Critical | Investigar logs/traces, posible rollback |
| ServiceConnectionFailure | >3 fallos consecutivos a un servicio | Warning | Verificar disponibilidad del servicio |
| HighLatency | P95 latencia > 2s por 10min | Warning | Revisar carga y escalado |
| QueueBacklog | Profundidad cola > 100 por 5min | Warning | Aumentar workers, verificar bottlenecks |
| HighSessionCount | Sesiones activas > 80% de capacidad | Warning | Preparar escalado horizontal |

### 5.2 Configuración

El servicio utiliza Prometheus AlertManager integrado con PagerDuty y Slack.

## 6. Dashboards

### 6.1 Dashboard Principal

**Métricas de Alto Nivel**:
- Número total de sesiones activas (por tenant)
- Tasa de mensajes procesados (por minuto)
- Latencia de respuestas (p50, p95, p99)
- Tasa de errores
- Uso de CPU/RAM

**Panel de Estado de Servicios**:
- Status del Agent Orchestrator y servicios dependientes
- Latencia de comunicación entre servicios
- Error rate por servicio

### 6.2 Dashboard de Rendimiento

**Comunicación con Servicios**:
- Número de llamadas por servicio/operación
- Duración de llamadas
- Error rate por servicio/operación
- Circuit breaker status

**Sistema de Colas**:
- Profundidad de colas por tenant
- Throughput de procesamiento
- Backlog y lag time

## 7. Implementación

### 7.1 Instrumentación de Código

Ejemplo de instrumentación de un endpoint:

```python
# routes/sessions.py
from opentelemetry import trace
from prometheus_client import Counter, Histogram

# Definición de métricas
SESSION_CREATED = Counter(
    "nooble_orchestrator_sessions_created_total",
    "Total de sesiones creadas",
    ["tenant_id", "agent_id"]
)

SESSION_DURATION = Histogram(
    "nooble_orchestrator_session_init_seconds",
    "Tiempo de inicialización de sesión",
    ["tenant_id", "agent_id"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

@router.post("/api/v1/sessions")
async def create_session(
    session_data: SessionCreate,
    tenant_id: str = Header(..., alias="X-Tenant-ID")
):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("create_session"):
        with SESSION_DURATION.labels(
            tenant_id=tenant_id,
            agent_id=session_data.agent_id
        ).time():
            # Lógica de creación de sesión...
            session = await session_service.create(tenant_id, session_data)
            
            # Incrementar contador
            SESSION_CREATED.labels(
                tenant_id=tenant_id,
                agent_id=session_data.agent_id
            ).inc()
            
            return session
```

### 7.2 Integración con Servicios de Observabilidad

El Agent Orchestrator Service está preconfigurado para integración con:

- **Prometheus**: Para recolección de métricas
- **Jaeger/Tempo**: Para distributed tracing
- **Loki**: Para centralización de logs
- **Grafana**: Para dashboards y visualización
- **AlertManager**: Para alertas

### 7.3 Health Checks

```python
# routes/health.py
@router.get("/health/liveness")
async def liveness_check():
    """Verifica que el servicio está en ejecución"""
    return {"status": "ok"}

@router.get("/health/readiness")
async def readiness_check():
    """Verifica que el servicio está listo para recibir tráfico"""
    # Verificar conectividad con dependencias críticas
    redis_ok = await check_redis_connection()
    db_ok = await check_database_connection()
    
    if redis_ok and db_ok:
        return {
            "status": "ok",
            "checks": {
                "redis": "ok",
                "database": "ok"
            }
        }
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "checks": {
                    "redis": "ok" if redis_ok else "error",
                    "database": "ok" if db_ok else "error"
                }
            }
        )
```
