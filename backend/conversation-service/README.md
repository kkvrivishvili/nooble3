# Conversation Service

## Descripción
Servicio encargado de gestionar las conversaciones entre usuarios y agentes, incluyendo historial, contexto y seguimiento de sesiones.

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

> 📌 **Este documento describe el Conversation Service**, ubicado en el Nivel 2 como servicio funcional encargado de la gestión del historial y contexto de las conversaciones

## 🔄 Flujos de Trabajo Principales

### 1. Consulta Normal (Con historial de conversación)
```
Cliente → Orchestrator → Conversation Service (recuperar historial) → Agent Execution → Embedding Service → Query Service → Conversation Service (guardar interacción) → Respuesta
```

### 2. Conversación multi-turno con memoria
```
Cliente → Orchestrator → Conversation Service (memoria + contexto) → Agent Execution → Query Service → Conversation Service (actualizar contexto) → Respuesta
```

> 🔍 **Rol del Conversation Service**: Mantener el historial de conversación, gestionar la memoria contextual y facilitar conversaciones de múltiples turnos con contexto persistente.

## Estructura
```
conversation-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # ConversationSettings
│   └── constants.py             # TTLs, límites de memoria
├── models/
│   ├── __init__.py
│   ├── conversation.py          # Conversation, ConversationCreate
│   ├── message.py               # Message, MessageRole, MessageCreate
│   ├── memory.py                # ConversationMemory, MemoryWindow
│   └── session.py               # Session, SessionContext
├── routes/
│   ├── __init__.py
│   ├── conversations.py         # CRUD conversaciones
│   ├── messages.py              # Gestión de mensajes
│   ├── internal.py              # APIs para Agent Execution
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── conversation_manager.py  # Gestión de conversaciones
│   ├── message_store.py         # Almacenamiento de mensajes
│   ├── memory_manager.py        # ConversationMemoryManager (mejorado)
│   └── context_tracker.py       # Tracking de contexto
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       └── message_tasks.py     # Tareas asíncronas de procesamiento
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── utils/
│   ├── __init__.py
│   └── memory_utils.py          # Utilidades para memoria
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Conversation Service

```
+------------------------------------------------------+
|             COLAS DE CONVERSATION                     |
+------------------------------------------------------+
|                                                      |
| conversation_tasks:{tenant_id}                       | → Cola principal de tareas
| conversation_context:{tenant_id}:{conversation_id}   | → Datos de contexto
| conversation_memory:{tenant_id}:{agent_id}           | → Datos de memoria
| conversation_updates:{tenant_id}:{conversation_id}   | → Cambios a notificar
|                                                      |
+------------------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Persistencia de memoria**: Almacenamiento eficiente del contexto de conversación
- **Ventanas de memoria deslizantes**: Optimización para conversaciones largas
- **Gestión avanzada de TTL**: Control sobre caducidad de datos de conversación

### Formato de Mensaje Estandarizado

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "conversation_id": "conversation-uuid",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "store_message|retrieve_context|update_memory",
  "priority": 0-9,
  "metadata": {
    "agent_id": "agent-identifier",
    "session_id": "session-identifier",
    "user_id": "optional-user-id"
  },
  "payload": {
    "message": {
      "role": "user|assistant|system",
      "content": "Contenido del mensaje",
      "timestamp": "ISO-timestamp"
    },
    "memory_window": 10,
    "include_system_messages": true
  }
}
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Conexión bidireccional con Agent Orchestrator
- **Notificaciones de mensajes**: Actualización en tiempo real de mensajes entrantes
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Conversation Service

- `conversation_created`: Nueva conversación iniciada
- `message_stored`: Mensaje guardado en la base de datos
- `context_updated`: Actualización del contexto de conversación
- `memory_window_shifted`: Cambio en la ventana de memoria activa

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

async def notify_message_stored(task_id, tenant_id, message_data, global_task_id=None):
    """Notifica que un nuevo mensaje ha sido almacenado"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "message_stored",
                "service": "conversation",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "conversation_id": message_data["conversation_id"],
                    "message_id": message_data["message_id"],
                    "role": message_data["role"]
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar mensaje via WebSocket: {e}")

async def notify_context_updated(task_id, tenant_id, conversation_id, global_task_id=None):
    """Notifica que el contexto de una conversación ha sido actualizado"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": "context_updated",
                "service": "conversation",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "conversation_id": conversation_id
                }
            }
            await websocket.send(json.dumps(notification))
    except Exception as e:
        logger.error(f"Error al notificar actualización de contexto via WebSocket: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Gestión eficiente de contexto**: Mantenimiento óptimo del historial de conversación
- **Soporte para conversaciones largas**: Estrategias avanzadas de memoria y resumen
- **Aislamiento de responsabilidades**: Clara separación entre almacenamiento de mensajes y lógica de agente
- **Escalabilidad independiente**: Puede escalarse según la demanda de conversaciones

## Funciones Clave
1. Gestión de conversaciones y mensajes
2. Mantenimiento de contexto de conversación
3. Streaming de respuestas en tiempo real
4. Persistencia de historial con metadatos enriquecidos

## Sistema de Cola de Trabajo
- **Tareas**: Procesamiento asíncrono de mensajes, generación de resúmenes, análisis de sentimiento
- **Implementación**: Redis Queue con priorización de mensajes
- **Procesamiento**: Tareas en segundo plano para optimizar la experiencia del usuario

## Comunicación
- **HTTP**: API REST para creación y consulta de conversaciones/mensajes
- **WebSocket**: Streaming de respuestas y actualizaciones en tiempo real
- **Callbacks**: Notificaciones asíncronas al finalizar tareas en cola

## Integración con otros Servicios
El Conversation Service se comunica exclusivamente a través del Agent Orchestrator Service, que actúa como intermediario para todas las interacciones con:

1. Agent Execution Service: Para procesamiento de mensajes a través de agentes
2. Agent Management Service: Para validación de configuraciones
3. Workflow Engine Service: Para conversaciones basadas en flujos de trabajo

No se realizan comunicaciones directas con otros servicios sin pasar por el orquestador central, manteniendo así la arquitectura de microservicios correctamente aislada y gestionada.