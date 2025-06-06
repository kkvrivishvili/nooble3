# Estándares de Métricas y Monitoreo

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Categorías de Métricas](#2-categorías-de-métricas)
3. [Nomenclatura de Métricas](#3-nomenclatura-de-métricas)
4. [Dimensiones y Etiquetas](#4-dimensiones-y-etiquetas)
5. [Métricas Estándar por Servicio](#5-métricas-estándar-por-servicio)
6. [Dashboards](#6-dashboards)
7. [Alertas](#7-alertas)
8. [Implementación](#8-implementación)

## 1. Introducción

Este documento define los estándares de métricas y monitoreo para todos los microservicios de la plataforma Nooble AI. El objetivo es garantizar una observabilidad uniforme, facilitar el diagnóstico de problemas y asegurar la detección temprana de incidentes.

### 1.1 Principios Generales

- **Consistencia**: Definiciones uniformes en todos los servicios
- **Relevancia**: Métricas enfocadas en indicadores clave de rendimiento
- **Multi-tenancy**: Dimensiones que permitan filtrar por tenant
- **Eficiencia**: Balance entre nivel de detalle y sobrecarga
- **Accionabilidad**: Métricas que permitan identificar causa raíz

## 2. Categorías de Métricas

Las métricas se clasifican en las siguientes categorías:

### 2.1 Métricas de Servicio

Reflejan el estado y comportamiento general del servicio:

- **Disponibilidad**: Tiempo activo y estado del servicio
- **Rendimiento**: Latencia, throughput, tiempos de respuesta
- **Capacidad**: Utilización de recursos, saturación
- **Errores**: Tasas de error, tipos de fallos

### 2.2 Métricas de Negocio

Reflejan indicadores específicos del dominio:

- **Operaciones**: Volumen y estado de operaciones de negocio
- **Calidad**: Precisión y relevancia de resultados
- **Uso**: Patrones de utilización de características
- **SLA**: Cumplimiento de acuerdos de nivel de servicio

### 2.3 Métricas de Recursos

Reflejan el estado de los recursos técnicos:

- **Computación**: CPU, memoria, hilos
- **Almacenamiento**: Uso de disco, operaciones I/O
- **Red**: Tráfico, conexiones, latencia
- **Dependencias**: Estado de servicios externos

### 2.4 Métricas LLM Específicas

Específicas para operaciones con modelos de lenguaje:

- **Tokens**: Uso de tokens (entrada/salida)
- **Costos**: Estimación de costos por operación LLM
- **Rendimiento**: Tokens por segundo, tiempo de generación
- **Calidad**: Métricas RAG, relevancia de respuestas

## 3. Nomenclatura de Métricas

Las métricas deben seguir esta estructura de nomenclatura:

```
{servicio}_{categoría}_{métrica}_{unidad}
```

Donde:
- `servicio`: Nombre corto del servicio (ej: `workflow`, `query`, `embedding`)
- `categoría`: Categoría funcional dentro del servicio (ej: `http`, `queue`, `database`)
- `métrica`: Nombre descriptivo de lo que se mide (ej: `requests`, `latency`, `errors`)
- `unidad`: Unidad de medida cuando es relevante (ej: `seconds`, `bytes`, `count`)

**Ejemplos**:
- `workflow_http_requests_total`
- `query_rag_latency_seconds`
- `embedding_tokens_used_count`
- `tool_execution_errors_total`

### 3.1 Unidades Estándar

| Aspecto | Unidad | Sufijo | Ejemplo |
|---------|--------|--------|---------|
| Contadores | (ninguna) | _total | `http_requests_total` |
| Tiempo | Segundos | _seconds | `request_latency_seconds` |
| Tamaño | Bytes | _bytes | `memory_used_bytes` |
| Temperatura | Celsius | _celsius | `cpu_temperature_celsius` |
| Porcentaje | Ratio 0-1 | _ratio | `cache_hit_ratio` |

## 4. Dimensiones y Etiquetas

Cada métrica debe incluir dimensiones relevantes como etiquetas para permitir filtrado y agregación:

### 4.1 Dimensiones Obligatorias

| Dimensión | Descripción | Ejemplo |
|-----------|-------------|---------|
| tenant_id | Identificador del tenant | "tenant-123" |
| service | Nombre del servicio | "workflow-engine" |
| environment | Entorno de ejecución | "production" |
| instance | Instancia específica | "workflow-engine-pod-7" |

### 4.2 Dimensiones Opcionales por Contexto

| Contexto | Dimensiones Recomendadas |
|----------|--------------------------|
| HTTP | method, path, status_code |
| Colas | queue_name, message_type |
| Base de datos | operation, table, query_type |
| LLM | model, operation_type |
| Workflow | workflow_type, step_type |

### 4.3 Cardinalidad

La cardinalidad de las etiquetas debe mantenerse bajo control:

- Evitar dimensiones de alta cardinalidad (IDs únicos ilimitados)
- Usar bucketing para valores continuos (ej: rangos de latencia)
- Limitar valores de enumeración a conjuntos conocidos

## 5. Métricas Estándar por Servicio

Cada servicio debe implementar un conjunto mínimo de métricas:

### 5.1 Métricas Comunes (Todos los Servicios)

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| {servicio}_up | Gauge | Estado del servicio (1=activo, 0=caído) |
| {servicio}_http_requests_total | Counter | Total de solicitudes HTTP recibidas |
| {servicio}_http_request_duration_seconds | Histogram | Distribución de tiempos de respuesta HTTP |
| {servicio}_http_request_size_bytes | Histogram | Tamaño de solicitudes HTTP |
| {servicio}_http_response_size_bytes | Histogram | Tamaño de respuestas HTTP |
| {servicio}_http_errors_total | Counter | Total de errores HTTP |
| {servicio}_task_duration_seconds | Histogram | Tiempo de procesamiento de tareas asíncronas |
| {servicio}_task_errors_total | Counter | Errores en tareas asíncronas |
| {servicio}_memory_used_bytes | Gauge | Uso de memoria |
| {servicio}_cpu_usage_ratio | Gauge | Uso de CPU (0-1) |

### 5.2 Workflow Engine Service

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| workflow_executions_total | Counter | Total de ejecuciones de workflows |
| workflow_execution_duration_seconds | Histogram | Duración total de workflows |
| workflow_step_duration_seconds | Histogram | Duración de pasos individuales |
| workflow_queue_depth | Gauge | Profundidad de cola por tipo de tarea |
| workflow_active_executions | Gauge | Ejecuciones activas simultáneas |

### 5.3 Query Service

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| query_requests_total | Counter | Total de consultas procesadas |
| query_tokens_input_total | Counter | Tokens de entrada consumidos |
| query_tokens_output_total | Counter | Tokens de salida generados |
| query_latency_seconds | Histogram | Latencia de consultas completas |
| query_rag_relevance_score | Histogram | Puntuación de relevancia RAG (0-1) |
| query_vector_search_latency_seconds | Histogram | Tiempo de búsqueda vectorial |
| query_prompt_tokens | Histogram | Distribución de tamaños de prompts |

### 5.4 Embedding Service

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| embedding_requests_total | Counter | Total de solicitudes de embeddings |
| embedding_tokens_total | Counter | Tokens procesados para embeddings |
| embedding_generation_duration_seconds | Histogram | Tiempo de generación de embeddings |
| embedding_batch_size | Histogram | Tamaño de lotes de embeddings |
| embedding_errors_by_provider | Counter | Errores por proveedor |

### 5.5 Tool Registry Service

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| tool_invocations_total | Counter | Total de invocaciones de herramientas |
| tool_execution_duration_seconds | Histogram | Duración de ejecución de herramientas |
| tool_registration_total | Counter | Total de registros de herramientas |
| tool_execution_success_ratio | Gauge | Ratio de éxito de ejecución (0-1) |
| tool_discovery_latency_seconds | Histogram | Tiempo de descubrimiento de herramientas |

### 5.6 Agent Execution Service

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| agent_executions_total | Counter | Total de ejecuciones de agentes |
| agent_execution_duration_seconds | Histogram | Duración de ejecuciones de agentes |
| agent_tokens_used_total | Counter | Total de tokens usados en ejecuciones |
| agent_tool_calls_total | Counter | Llamadas a herramientas por agentes |
| agent_streaming_events_total | Counter | Eventos de streaming emitidos |

## 6. Dashboards

Cada servicio debe contar con dashboards estandarizados:

### 6.1 Dashboard de Estado General

Dashboard unificado que muestra:
- Estado de todos los servicios
- Principales métricas de rendimiento
- Tasas de error agregadas
- SLOs/SLAs críticos

### 6.2 Dashboards por Servicio

Cada servicio debe implementar dashboards específicos:

1. **Dashboard Operacional**:
   - Estado y disponibilidad
   - Tráfico y throughput
   - Latencia (p50, p95, p99)
   - Tasas de error
   - Profundidad de colas

2. **Dashboard de Recursos**:
   - Uso de CPU y memoria
   - Uso de disco y red
   - Conexiones de base de datos
   - Saturación de recursos

3. **Dashboard de Negocio**:
   - Métricas específicas de dominio
   - Volumen de operaciones clave
   - Indicadores de calidad
   - Tendencias de uso

### 6.3 Dashboard de Multi-tenancy

Dashboard específico para análisis por tenant:
- Consumo de recursos por tenant
- Volumen de operaciones por tenant
- SLAs por tenant
- Incidentes por tenant

## 7. Alertas

### 7.1 Niveles de Severidad

| Nivel | Descripción | Tiempo de Respuesta |
|-------|-------------|---------------------|
| P0 | Crítico - Servicio caído | 15 minutos |
| P1 | Alto - Funcionalidad crítica afectada | 30 minutos |
| P2 | Medio - Degradación significativa | 2 horas |
| P3 | Bajo - Problemas menores | 8 horas |

### 7.2 Alertas Estándar

Cada servicio debe implementar estas alertas mínimas:

| Alerta | Condición | Severidad | Acción |
|--------|-----------|-----------|--------|
| ServiceDown | service_up == 0 | P0 | Página a ingeniería |
| HighErrorRate | error_rate > 5% por 5 minutos | P1 | Página a responsable |
| LatencySpike | p95 latencia > SLO durante 10 minutos | P1 | Notifica a responsable |
| QueueBacklog | queue_depth > umbral durante 15 minutos | P2 | Notifica a responsable |
| ResourceSaturation | cpu/memoria > 85% durante 10 minutos | P2 | Notifica a responsable |

### 7.3 Plantilla de Alertas

Las alertas deben incluir:
- Título claro y conciso
- Descripción del problema
- Métricas desencadenantes y valores actuales
- Posible impacto en usuarios/sistema
- Enlaces a dashboards relevantes
- Sugerencias de diagnóstico inicial
- Información de contacto del responsable

## 8. Implementación

### 8.1 Tecnologías

La implementación debe utilizar:
- **Recolección**: Prometheus con exporters específicos
- **Almacenamiento**: Prometheus (corto plazo) + VictoriaMetrics (largo plazo)
- **Visualización**: Grafana con dashboards estandarizados
- **Alertas**: Alertmanager con integración a PagerDuty y Slack

### 8.2 Código Estándar

Cada servicio debe implementar un módulo de métricas estandarizado:

```python
from prometheus_client import Counter, Histogram, Gauge, Summary, start_http_server

class NoobleMetrics:
    """Clase estándar para gestión de métricas en servicios Nooble"""
    
    def __init__(self, service_name, tenant_id=None):
        """Inicializa métricas estándar para un servicio"""
        self.service_name = service_name
        self.default_labels = {"service": service_name}
        if tenant_id:
            self.default_labels["tenant_id"] = tenant_id
        
        # Métricas HTTP
        self.http_requests = Counter(
            f"{service_name}_http_requests_total",
            "Total de solicitudes HTTP",
            ["method", "path", "status"]
        )
        
        self.http_latency = Histogram(
            f"{service_name}_http_request_duration_seconds",
            "Latencia de solicitudes HTTP",
            ["method", "path"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
        )
        
        # Métricas de tareas
        self.tasks_total = Counter(
            f"{service_name}_tasks_total",
            "Total de tareas procesadas",
            ["task_type", "status"]
        )
        
        self.task_duration = Histogram(
            f"{service_name}_task_duration_seconds",
            "Duración de procesamiento de tareas",
            ["task_type"],
            buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600)
        )
        
        # Métricas de recursos
        self.memory_usage = Gauge(
            f"{service_name}_memory_used_bytes",
            "Uso de memoria en bytes"
        )
        
        self.cpu_usage = Gauge(
            f"{service_name}_cpu_usage_ratio",
            "Uso de CPU (0-1)"
        )
    
    def track_request(self, method, path, status_code, duration):
        """Registra una solicitud HTTP completada"""
        self.http_requests.labels(
            method=method,
            path=path,
            status=str(status_code)
        ).inc()
        
        self.http_latency.labels(
            method=method,
            path=path
        ).observe(duration)
    
    def start_task_timer(self, task_type):
        """Inicia temporizador para una tarea"""
        return self.task_duration.labels(task_type=task_type).time()
    
    def track_task_completion(self, task_type, status):
        """Registra finalización de tarea"""
        self.tasks_total.labels(
            task_type=task_type,
            status=status
        ).inc()
    
    def update_resource_usage(self, memory_bytes, cpu_ratio):
        """Actualiza métricas de recursos"""
        self.memory_usage.set(memory_bytes)
        self.cpu_usage.set(cpu_ratio)
```

### 8.3 Exportación de Métricas

Cada servicio debe exponer un endpoint `/metrics` en el puerto 9090 para recolección por Prometheus:

```python
def setup_metrics_server(port=9090):
    """Configura servidor de métricas Prometheus"""
    start_http_server(port)
    logger.info(f"Metrics server started on port {port}")
```

### 8.4 Configuración de Recolección

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'nooble-services'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: nooble-.*
        action: keep
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: service
      - source_labels: [__meta_kubernetes_pod_label_tenant_id]
        target_label: tenant_id
```
