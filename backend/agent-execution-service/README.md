# Agent Execution Service

## Descripción
Servicio encargado de la ejecución de agentes, procesamiento de solicitudes de los usuarios y coordinación con servicios de consulta y embedding.

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

> 📌 **Este documento describe el Agent Execution Service**, ubicado en el Nivel 2 como servicio funcional encargado de la ejecución de la lógica específica de cada agente

## 🔄 Flujos de Trabajo Principales

### 1. Consulta Normal (Participación del Agent Execution)
```
Cliente → Orchestrator → Agent Execution → Embedding Service → Query Service → Respuesta
```

### 2. Ejecución con Herramientas
```
Cliente → Orchestrator → Agent Execution → Tool Registry → [Ejecución de herramientas] → Query Service → Respuesta
```

> 🔍 **Rol del Agent Execution**: Ejecutar la lógica principal del agente, coordinando interacciones con las herramientas, procesando prompts y manejando llamadas a LLM.

## Estructura
```
agent-execution-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # AgentExecutionSettings
│   └── constants.py             # Modelos LLM, timeouts
├── models/
│   ├── __init__.py
│   ├── execution.py             # ExecutionRequest, ExecutionResponse
│   ├── prompt.py                # PromptTemplate, PromptConfig
│   ├── completion.py            # CompletionRequest, CompletionResponse
│   └── tool_call.py             # ToolCall, ToolResult
├── routes/
│   ├── __init__.py
│   ├── execute.py               # Endpoints de ejecución
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── langchain_executor.py    # LangChainExecutor principal
│   ├── prompt_processor.py      # Procesamiento de prompts
│   ├── tool_orchestrator.py     # Orquestación de herramientas
│   └── llm_factory.py           # Factory para modelos LLM
├── providers/
│   ├── __init__.py
│   ├── openai_provider.py       # Proveedor OpenAI
│   ├── groq_provider.py         # Proveedor Groq
│   └── base_provider.py         # Interface base
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── execution_tasks.py    # Tareas de ejecución
│       └── batch_tasks.py        # Procesamiento por lotes
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

### Estructura Jerárquica de Colas del Agent Execution Service

```
+--------------------------------------------------+
|             COLAS DE AGENT EXECUTION              |
+--------------------------------------------------+
|                                                  |
| agent_execution:{tenant_id}                      | → Cola principal de tareas
| agent_tools:{tenant_id}:{agent_id}               | → Llamadas a herramientas
| agent_responses:{tenant_id}:{execution_id}       | → Respuestas de ejecución
| agent_streaming:{tenant_id}:{execution_id}       | → Respuestas en streaming
|                                                  |
+--------------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Ejecución asíncrona**: Procesamiento no bloqueante de solicitudes
- **Retries inteligentes**: Manejo automático de fallos transitorios
- **Prioridades dinámicas**: Ajuste de prioridad según tipo de agente y plan

### Formato de Mensaje Estandarizado

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "agent_id": "agent-identifier",
  "execution_id": "execution-uuid",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "agent_execution|tool_call|streaming_response",
  "priority": 0-9,
  "metadata": {
    "conversation_id": "conversation-id",
    "session_id": "session-identifier",
    "workflow_id": "optional-workflow-id",
    "source": "api|orchestrator|workflow"
  },
  "payload": {
    "query": "Consulta del usuario",
    "agent_config": {},
    "context": {},
    "tool_calls": []
  }
}
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Conexión bidireccional con Agent Orchestrator
- **Modo streaming**: Envío incremental de tokens de respuesta
- **Notificaciones de herramientas**: Eventos para llamadas a herramientas
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Agent Execution Service

- `agent_execution_started`: Inicio de la ejecución del agente
- `tool_call_requested`: Solicitud de llamada a herramienta
- `agent_response_token`: Token individual en modo streaming
- `agent_execution_completed`: Respuesta completa generada
- `agent_execution_failed`: Error en la ejecución del agente

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

async def notify_agent_progress(task_id, tenant_id, execution_data, global_task_id=None):
    """Notifica el progreso de una ejecución de agente"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "agent_execution_progress",
                "service": "agent-execution",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": execution_data
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar progreso de agente via WebSocket: {e}")

async def stream_agent_token(task_id, tenant_id, token, is_final=False, global_task_id=None):
    """Envía un token individual en modo streaming"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "agent_response_token",
                "service": "agent-execution",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "token": token,
                    "is_final": is_final
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al enviar token streaming: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Especialización en ejecución**: Foco en la lógica del agente sin preocuparse por orquestación
- **Integración flexible**: Soporte para múltiples proveedores de LLM y formatos de prompt
- **Separación de responsabilidades**: Clara división entre ejecución y herramientas
- **Escalabilidad independiente**: Puede escalarse según la demanda de agentes activos
```

## Funciones Clave
1. Ejecución de agentes con LLMs (Groq, OpenAI)
2. Procesamiento de prompts y completion
3. Orquestación de herramientas y llamadas a herramientas
4. Streaming de respuestas generativas

## Sistema de Cola de Trabajo
- **Tareas**: Procesamiento asíncrono de ejecuciones complejas, lotes de inferencias
- **Implementación**: Redis Queue con prioridad para tareas críticas
- **Procesamiento**: Tareas en segundo plano para ejecuciones que requieren más tiempo

## Comunicación
- **HTTP**: API REST para solicitudes de ejecución
- **WebSocket**: Streaming de respuestas y actualizaciones de ejecución
- **Callbacks**: Notificaciones de finalización de tareas en cola

## Integración con otros Servicios
El Agent Execution Service se comunica principalmente con:
1. Tool Registry Service: Para ejecutar herramientas durante el proceso de razonamiento
2. Agent Management Service: Para obtener configuraciones de agentes
3. Agent Orchestrator Service: Para solicitar operaciones de consulta o embedding (NO directamente con Query/Embedding Services)