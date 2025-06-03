# Tool Registry Service

## Descripción
Servicio encargado del registro, validación y ejecución de herramientas (tools) que pueden ser utilizadas por los agentes. Proporciona un mecanismo central para descubrir y utilizar herramientas de forma segura y controlada.

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

> 📌 **Este documento describe el Tool Registry Service**, ubicado en el Nivel 2 como servicio funcional encargado del registro, validación y ejecución de herramientas utilizadas por los agentes

## 🔄 Flujos de Trabajo Principales

### 1. Ejecución con Herramientas
```
Cliente → Orchestrator → Agent Execution → Tool Registry (descubrimiento) → Tool Registry (ejecución) → Respuesta
```

### 2. Registro de Nuevas Herramientas
```
Cliente → Orchestrator → Tool Registry (validación) → Tool Registry (registro) → Notificación
```

> 🔍 **Rol del Tool Registry**: Centralizar el registro, validación, descubrimiento y ejecución segura de herramientas disponibles para los agentes.

## Estructura
```
tool-registry-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # ToolRegistrySettings
│   └── constants.py             # Tipos de herramientas
├── models/
│   ├── __init__.py
│   ├── tool.py                  # Tool, ToolConfig, ToolMetadata
│   ├── registration.py          # ToolRegistration, ToolUpdate
│   └── execution.py             # ToolExecutionRequest/Response
├── routes/
│   ├── __init__.py
│   ├── tools.py                 # CRUD de herramientas
│   ├── registry.py              # Registro y discovery
│   ├── internal.py              # Ejecución de herramientas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── tool_registry.py         # Registro central
│   ├── tool_validator.py        # Validación de herramientas
│   └── tool_factory.py          # Factory de herramientas
├── tools/
│   ├── __init__.py
│   ├── base.py                  # BaseTool interface
│   ├── rag_tools.py             # RAGQueryTool, RAGSearchTool
│   ├── general_tools.py          # Calculator, DateTime, etc.
│   └── external_api_tool.py      # ExternalAPITool
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── tool_execution_tasks.py # Tareas de ejecución de herramientas
│       └── registration_tasks.py  # Tareas de registro y validación
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Tool Registry Service

```
+-------------------------------------------------+
|             COLAS DE TOOL REGISTRY               |
+-------------------------------------------------+
|                                                 |
| tool_registry_tasks:{tenant_id}                 | → Cola principal de tareas
| tool_execution:{tenant_id}                      | → Ejecución de herramientas
| tool_registration:{tenant_id}                   | → Registro de herramientas
| tool_validation:{tenant_id}                     | → Validación de herramientas
|                                                 |
+-------------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Control de acceso granular**: Permisos por agente, tenant y herramienta
- **Ejecución asíncrona**: Procesamiento paralelo de llamadas a herramientas
- **Validación automática**: Verificación de funcionamiento correcto de herramientas

### Formato de Mensaje Estandarizado

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "tool_execution|tool_registration|tool_discovery",
  "priority": 0-9,
  "metadata": {
    "agent_id": "agent-identifier",
    "session_id": "session-identifier",
    "execution_id": "execution-identifier",
    "source": "agent_execution|workflow|api"
  },
  "payload": {
    "tool_id": "tool-identifier",
    "tool_name": "tool-name",
    "tool_type": "rag|calculator|external_api|...",
    "parameters": {},
    "timeout_ms": 5000
  }
}
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Conexión bidireccional con Agent Orchestrator
- **Notificaciones de herramientas**: Actualizaciones en tiempo real del estado de ejecución
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Tool Registry Service

- `tool_execution_started`: Inicio de ejecución de herramienta
- `tool_execution_completed`: Finalización exitosa de herramienta
- `tool_execution_failed`: Error en la ejecución de herramienta
- `tool_registered`: Nueva herramienta registrada
- `tool_validation_completed`: Validación de herramienta finalizada

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

async def notify_tool_execution(task_id, tenant_id, execution_data, global_task_id=None):
    """Notifica sobre la ejecución de una herramienta"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "tool_execution_completed",
                "service": "tool-registry",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "tool_id": execution_data["tool_id"],
                    "execution_id": execution_data["execution_id"],
                    "result": execution_data["result"],
                    "execution_time_ms": execution_data["execution_time_ms"]
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar ejecución de herramienta via WebSocket: {e}")

async def notify_tool_registration(task_id, tenant_id, tool_data, global_task_id=None):
    """Notifica el registro de una nueva herramienta"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "tool_registered",
                "service": "tool-registry",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "tool_id": tool_data["tool_id"],
                    "tool_name": tool_data["tool_name"],
                    "tool_type": tool_data["tool_type"]
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar registro de herramienta via WebSocket: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Extensibilidad**: Fácil adición de nuevas herramientas sin modificar otros servicios
- **Registro centralizado**: Catálogo único de todas las herramientas disponibles
- **Seguridad y control de acceso**: Gestión de permisos para uso de herramientas
- **Monitoreo y observabilidad**: Seguimiento detallado de uso de cada herramienta
```

## Funciones Clave
1. Registro y discovery de herramientas disponibles
2. Validación de permisos y configuraciones
3. Ejecución segura de herramientas
4. Abstracción de APIs externas

## Sistema de Cola de Trabajo
- **Tareas**: Ejecución asíncrona de herramientas de larga duración, validación de herramientas externas
- **Implementación**: Redis Queue con sistema de resultados y estado
- **Procesamiento**: Herramientas que requieren tiempo de ejecución prolongado

## Comunicación
- **HTTP**: API REST para registro y ejecución de herramientas
- **WebSocket**: Actualizaciones en tiempo real del estado de ejecución
- **Callbacks**: Notificaciones de finalización de tareas en cola

## Integración con otros Servicios
El Tool Registry Service se comunica exclusivamente a través del Agent Orchestrator Service, que actúa como intermediario para todas las interacciones con otros servicios:

1. Agent Execution Service: Para proporcionar herramientas a los agentes
2. Agent Management Service: Para validar permisos de herramientas
3. Workflow Engine Service: Para herramientas utilizadas en flujos de trabajo

Además, no se comunica directamente con el Query Service ni el Embedding Service, sino que todas las operaciones RAG o de embeddings son solicitadas a través del Agent Orchestrator Service, manteniendo así la arquitectura centralizada.