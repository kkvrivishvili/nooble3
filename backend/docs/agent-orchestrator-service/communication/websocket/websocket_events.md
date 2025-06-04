# Catálogo de Eventos WebSocket

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Catálogo de Eventos WebSocket](#catálogo-de-eventos-websocket)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Eventos de Servidor a Cliente](#2-eventos-de-servidor-a-cliente)
    - [2.1 Evento: content_stream](#21-evento-content_stream)
    - [2.2 Evento: message_completed](#22-evento-message_completed)
    - [2.3 Evento: message_status_update](#23-evento-message_status_update)
    - [2.4 Evento: tool_call](#24-evento-tool_call)
    - [2.5 Evento: tool_response](#25-evento-tool_response)
    - [2.6 Evento: error](#26-evento-error)
    - [2.7 Evento: task_status_update](#27-evento-task_status_update)
  - [3. Eventos de Cliente a Servidor](#3-eventos-de-cliente-a-servidor)
    - [3.1 Evento: cancel_task](#31-evento-cancel_task)
    - [3.2 Evento: ping](#32-evento-ping)
    - [3.3 Evento: tool_response](#33-evento-tool_response)
  - [4. Gestión de Estados y Reconexión](#4-gestión-de-estados-y-reconexión)
    - [4.1 Reconexión del Cliente](#41-reconexión-del-cliente)
    - [4.2 Sincronización de Estado](#42-sincronización-de-estado)

## 1. Introducción

Este documento define el catálogo completo de eventos WebSocket utilizados en la comunicación en tiempo real entre el Agent Orchestrator Service y los clientes frontend. Sirve como referencia centralizada para estandarizar los nombres y formatos de todos los eventos, eliminando inconsistencias entre servicios.

## 2. Eventos de Servidor a Cliente

### 2.1 Evento: content_stream

Evento para transmisión en tiempo real (streaming) del contenido generado.

**Origen:** Agent Execution Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "content_stream",
  "message_id": "uuid-v4",
  "chunk": "fragmento de texto",
  "is_final": false,
  "timestamp": "ISO-8601"
}
```

### 2.2 Evento: message_completed

Evento emitido cuando un mensaje ha sido completamente procesado.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "message_completed",
  "message_id": "uuid-v4",
  "response": {
    "content": "Contenido completo de la respuesta",
    "type": "text",
    "sources": [
      {
        "title": "Documento A",
        "url": "https://url-to-doc.com",
        "snippet": "fragmento relevante..."
      }
    ],
    "metadata": {}
  },
  "timestamp": "ISO-8601"
}
```

### 2.3 Evento: message_status_update

Evento para actualizar el estado de un mensaje.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "message_status_update",
  "message_id": "uuid-v4",
  "status": "processing|completed|failed",
  "timestamp": "ISO-8601"
}
```

### 2.4 Evento: tool_call

Evento para solicitar al cliente la ejecución de una herramienta.

**Origen:** Agent Execution Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "tool_call",
  "tool_call_id": "uuid-v4",
  "message_id": "uuid-v4",
  "tool_id": "nombre-herramienta",
  "params": {
    "param1": "valor1",
    "param2": "valor2"
  },
  "timestamp": "ISO-8601"
}
```

### 2.5 Evento: tool_response

Evento que transmite el resultado de una ejecución de herramienta.

**Origen:** Tool Registry Service (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "tool_response",
  "tool_call_id": "uuid-v4",
  "message_id": "uuid-v4",
  "result": {
    "status": "success|error",
    "data": {},
    "error_message": "descripción del error (opcional)"
  },
  "timestamp": "ISO-8601"
}
```

### 2.6 Evento: error

Evento para notificar errores durante el procesamiento.

**Origen:** Cualquier servicio (vía Orchestrator)  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "error",
  "message_id": "uuid-v4", // Opcional
  "task_id": "uuid-v4", // Opcional
  "code": "error_code",
  "message": "Descripción del error",
  "details": {},
  "timestamp": "ISO-8601"
}
```

### 2.7 Evento: task_status_update

Evento para actualizar el estado de una tarea.

**Origen:** Agent Orchestrator  
**Destino:** Cliente Frontend

**Formato:**
```json
{
  "event": "task_status_update",
  "global_task_id": "uuid-v4",
  "status": "queued|processing|completed|failed",
  "progress": 0.75,
  "message": "Procesando documentos...",
  "timestamp": "ISO-8601"
}
```

## 3. Eventos de Cliente a Servidor

### 3.1 Evento: cancel_task

Evento para cancelar una tarea en curso.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "action": "cancel_task",
  "global_task_id": "uuid-v4"
}
```

### 3.2 Evento: ping

Evento para mantener la conexión activa.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "action": "ping",
  "client_timestamp": "ISO-8601"
}
```

### 3.3 Evento: tool_response

Evento para enviar la respuesta de una herramienta ejecutada en el cliente.

**Origen:** Cliente Frontend  
**Destino:** Agent Orchestrator

**Formato:**
```json
{
  "action": "tool_response",
  "tool_call_id": "uuid-v4",
  "result": {
    "status": "success|error",
    "data": {},
    "error_message": "descripción del error (opcional)"
  }
}
```

## 4. Gestión de Estados y Reconexión

### 4.1 Reconexión del Cliente

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

### 4.2 Sincronización de Estado

Tras una reconexión exitosa, el cliente debe:

1. Enviar su último `message_id` conocido
2. El servidor responderá con el estado actual y los mensajes pendientes
3. Sincronizar automáticamente el estado local con el del servidor

Ejemplo de sincronización:
```javascript
const syncStateAfterReconnect = (websocket, lastKnownMessageId) => {
  websocket.send(JSON.stringify({
    action: "sync_state",
    last_message_id: lastKnownMessageId
  }));
  
  // El servidor enviará eventos de sincronización
  // que el cliente procesará normalmente
};
```
