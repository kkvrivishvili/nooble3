# Estándares de Comunicación entre Microservicios - Nooble AI (Parte 2)

## 6. Patrones de Comunicación por Nivel de Flujo (Continuación)

### 6.2 Flujos Intermedios (Nivel 2)

Para los flujos intermedios como Conversación Multi-turno, Uso de Herramientas Simples y Generación con Memoria, se aplican estos patrones:

- **Comunicación primaria**: 80% asíncrona, 20% sincrónica
- **Latencia esperada**: 3-12 segundos
- **Patrón dominante**: Solicitud-respuesta con contexto ampliado
- **Colas críticas**:
  - `conversation.context.{tenant}.{session}`
  - `tools.execution.{tenant}`
  - `agent.memory.{tenant}.{agent}`
  - `conversation.windowing.{tenant}`

**Ejemplo de secuencia para Uso de Herramientas Simples**:

1. Orchestrator evalúa la solicitud y publica mensaje en `agent_execution.tasks.{tenant}`
2. Agent Execution identifica necesidad de herramienta y solicita ejecución en `tools.execution.{tenant}`
3. Tool Registry valida y ejecuta la herramienta
4. Resultado notificado vía `tools.results.{tenant}.{execution_id}`
5. Agent Execution integra el resultado y genera respuesta final
6. Respuesta notificada al Orchestrator vía WebSocket y en `agent_execution.results.{tenant}.{session}`

### 6.3 Flujos Avanzados (Nivel 3)

Para los flujos avanzados como Workflow Multi-etapa, Herramientas Encadenadas y Decisiones Condicionales, se aplican estos patrones:

- **Comunicación primaria**: 90% asíncrona, 10% sincrónica
- **Latencia esperada**: 5-30 segundos
- **Patrón dominante**: Orquestación de múltiples pasos
- **Colas críticas**:
  - `workflow.execution.{tenant}.{workflow}`
  - `workflow.steps.{tenant}.{workflow}`
  - `tools.chain.{tenant}.{chain_id}`
  - `workflow.decisions.{tenant}.{workflow}`

**Ejemplo de secuencia para Workflow Multi-etapa**:

1. Orchestrator inicia el workflow publicando en `workflow.execution.{tenant}.{workflow}`
2. Workflow Engine coordina la ejecución de cada paso
3. Para cada paso, se envían mensajes a los servicios correspondientes
4. Los resultados intermedios se notifican vía WebSocket para actualizaciones en tiempo real
5. El Workflow Engine mantiene el estado en `workflow.state.{tenant}.{workflow}`
6. Al completarse, el resultado final se notifica al Orchestrator

### 6.4 Flujos Complejos (Nivel 4)

Para los flujos complejos como Ingestión de Documentos, Análisis Multi-documento y Orquestación Multi-agente, se aplican estos patrones:

- **Comunicación primaria**: 95% asíncrona, 5% sincrónica
- **Latencia esperada**: 30-300 segundos
- **Patrón dominante**: Procesamiento distribuido con checkpoints
- **Colas críticas**:
  - `ingestion.processing.{tenant}.{collection}`
  - `batch.processing.{tenant}.{batch_id}`
  - `analysis.multidoc.{tenant}.{analysis_id}`
  - `multiagent.coordination.{tenant}.{task}`

**Ejemplo de secuencia para Ingestión de Documentos**:

1. Orchestrator inicia la ingestión publicando en `ingestion.tasks.{tenant}`
2. Ingestion Service procesa el documento en múltiples etapas:
   - Extracción en `ingestion.extraction.{tenant}`
   - Chunking en `ingestion.chunking.{tenant}`
3. Para la vectorización, publica lotes en `embedding.batch.{tenant}`
4. El estado de procesamiento se actualiza en `ingestion.status.{tenant}.{batch_id}`
5. Las actualizaciones de progreso se notifican vía WebSocket
6. Al finalizar, los resultados se indexan y se notifica la finalización

## 7. Integración de Servicios Específicos

### 7.1 Agent Orchestrator Service

Como componente central de orquestación, este servicio:

- **Actúa como**: Hub central de comunicación
- **Coordina**: Flujos de trabajo complejos multi-servicio
- **Mantiene**: Estado global de sesiones y tareas
- **Expone**: WebSockets para notificaciones en tiempo real

**Interfaces críticas**:

| Servicio Destino | Canal de Comunicación | Descripción |
|-----------------|----------------------|-------------|
| Agent Execution | `agent_execution.tasks.{tenant}` | Tareas de ejecución |
| Conversation | `conversation.context.{tenant}.{session}` | Gestión de contexto |
| Workflow Engine | `workflow.execution.{tenant}.{workflow}` | Inicio de workflows |
| Tool Registry | `tools.requests.{tenant}` | Solicitudes de herramientas |
| Todos | Canal WebSocket `/ws/task_updates` | Notificaciones de estado |

### 7.2 Agent Execution Service

Responsable de la ejecución de la lógica de agentes:

- **Consume de**: Orchestrator, Conversation Service
- **Produce para**: Tool Registry, Query Service, Embedding Service
- **Mantiene**: Estado de ejecución de agentes por sesión

**Interfaces críticas**:

| Servicio Destino | Canal de Comunicación | Descripción |
|-----------------|----------------------|-------------|
| Tool Registry | `tools.execution.{tenant}` | Ejecución de herramientas |
| Query Service | `query.generation.{tenant}` | Generación de respuestas |
| Embedding Service | `embedding.tasks.{tenant}` | Vectorización |
| Agent Management | `agent.configuration.{tenant}` | Configuración de agentes |

### 7.3 Tool Registry Service

Gestiona el registro y ejecución de herramientas:

- **Consume de**: Agent Execution, Workflow Engine
- **Produce para**: Agent Execution, servicios externos
- **Mantiene**: Registro de herramientas y resultados de ejecución

**Interfaces críticas**:

| Servicio Destino | Canal de Comunicación | Descripción |
|-----------------|----------------------|-------------|
| Agent Execution | `tools.results.{tenant}.{execution_id}` | Resultados de herramientas |
| External APIs | Configuración por herramienta | APIs externas |
| Orchestrator | WebSocket `tool_execution_completed` | Notificación de finalización |

### 7.4 Query Service

Gestiona operaciones RAG y generación:

- **Consume de**: Agent Execution, Conversation Service
- **Produce para**: Múltiples consumidores
- **Mantiene**: Cachés y resultados temporales

**Interfaces críticas**:

| Servicio Destino | Canal de Comunicación | Descripción |
|-----------------|----------------------|-------------|
| Embedding Service | `embedding.tasks.{tenant}` | Embeddings para búsqueda |
| Agent Execution | `query.results.{tenant}.{query_id}` | Resultados de búsqueda |
| LLM Providers | APIs configuradas | Generación de texto |

## 8. Estrategias de Manejo de Fallos Estándar

### 8.1 Patrones de Circuit Breaker

Cada servicio debe implementar el patrón Circuit Breaker para proteger contra fallos en cascada:

| Tipo de Servicio | Configuración Recomendada |
|-----------------|--------------------------|
| Crítico (Nivel 1) | Umbral: 3 fallos, Reset: 30s, Half-open: 1 req/15s |
| Estándar (Nivel 2-3) | Umbral: 5 fallos, Reset: 60s, Half-open: 1 req/30s |
| Batch (Nivel 4-5) | Umbral: 10 fallos, Reset: 300s, Half-open: 1 req/60s |

### 8.2 Estrategia de Reintentos

Política estándar de reintentos para todas las operaciones asíncronas:

```
MaxIntentos = 3
DelayInicial = 1000ms
Factor = 2
Jitter = 0.5
```

Ejemplo de cálculo de delay entre intentos:
```
Intento 1: 1000ms
Intento 2: 2000ms ± 1000ms (jitter)
Intento 3: 4000ms ± 2000ms (jitter)
```

### 8.3 Dead Letter Queues

Cada cola principal debe tener una cola de "dead letter" asociada:

```
{servicio}.dead_letter.{tenant}[.{identificador}]
```

Los mensajes que fallan después de todos los reintentos deben ser movidos a esta cola para:
- Análisis posterior
- Recuperación manual
- Detección de problemas sistemáticos

## 9. Monitoreo y Observabilidad

### 9.1 Métricas Estándar

Cada servicio debe exponer las siguientes métricas:

| Métrica | Tipo | Etiquetas | Descripción |
|---------|------|-----------|-------------|
| `nooble_tasks_received_total` | Counter | service, tenant, type | Tareas recibidas |
| `nooble_tasks_processed_total` | Counter | service, tenant, type, status | Tareas procesadas |
| `nooble_task_processing_duration` | Histogram | service, tenant, type | Duración de procesamiento |
| `nooble_queue_depth` | Gauge | service, tenant, queue | Profundidad de cola |
| `nooble_circuit_breaker_state` | Gauge | service, target_service | Estado de circuit breaker |

### 9.2 Distributed Tracing

Todos los servicios deben implementar tracing distribuido:

- **Propagación**: Headers W3C Trace Context
- **Sampling**: Adaptativo basado en carga
- **Span Tags**: Standard OpenTelemetry + custom para la plataforma
- **Valores Críticos**: tenant_id, user_id, session_id, correlation_id

### 9.3 Log Centralizado

Formato estándar de logs para todos los servicios:

```json
{
  "timestamp": "ISO-timestamp",
  "level": "DEBUG|INFO|WARN|ERROR|FATAL",
  "service": "service-name",
  "tenant_id": "tenant-id",
  "correlation_id": "correlation-id",
  "message": "Descripción del evento",
  "context": {
    // Datos adicionales específicos del evento
  }
}
```

## 10. Comunicación Frontend-Backend

### 10.1 Interfaces API REST

Para la comunicación entre frontend y backend se usan APIs REST:

- **Base URL**: `/api/v1`
- **Autenticación**: JWT Bearer token
- **Identificación de tenant**: Header `X-Tenant-ID`
- **Códigos de respuesta estándar**:
  - 200: Éxito
  - 202: Aceptado (procesamiento asíncrono)
  - 400: Error de solicitud
  - 401: No autenticado
  - 403: No autorizado
  - 404: No encontrado
  - 429: Demasiadas solicitudes
  - 500: Error interno

### 10.2 WebSockets para Tiempo Real

El frontend se comunica con el backend para actualizaciones en tiempo real a través de:

```
ws://agent-orchestrator:8000/ws/{tenant_id}/frontend/{session_id}
```

Eventos principales:
- `session_started`
- `agent_thinking`
- `agent_response`
- `tool_execution_progress`
- `session_completed`
