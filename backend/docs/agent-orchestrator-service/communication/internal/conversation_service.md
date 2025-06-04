# Comunicación con Conversation Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Comunicación con Conversation Service](#comunicación-con-conversation-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Integración en Flujos de Trabajo](#2-integración-en-flujos-de-trabajo)
  - [3. Estructura de Colas](#3-estructura-de-colas)
  - [4. Formato de Mensajes](#4-formato-de-mensajes)
  - [5. Comunicación WebSocket](#5-comunicación-websocket)
  - [6. REST API](#6-rest-api)
  - [7. Gestión de Errores](#7-gestión-de-errores)

## 1. Visión General

El Agent Orchestrator Service interactúa con el Conversation Service para mantener el historial, el contexto y la memoria de las sesiones de conversación. Esta comunicación es fundamental para la continuidad de las conversaciones multi-turno y para proporcionar contexto relevante a otros servicios como el Agent Execution Service.

### 1.1 Principios de Interacción

- **Fuente de Verdad**: El Conversation Service es la fuente de verdad definitiva para todo el historial y contexto de conversaciones
- **Comunicación Bidireccional**: El Orchestrator tanto consulta como actualiza datos en el Conversation Service
- **Separación de Responsabilidades**: El Conversation Service solo gestiona el almacenamiento y recuperación de conversaciones, mientras que el Orchestrator decide cuándo y cómo utilizarlas
- **Procesamiento Asincrónico**: Las operaciones intensivas de almacenamiento y procesamiento de contexto se delegan al Conversation Service de forma asíncrona

![Diagrama de Comunicación](../diagrams/orchestrator_conversation_communication.png)

## 2. Integración en Flujos de Trabajo

### 2.1 Consulta con Contexto (Nivel 1)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant CS as Conversation Service
    participant AE as Agent Execution
    participant Q as Query Service
    
    C->>O: Nueva consulta
    O->>CS: Obtener contexto
    CS->>O: Historial relevante
    O->>AE: Consulta + contexto
    AE->>Q: Generar con contexto
    Q->>AE: Respuesta contextual
    AE->>O: Resultado
    O->>CS: Almacenar interacción
    O->>C: Respuesta final
```

### 2.2 Conversación Multi-turno (Nivel 2)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant CS as Conversation Service
    participant AE as Agent Execution
    
    loop Cada turno de conversación
        C->>O: Mensaje
        O->>CS: Contexto completo
        CS->>O: Ventana de contexto
        O->>AE: Procesar con historial
        AE->>O: Respuesta
        O->>CS: Actualizar historial
        O->>C: Respuesta
    end
```

### 2.3 Generación con Memoria (Nivel 2)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant AE as Agent Execution
    participant CS as Conversation Service
    participant Q as Query Service
    
    C->>O: Consulta personalizada
    O->>AE: Procesar con memoria
    AE->>CS: Obtener memoria de conversación
    CS->>AE: Contexto personalizado
    AE->>Q: Generar respuesta
    Q->>AE: Respuesta personalizada
    AE->>CS: Actualizar memoria
    AE->>O: Resultado
    O->>C: Respuesta final
```

## 3. Estructura de Colas

El Orchestrator interactúa con el Conversation Service a través de las siguientes colas Redis. Siguiendo el estándar global de comunicación, todas las colas tienen el formato `service-name.[priority].[domain].[action]`:

### 3.1 Colas que Produce el Orchestrator 

| Cola | Domain | Action | Propósito | Prioridad |
|------|--------|--------|------------|----------|
| `conversation_service.high.conversation.task` | `conversation` | `task` | Cola principal para tareas de conversación | Alta |
| `conversation_service.medium.message.store` | `message` | `store` | Almacenamiento de nuevos mensajes | Media |
| `conversation_service.high.context.retrieve` | `context` | `retrieve` | Solicitudes de recuperación de contexto | Alta |
| `conversation_service.low.conversation.history` | `conversation` | `history` | Obtención de historial completo | Baja |
| `conversation_service.high.memory.update` | `memory` | `update` | Actualización de memoria de conversación | Alta |

### 3.2 Colas que Consume el Orchestrator

| Cola | Domain | Action | Propósito | Prioridad |
|------|--------|--------|------------|----------|
| `agent_orchestrator.high.context.result` | `context` | `result` | Resultados de recuperación de contexto | Alta |
| `agent_orchestrator.medium.conversation.update` | `conversation` | `update` | Notificaciones de actualizaciones | Media |
| `agent_orchestrator.high.memory.result` | `memory` | `result` | Respuestas de actualización de memoria | Alta |

### 3.3 Campos de Control Estándar

Todos los mensajes intercambiados en estas colas incluyen los siguientes campos de control estándar:

- `message_id`: Identificador único del mensaje (UUID)
- `correlation_id`: ID para correlacionar solicitudes y respuestas
- `task_id`: Identificador de la tarea asociada
- `tenant_id`: Identificador del tenant
- `schema_version`: Versión del esquema del mensaje (actualmente "1.1")
- `type`: Objeto con campos `domain` y `action` que categorizan el mensaje
- `priority`: Nivel de prioridad (1-10, siendo 10 la mayor prioridad)
- `source_service`: Servicio de origen del mensaje
- `target_service`: Servicio de destino del mensaje

## 4. Formato de Mensajes

### 4.1 Mensaje de Tarea de Conversación

**Domain**: `conversation`  
**Action**: `task`

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "tenant-identifier",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002",
  "created_at": "2025-06-03T16:30:45.123Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "conversation",
    "action": "task"
  },
  "priority": 5,
  "source_service": "agent_orchestrator",
  "target_service": "conversation_service",
  "metadata": {
    "trace_id": "trace-abc123",
    "session_id": "session-uuid",
    "user_id": "user-uuid",
    "agent_id": "agent-uuid",
    "conversation_id": "conversation-uuid"
  },
  "payload": {
    "task_type": "process",
    "task_parameters": {
      // Parámetros específicos de la tarea
    }
  }
}
```

### 4.2 Mensaje de Almacenamiento 

**Domain**: `message`  
**Action**: `store`

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440003",
  "task_id": "550e8400-e29b-41d4-a716-446655440004",
  "tenant_id": "tenant-identifier",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440005",
  "created_at": "2025-06-03T16:32:10.456Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "message",
    "action": "store"
  },
  "priority": 5,
  "source_service": "agent_orchestrator",
  "target_service": "conversation_service",
  "metadata": {
    "trace_id": "trace-def456",
    "session_id": "session-uuid",
    "user_id": "user-uuid",
    "agent_id": "agent-uuid",
    "conversation_id": "conversation-uuid"
  },
  "payload": {
    "message": {
      "id": "msg-uuid-1",
      "role": "user",
      "content": "Contenido del mensaje",
      "timestamp": "2025-06-03T16:32:05.789Z",
      "content_type": "text/plain",
      "tokens": 15
    },
    "update_context": true,
    "important": false
  }
}
```

### 4.3 Mensaje de Solicitud de Contexto

**Domain**: `context`  
**Action**: `retrieve`

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440006",
  "task_id": "550e8400-e29b-41d4-a716-446655440007",
  "tenant_id": "tenant-identifier",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440008",
  "created_at": "2025-06-03T16:33:20.123Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "context",
    "action": "retrieve"
  },
  "priority": 7,
  "source_service": "agent_orchestrator",
  "target_service": "conversation_service",
  "metadata": {
    "trace_id": "trace-ghi789",
    "session_id": "session-uuid",
    "user_id": "user-uuid",
    "agent_id": "agent-uuid",
    "conversation_id": "conversation-uuid"
  },
  "payload": {
    "message_count": 10,
    "include_system_messages": true,
    "max_tokens": 4000,
    "recency_bias": 0.7,
    "context_type": "chat_history",
    "filter": {
      "from_timestamp": "2025-06-01T00:00:00Z",
      "exclude_tags": ["debug", "system-only"]
    }
  }
}
```

### 4.4 Mensaje de Resultado de Contexto

**Domain**: `context`  
**Action**: `result`

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440009",
  "task_id": "550e8400-e29b-41d4-a716-446655440010",
  "original_task_id": "550e8400-e29b-41d4-a716-446655440007",
  "tenant_id": "tenant-identifier",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440008",
  "created_at": "2025-06-03T16:33:45.456Z",
  "schema_version": "1.1",
  "status": "completed",
  "type": {
    "domain": "context",
    "action": "result"
  },
  "source_service": "conversation_service",
  "target_service": "agent_orchestrator",
  "metadata": {
    "trace_id": "trace-ghi789",
    "session_id": "session-uuid",
    "user_id": "user-uuid",
    "agent_id": "agent-uuid",
    "conversation_id": "conversation-uuid",
    "processing_time_ms": 235
  },
  "payload": {
    "messages": [
      {
        "id": "msg-uuid-1",
        "role": "user",
        "content": "¿Cómo puedo configurar mi agente?",
        "timestamp": "2025-06-03T16:30:00.000Z",
        "content_type": "text/plain",
        "tokens": 12
      },
      {
        "id": "msg-uuid-2",
        "role": "assistant",
        "content": "Puedes configurar tu agente desde el dashboard...",
        "timestamp": "2025-06-03T16:30:20.000Z",
        "content_type": "text/plain",
        "tokens": 15
      },
      // ... más mensajes ...
    ],
    "context_summary": "Conversación sobre configuración de agentes y opciones disponibles",
    "total_messages": 12,
    "included_messages": 10,
    "total_tokens": 1250,
    "has_more": true,
    "relevance_score": 0.85,
    "context_type": "chat_history"
  }
}
```

### 4.5 Mensaje de Actualización de Conversación

**Domain**: `conversation`  
**Action**: `update`

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440011",
  "tenant_id": "tenant-identifier",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440012",
  "created_at": "2025-06-03T16:34:10.789Z",
  "schema_version": "1.1",
  "type": {
    "domain": "conversation",
    "action": "update"
  },
  "priority": 4,
  "source_service": "conversation_service",
  "target_service": "agent_orchestrator", 
  "metadata": {
    "trace_id": "trace-jkl012",
    "session_id": "session-uuid",
    "user_id": "user-uuid"
  },
  "payload": {
    "update_type": "new_message",
    "conversation_id": "conversation-uuid",
    "agent_id": "agent-uuid",
    "messages_count": 12,
    "last_message": {
      "id": "msg-uuid-12",
      "role": "assistant",
      "content_preview": "Aquí tienes las opciones de configuración...",
      "timestamp": "2025-06-03T16:34:05.456Z",
      "content_type": "text/plain",
      "tokens": 18
    },
    "requires_attention": false,
    "update_channels": ["websocket", "notification"],
    "importance": "normal"
  }
}
```

## 5. Comunicación WebSocket

El Orchestrator recibe y envía mensajes WebSocket al Conversation Service para actualizaciones en tiempo real, siguiendo el formato domain/action.

### 5.1 Mensajes que Recibe el Orchestrator

| Domain | Action | Propósito | Origen | Procesamiento |
|--------|--------|------------|--------|---------------|
| `task` | `completed` | Notificación de tarea completada | Conversation Service | Actualizar estado y notificar al cliente |
| `task` | `failed` | Error en tarea de procesamiento | Conversation Service | Manejo de errores y reintentos |
| `conversation` | `update` | Actualización de datos de conversación | Conversation Service | Actualizar caché y propagar |
| `memory` | `update` | Actualización de memoria de conversación | Conversation Service | Propagar a todos los servicios relevantes |
| `system` | `status` | Estado y estadísticas del servicio | Conversation Service | Monitoreo y alertas |

### 5.2 Mensajes que Envía el Orchestrator

| Domain | Action | Propósito | Destino | Procesamiento |
|--------|--------|------------|---------|---------------|
| `conversation` | `create` | Creación de nueva conversación | Conversation Service | Inicialización de conversación |
| `task` | `cancel` | Cancelar tarea en proceso | Conversation Service | Detener procesamiento de tarea |
| `session` | `register` | Registrar sesión para actualizaciones | Conversation Service | Activar notificaciones para sesión |
| `system` | `ping` | Verificación de conexión | Conversation Service | Mantener conexión activa |

### 5.3 Implementación

```python
# En el Orchestrator - Manejador de Mensajes WebSocket
async def handle_websocket_message(message_data):
    # Extraer domain y action del mensaje
    message_type = message_data.get("type", {})
    domain = message_type.get("domain")
    action = message_type.get("action")
    
    # Procesar mensaje basado en domain/action
    if domain == "task" and action == "completed":
        # Procesar tarea completada
        task_id = message_data["payload"]["task_id"]
        tenant_id = message_data["tenant_id"]
        correlation_id = message_data.get("correlation_id")
        
        # Log para trazabilidad
        logger.info(f"Tarea completada. task_id={task_id}, trace_id={message_data['metadata'].get('trace_id')}")
        
        # Actualizar estado de tarea y notificar al cliente
        await update_task_status(task_id, tenant_id, "completed", correlation_id)
        await notify_client(tenant_id, message_data["payload"], correlation_id)
        
    elif domain == "task" and action == "failed":
        # Manejar error en tarea
        error = message_data["payload"]["error"]
        task_id = message_data["payload"]["task_id"]
        tenant_id = message_data["tenant_id"]
        trace_id = message_data["metadata"].get("trace_id")
        
        # Registrar error y posiblemente reintentar
        logger.error(f"Error en tarea: {error}. task_id={task_id}, trace_id={trace_id}")
        await handle_task_failure(task_id, tenant_id, error)
        
    elif domain == "conversation" and action == "update":
        # Actualizar cache de conversación
        conversation_id = message_data["payload"]["conversation_id"]
        tenant_id = message_data["tenant_id"]
        update_type = message_data["payload"]["update_type"]
        
        logger.debug(f"Actualización de conversación: {update_type} para {conversation_id}")
        await update_conversation_cache(tenant_id, conversation_id, message_data["payload"])
```

### 5.4 Registro de Suscripciones

Para recibir actualizaciones específicas, el Orchestrator debe registrarse utilizando un mensaje de suscripción:

```python
async def register_for_conversation_updates(websocket, tenant_id, session_id=None, conversation_id=None):
    # Crear mensaje de registro con formato domain/action
    registration_message = {
        "message_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "schema_version": "1.1",
        "type": {
            "domain": "subscription",
            "action": "register"
        },
        "source_service": "agent_orchestrator",
        "target_service": "conversation_service",
        "payload": {
            "topics": [
                "conversation.update",
                "task.completed",
                "task.failed"
            ],
            "filters": {
                "session_id": session_id,
                "conversation_id": conversation_id
            }
        }
    }
    
    # Enviar mensaje de registro
    await websocket.send(json.dumps(registration_message))
```

## 6. REST API

Además de la comunicación asíncrona, el Orchestrator también utiliza las siguientes APIs REST del Conversation Service:

### 6.1 Endpoints Utilizados

| Endpoint | Método | Propósito | Parámetros |
|----------|--------|-----------|------------|
| `/api/v1/conversations` | POST | Crear nueva conversación | tenant_id, agent_id, metadata |
| `/api/v1/conversations/{id}` | GET | Obtener detalles de conversación | conversation_id |
| `/api/v1/conversations/{id}/messages` | GET | Obtener mensajes de conversación | conversation_id, limit, offset |
| `/api/v1/conversations/{id}/messages` | POST | Añadir mensaje a conversación | conversation_id, message |
| `/api/v1/internal/context/{conversation_id}` | GET | Obtener contexto (uso interno) | conversation_id, token_limit, message_count |

### 6.2 Ejemplos de Comunicación REST

**Crear Conversación**:
```python
async def create_conversation(tenant_id, agent_id, user_id, metadata=None):
    url = f"{CONVERSATION_SERVICE_URL}/api/v1/conversations"
    payload = {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "metadata": metadata or {}
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}
        )
        
        if response.status_code == 201:
            return response.json()["data"]
        else:
            raise ServiceCommunicationError(f"Error creating conversation: {response.text}")
```

**Obtener Contexto (para consultas síncronas rápidas)**:
```python
async def get_conversation_context_sync(tenant_id, conversation_id, message_count=10, max_tokens=4000):
    url = f"{CONVERSATION_SERVICE_URL}/api/v1/internal/context/{conversation_id}"
    params = {
        "tenant_id": tenant_id,
        "message_count": message_count,
        "max_tokens": max_tokens
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}
        )
        
        if response.status_code == 200:
            return response.json()["data"]
        else:
            logger.error(f"Error retrieving context: {response.text}")
            return {"messages": []}
```

## 7. Gestión de Errores

### 7.1 Errores Comunes y Estrategias

| Error | Causa | Estrategia de Manejo |
|-------|-------|----------------------|
| `ConversationNotFound` | ID de conversación no existe | Crear nueva conversación y notificar al usuario |
| `ContextProcessingError` | Error al procesar contexto | Utilizar contexto parcial o vacío, logear error |
| `MessageStorageError` | Error al almacenar mensaje | Reintentar con backoff exponencial |
| `RateLimitExceeded` | Límite de tasa excedido | Esperar y reintentar con jitter |
| `ServiceTimeout` | Timeout de servicio | Fallback a modo sin contexto, reintentar en segundo plano |

### 7.2 Circuito de Recuperación

```mermaid
flowchart TD
    A[Solicitud de Contexto] --> B{Disponible en caché?}
    B -->|Sí| C[Usar contexto de caché]
    B -->|No| D[Solicitar a Conversation Service]
    
    D --> E{Respuesta rápida?}
    E -->|Sí| F[Procesar contexto normal]
    E -->|No| G[Usar contexto parcial]
    
    G --> H[Continuar flujo]
    F --> H
    C --> H
    
    H --> I[Actualizar contexto en segundo plano]
```

### 7.3 Política de Reintentos

- **Exponential Backoff**: Retraso inicial de 1s, duplicando hasta 16s
- **Jitter**: +/- 20% del valor de retraso para prevenir tormentas de sincronización
- **Máximo de Intentos**: 3 para operaciones críticas
- **Circuit Breaker**: Se activa después de 5 fallos consecutivos, timeout de reset de 30s
