# Workflow Engine Service

## Descripción
Servicio responsable de definir, gestionar y ejecutar flujos de trabajo (workflows) para orquestación de tareas complejas. Permite la creación de flujos basados en nodos interconectados con condiciones y transiciones.

## 🏗️ Ecosistema de Servicios

La arquitectura se organiza en 3 niveles jerárquicos:

### Nivel 1: Orquestación

- **Agent Orchestrator**: Punto de entrada único, gestión de sesiones y coordinación global

### Nivel 2: Servicios Funcionales

- **Conversation Service**: Historial y contexto de conversaciones
- **Workflow Engine**: Flujos de trabajo complejos multi-etapa
- **Agent Execution**: Lógica específica del agente
- **Tool Registry**: Registro y ejecución de herramientas

### Nivel 3: Servicios de Infraestructura

- **Query Service**: Procesamiento RAG y LLM
- **Embedding Service**: Generación de embeddings vectoriales
- **Ingestion Service**: Procesamiento de documentos

> 📌 **Este documento describe el Workflow Engine Service**, ubicado en el Nivel 2 como servicio funcional encargado de gestionar flujos de trabajo complejos multi-etapa

## 🔄 Flujos de Trabajo Principales

### 1. Flujo Multi-Etapa con Herramientas
```
Cliente → Orchestrator → Workflow Engine (define flujo) → Agent Execution → Tool Registry → Query Service → Workflow Engine (avanza flujo) → Respuesta
```

### 2. Flujo de Decisión Condicional
```
Cliente → Orchestrator → Workflow Engine (evalúa condiciones) → [Ramificación condicional] → Servicios correspondientes → Workflow Engine (sincroniza) → Respuesta
```

> 🔍 **Rol del Workflow Engine**: Definir, ejecutar y coordinar flujos de trabajo complejos con nodos, condiciones y transiciones para modelar procesos de negocio personalizados.

## Estructura
```
workflow-engine-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # WorkflowEngineSettings
│   └── constants.py             # Estados, tipos de nodos
├── models/
│   ├── __init__.py
│   ├── workflow.py              # Workflow, WorkflowDefinition
│   ├── node.py                  # WorkflowNode, NodeConnection
│   ├── execution.py             # WorkflowExecution, ExecutionState
│   └── step.py                  # WorkflowStep, StepResult
├── routes/
│   ├── __init__.py
│   ├── workflows.py             # CRUD workflows
│   ├── execution.py             # Ejecución de workflows
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── workflow_manager.py      # Gestión de definiciones
│   ├── workflow_executor.py     # Motor de ejecución
│   ├── state_manager.py         # Gestión de estado
│   └── step_processor.py        # Procesador de pasos
├── engine/
│   ├── __init__.py
│   ├── conditions.py            # Evaluador de condiciones
│   ├── transitions.py           # Gestor de transiciones
│   └── variables.py             # Gestor de variables
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── workflow_tasks.py      # Tareas de ejecución de workflows
│       └── step_tasks.py          # Procesamiento de pasos individuales
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── main.py
├── requirements.txt
├── Dockerfile

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Workflow Engine

```
+-----------------------------------------------+
|             COLAS DE WORKFLOW                 |
+-----------------------------------------------+
|                                               |
| workflow_tasks:{tenant_id}                    | → Cola principal de tareas
| workflow_executions:{tenant_id}:{workflow_id} | → Estado de ejecuciones
| workflow_steps:{tenant_id}:{execution_id}     | → Pasos individuales
| workflow_events:{tenant_id}:{execution_id}    | → Eventos de workflow
|                                               |
+-----------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Persistencia de estado**: Almacenamiento del estado de ejecución
- **Ejecución distribuida**: Procesamiento paralelo de pasos independientes
- **Checkpointing**: Capacidad de reanudar workflows desde puntos de control

### Formato de Mensaje Estandarizado

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "workflow_id": "workflow-definition-id",
  "execution_id": "execution-instance-id",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed|paused",
  "type": "workflow_start|step_execution|condition_evaluation",
  "priority": 0-9,
  "metadata": {
    "agent_id": "agent-identifier",
    "session_id": "session-identifier",
    "user_id": "optional-user-id",
    "source": "api|orchestrator|scheduled"
  },
  "payload": {
    "current_node": "node-identifier",
    "input_data": {},
    "execution_context": {},
    "variables": {}
  }
}
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Conexión bidireccional con Agent Orchestrator
- **Eventos de progreso**: Actualizaciones en tiempo real del estado del workflow
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Workflow Engine

- `workflow_started`: Inicio de ejecución de un workflow
- `workflow_step_completed`: Finalización de paso individual
- `workflow_decision_point`: Punto de decisión entre caminos alternativos
- `workflow_completed`: Workflow completado en su totalidad
- `workflow_paused`: Workflow en espera de entrada o decisión

### Implementación WebSocket para Notificaciones:

```python
# websocket/notifier.py
import asyncio
import websockets
import json
import logging
from datetime import datetime

ORCHESTRATOR_WS_URL = "ws://agent-orchestrator:8000/ws/task_updates"

logger = logging.getLogger(__name__)

async def notify_workflow_progress(task_id, tenant_id, execution_data, global_task_id=None):
    """Notifica el progreso de un workflow"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "workflow_step_completed",
                "service": "workflow-engine",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "workflow_id": execution_data["workflow_id"],
                    "execution_id": execution_data["execution_id"],
                    "step_id": execution_data["step_id"],
                    "next_node": execution_data["next_node"],
                    "progress_percentage": execution_data["progress"]
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar progreso de workflow via WebSocket: {e}")

async def notify_workflow_completed(task_id, tenant_id, result, global_task_id=None):
    """Notifica la finalización de un workflow"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "workflow_completed",
                "service": "workflow-engine",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": result
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar completado via WebSocket: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Modelado de procesos complejos**: Capacidad para representar flujos de decisión sofisticados
- **Flexibilidad de configuración**: Definición de workflows sin necesidad de cambios de código
- **Observabilidad completa**: Seguimiento detallado de cada paso en la ejecución
- **Escalabilidad independiente**: Puede escalarse según la complejidad y demanda de workflows
```

## Funciones Clave
1. Definición y gestión de workflows basados en nodos
2. Ejecución de workflows con maquina de estados
3. Procesamiento condicional y ramificaciones
4. Gestión de variables y contexto entre pasos

## Sistema de Cola de Trabajo
- **Tareas**: Ejecución de workflows completos y pasos individuales
- **Implementación**: Redis Queue con sistema de estado distribuido
- **Procesamiento**: Workflows de larga duración con puntos de control

## Comunicación
- **HTTP**: API REST para definición y gestión de workflows
- **WebSocket**: Actualizaciones en tiempo real del estado de ejecución
- **Callbacks**: Notificaciones en puntos clave del workflow

## Integración con otros Servicios
El Workflow Engine Service se comunica principalmente con el Agent Orchestrator Service, que actúa como intermediario central para todas las interacciones con otros servicios del sistema:

1. Agent Orchestrator Service: Punto principal de comunicación para orquestar flujos complejos
2. Tool Registry Service: No hay comunicación directa, sino a través del orquestador para ejecutar herramientas
3. Conversation Service: No hay comunicación directa, sino a través del orquestador para workflows basados en conversaciones
4. Agent Execution Service: No hay comunicación directa, sino a través del orquestador para ejecución de agentes

Este patrón de comunicación centralizada asegura la consistencia en el control de acceso, el seguimiento de tokens y la trazabilidad de las operaciones en todo el sistema.