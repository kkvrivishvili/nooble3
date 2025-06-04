# Catálogo de Eventos WebSocket Domain/Action

*Versión: 2.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Catálogo de Eventos WebSocket Domain/Action](#catálogo-de-eventos-websocket-domainaction)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Estructura Base de Mensajes Domain/Action](#2-estructura-base-de-mensajes-domainaction)
  - [3. Eventos de Servidor a Cliente](#3-eventos-de-servidor-a-cliente)
    - [3.1 Evento: chat.stream](#31-evento-chatstream)
    - [3.2 Evento: chat.completed](#32-evento-chatcompleted)
    - [3.3 Evento: chat.status_update](#33-evento-chatstatus_update)
    - [3.4 Evento: tool.execute](#34-evento-toolexecute)
    - [3.5 Evento: tool.result](#35-evento-toolresult)
    - [3.6 Evento: system.error](#36-evento-systemerror)
    - [3.7 Evento: workflow.status_update](#37-evento-workflowstatus_update)
  - [4. Eventos de Cliente a Servidor](#4-eventos-de-cliente-a-servidor)
    - [4.1 Evento: workflow.cancel](#41-evento-workflowcancel)
    - [4.2 Evento: system.ping](#42-evento-systemping)
    - [4.3 Evento: tool.result](#43-evento-toolresult)
  - [4. Gestión de Estados y Reconexión](#4-gestión-de-estados-y-reconexión)
    - [4.1 Reconexión del Cliente](#41-reconexión-del-cliente)
    - [4.2 Sincronización de Estado](#42-sincronización-de-estado)

## 1. Introducción

Este documento define el catálogo completo de eventos WebSocket utilizados en la comunicación en tiempo real entre el Agent Orchestrator Service y los clientes frontend, implementando el estándar global domain/action. Sirve como referencia centralizada para estandarizar los nombres, formatos y estructura de todos los eventos, asegurando consistencia y trazabilidad en la comunicación.

## 2. Estructura Base de Mensajes Domain/Action

Todos los eventos WebSocket siguen la estructura estandarizada domain/action. Cada mensaje incluye:

```json
{
  "message_id": "uuid-v4",           // Identificador único del mensaje
  "correlation_id": "uuid-v4",       // ID para correlacionar solicitudes y respuestas
  "type": {                        // Clasificación del mensaje
    "domain": "string",            // Dominio funcional (chat, tool, system, workflow)
    "action": "string"             // Acción específica dentro del dominio
  },
  "schema_version": "1.0",         // Versión del esquema de mensaje
  "created_at": "ISO-8601",        // Timestamp de creación
  "tenant_id": "string",           // Identificador del tenant
  "source_service": "string",      // Servicio que originó el mensaje
  "data": {}                       // Payload específico del mensaje
}
```

### Dominios y Acciones Principales

Los eventos WebSocket se clasifican en estos dominios principales:

| Dominio | Descripción | Ejemplos de Acciones |
|---------|-------------|---------------------|
| `chat` | Interacción conversacional | stream, completed, status_update |
| `tool` | Operaciones con herramientas | execute, result |
| `workflow` | Flujos de trabajo | status_update, cancel |
| `system` | Operaciones del sistema | error, ping |
| `session` | Gestión de sesiones | update, sync |

## 3. Eventos de Servidor a Cliente

### 3.1 Evento: chat.stream

Evento para transmisión en tiempo real (streaming) del contenido generado.

**Origen:** Agent Execution Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "stream"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-execution-service",
  "data": {
    "chunk": "fragmento de texto",
    "is_final": false,
    "parent_message_id": "uuid-v4",
    "sequence_number": 5
  }
}
```

### 3.2 Evento: chat.completed

Evento emitido cuando un mensaje ha sido completamente procesado.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "completed"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "content": "Contenido completo de la respuesta",
    "content_type": "text",
    "sources": [
      {
        "title": "Documento A",
        "url": "https://url-to-doc.com",
        "snippet": "fragmento relevante..."
      }
    ],
    "processing_time_ms": 1200,
    "token_count": 250,
    "metadata": {}
  }
}
```

### 3.3 Evento: chat.status_update

Evento para actualizar el estado de un mensaje.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "status_update"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "status": "processing|completed|failed",
    "progress": 0.45,
    "estimated_completion_time": "ISO-8601"
  }
}
```

### 3.4 Evento: tool.execute

Evento para solicitar al cliente la ejecución de una herramienta.

**Origen:** Agent Execution Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "tool",
    "action": "execute"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-execution-service",
  "data": {
    "tool_call_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "tool_id": "nombre-herramienta",
    "params": {
      "param1": "valor1",
      "param2": "valor2"
    },
    "timeout_ms": 30000
  }
}
```

### 3.5 Evento: tool.result

Evento que transmite el resultado de una ejecución de herramienta.

**Origen:** Tool Registry Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "tool-registry-service",
  "data": {
    "tool_call_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "result": {
      "status": "success|error",
      "data": {},
      "error_message": "descripción del error (opcional)",
      "execution_time_ms": 520
    }
  }
}
```

### 3.6 Evento: system.error

Evento para notificar errores durante el procesamiento.

**Origen:** Cualquier servicio (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "system",
    "action": "error"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "service-name",
  "data": {
    "parent_id": "uuid-v4", // ID del mensaje o tarea relacionada
    "error_code": "error.domain.specific_error",
    "error_message": "Descripción del error",
    "error_details": {},
    "severity": "warning|error|critical",
    "is_recoverable": true
  }
}
```

### 3.7 Evento: workflow.status_update

Evento para actualizar el estado de una tarea o workflow.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "status_update"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "workflow_id": "uuid-v4",
    "task_id": "uuid-v4",
    "status": "queued|processing|completed|failed|cancelled",
    "progress": 0.75,
    "status_message": "Procesando documentos...",
    "estimated_completion_time": "ISO-8601",
    "steps_completed": 3,
    "steps_total": 5
  }
}
```

## 4. Eventos de Cliente a Servidor

### 4.1 Evento: workflow.cancel

Evento para cancelar una tarea o workflow en curso.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", // Relacionado con el ID de la tarea a cancelar
  "type": {
    "domain": "workflow",
    "action": "cancel"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    "workflow_id": "uuid-v4",
    "reason": "user_requested",
    "notify_user": true
  }
}
```

### 4.2 Evento: system.ping

Evento para mantener la conexión activa.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "type": {
    "domain": "system",
    "action": "ping"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    "client_timestamp": "ISO-8601",
    "client_info": {
      "version": "1.2.3",
      "platform": "web|ios|android"
    }
  }
}
```

### 4.3 Evento: tool.result

Evento para enviar la respuesta de una herramienta ejecutada en el cliente.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", // Mismo ID del tool.execute original 
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    "tool_call_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "result": {
      "status": "success|error",
      "data": {},
      "error_message": "descripción del error (opcional)",
      "execution_time_ms": 350
    }
  }
}
```

## 5. Gestión de Estados y Reconexión con Domain/Action

### 5.1 Reconexión del Cliente

En caso de desconexión, el cliente debe implementar:

1. Backoff exponencial comenzando con 1 segundo
2. Jitter aleatorio (±20%) para evitar reconexiones sincronizadas 
3. Máximo de 5 intentos antes de notificar al usuario

Ejemplo (JavaScript):
```javascript
const reconnectWithBackoff = async (maxRetries = 5) => {
  let retries = 0;
  while (retries < maxRetries) {
    try {
      await connectWebSocket();
      break; // Conexión exitosa
    } catch (error) {
      retries++;
      
      // Backoff exponencial con jitter
      const baseWait = Math.min(1000 * Math.pow(2, retries), 30000);
      const jitter = baseWait * 0.2 * (Math.random() - 0.5);
      const waitTime = baseWait + jitter;
      
      console.log(`Intento ${retries}/${maxRetries} después de ${waitTime}ms`);
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
  }
  
  if (retries >= maxRetries) {
    notifyUser("No se pudo restablecer la conexión");
  }
};
```

### 5.2 Sincronización de Estado

Tras una reconexión exitosa, el cliente debe enviar un mensaje domain/action para sincronizar su estado:

1. Enviar mensaje `session.sync` con último `correlation_id` conocido
2. El servidor responderá con el estado actual y los mensajes pendientes
3. Sincronizar automáticamente el estado local con el del servidor

Formato del mensaje de sincronización:
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "session",
    "action": "sync"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    "session_id": "uuid-v4",
    "last_message_id": "uuid-v4",
    "client_state": {
      "last_event_timestamp": "ISO-8601",
      "active_workflows": ["uuid-v4", "uuid-v4"]
    }
  }
}
```

Ejemplo de sincronización (JavaScript):
```javascript
const syncStateAfterReconnect = (websocket, sessionId, lastKnownMessageId) => {
  const syncMessage = {
    message_id: generateUUID(),
    correlation_id: generateUUID(),
    type: {
      domain: "session",
      action: "sync"
    },
    schema_version: "1.0",
    created_at: new Date().toISOString(),
    data: {
      session_id: sessionId,
      last_message_id: lastKnownMessageId,
      client_state: {
        last_event_timestamp: new Date().toISOString(),
        active_workflows: getActiveWorkflowIds()
      }
    }
  };
  
  websocket.send(JSON.stringify(syncMessage));
  
  // El servidor enviará eventos session.state_update con los mensajes pendientes
};
```
