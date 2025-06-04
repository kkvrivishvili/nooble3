# Guía de Integración Frontend para Agent Orchestrator Service con Domain/Action

*Versión: 2.0.0*  
*Última actualización: 2025-06-10*  
*Responsable: Equipo Nooble Frontend*

## 1. Introducción

Este documento proporciona una guía detallada para integrar aplicaciones frontend con el Agent Orchestrator Service utilizando el estándar global domain/action. El estándar domain/action estructura todas las comunicaciones (REST, WebSocket, mensajería asíncrona) en un formato consistente y trazable, facilitando el desarrollo, depuración y evolución de las integraciones frontend-backend.

## 2. Estructura Base Domain/Action

Todas las comunicaciones siguen esta estructura común:

```json
{
  "message_id": "uuid-v4",           // ID único del mensaje
  "correlation_id": "uuid-v4",      // Para correlacionar solicitudes/respuestas
  "type": {                        // Clasificación del mensaje
    "domain": "session|chat|workflow|agent|tool|system",
    "action": "create|update|message|execute|etc"
  },
  "schema_version": "1.0",         // Versión del esquema
  "created_at": "ISO-8601",        // Timestamp de creación
  "tenant_id": "tenant-uuid",      // ID de tenant (multi-tenancy)
  "source_service": "frontend",    // Servicio de origen
  "data": {                        // Carga útil específica del message
    // Contenido variable según domain.action
  }
}
```

### 2.1 Dominios y Acciones Principales

| Dominio | Acciones Comunes | Descripción |
|---------|-----------------|-------------|
| `session` | create, get, update, close | Gestión del ciclo de vida de sesiones |
| `chat` | message, history, stream | Comunicación conversacional |
| `workflow` | execute, status, cancel | Ejecución de tareas y workflows |
| `agent` | list, get, assign | Gestión de agentes |
| `tool` | execute, result | Ejecución de herramientas |
| `system` | error, ping, status | Operaciones de sistema |

## 3. Endpoints API REST con Domain/Action

### 3.1 Dominio: Session

#### Crear nueva sesión (session.create)

```
POST /api/v1/session.create
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "session",
    "action": "create"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "frontend",
  "data": {
    "user_id": "string",
    "agent_id": "string",
    "metadata": {
      "client_version": "string",
      "user_timezone": "string", 
      "additional_context": {}
    }
  }
}
```

**Respuesta exitosa (201 Created):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "session",
    "action": "created"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "created_at": "ISO-8601",
    "status": "active",
    "agent_id": "string",
    "websocket_url": "wss://api.domain.com/ws/v1/chat/{session_id}"
  },
  "status": {
    "code": 201,
    "message": "Created"
  }
}
```

#### Obtener sesión existente (session.get)

```
GET /api/v1/session.get/{session_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "session",
    "action": "get_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "created_at": "ISO-8601",
    "updated_at": "ISO-8601",
    "status": "active|inactive|closed",
    "agent_id": "string",
    "messages_count": 24,
    "last_activity": "ISO-8601"
  },
  "status": {
    "code": 200,
    "message": "OK"
  }
}
```

#### Listar sesiones (session.list)

```
GET /api/v1/session.list
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`

**Parámetros de consulta opcionales:**
- `status` - Filtrar por estado (active, inactive, closed)
- `limit` - Cantidad máxima de resultados (default: 20)
- `offset` - Desplazamiento para paginación

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "session",
    "action": "list_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "items": [
      {
        "session_id": "uuid-v4",
        "created_at": "ISO-8601",
        "status": "active",
        "agent_id": "string",
        "messages_count": 24,
        "last_activity": "ISO-8601"
      },
      // Más sesiones...
    ]
  },
  "status": {
    "code": 200,
    "message": "OK"
  },
  "meta": {
    "pagination": {
      "limit": 20,
      "offset": 0,
      "total": 45
    }
  }
}
```

### 3.2 Dominio: Chat

#### Enviar nuevo mensaje (chat.message)

```
POST /api/v1/chat.message
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "message"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "frontend",
  "data": {
    "session_id": "uuid-v4",
    "content": "Texto del mensaje del usuario",
    "content_type": "text",
    "metadata": {
      "source": "chat|voice|email",
      "attachments": [],
      "user_info": {}
    }
  }
}
```

**Respuesta exitosa (202 Accepted):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", // Mismo ID de la solicitud original
  "type": {
    "domain": "chat",
    "action": "message_accepted"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "chat_message_id": "uuid-v4",
    "session_id": "uuid-v4",
    "status": "processing",
    "workflow_id": "uuid-v4",
    "estimated_time_seconds": 5
  },
  "status": {
    "code": 202,
    "message": "Accepted"
  }
}
```

#### Obtener historial de mensajes (chat.history)

```
GET /api/v1/chat.history/{session_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`

**Parámetros de consulta opcionales:**
- `limit` - Cantidad máxima de mensajes (default: 20)
- `before` - Timestamp para filtrar mensajes antes de esta fecha
- `after` - Timestamp para filtrar mensajes después de esta fecha

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "history_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "messages": [
      {
        "message_id": "uuid-v4",
        "content": "Texto del mensaje",
        "content_type": "text",
        "role": "user|assistant",
        "created_at": "ISO-8601",
        "metadata": {}
      },
      // Más mensajes...
    ]
  },
  "status": {
    "code": 200,
    "message": "OK"
  },
  "meta": {
    "pagination": {
      "has_more": true,
      "next_cursor": "cursor-hash"
    }
  }
}
```

#### Cancelar procesamiento de mensaje (chat.cancel)

```
POST /api/v1/chat.cancel/{message_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "cancel"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "frontend",
  "data": {
    "session_id": "uuid-v4",
    "target_message_id": "uuid-v4",
    "reason": "user_requested"
  }
}
```

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "cancel_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "target_message_id": "uuid-v4",
    "cancelled": true
  },
  "status": {
    "code": 200,
    "message": "OK"
  }
}
```

### 3.3 Dominio: Workflow

#### Iniciar procesamiento por lotes (workflow.batch)

```
POST /api/v1/workflow.batch
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "batch"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "frontend",
  "data": {
    "operation_type": "embedding|ingestion|analysis",
    "items": [
      {
        "id": "item-1",
        "content": "contenido a procesar",
        "metadata": {}
      },
      {
        "id": "item-2",
        "content": "otro contenido",
        "metadata": {}
      }
    ],
    "config": {
      "priority": 1,
      "callback_url": "https://optional-callback.com",
      "processing_options": {}
    }
  }
}
```

**Respuesta exitosa (202 Accepted):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "batch_accepted"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "workflow_id": "uuid-v4",
    "batch_id": "uuid-v4",
    "status": "queued",
    "items_count": 2,
    "estimated_completion_time": "ISO-8601"
  },
  "status": {
    "code": 202,
    "message": "Accepted"
  }
}
```

#### Verificar estado de workflow (workflow.status)

```
GET /api/v1/workflow.status/{workflow_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "status_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "workflow_id": "uuid-v4",
    "status": "queued|processing|completed|failed|cancelled",
    "progress": 0.75,
    "current_step": "processing_images",
    "steps_total": 5,
    "steps_completed": 3,
    "started_at": "ISO-8601",
    "updated_at": "ISO-8601",
    "estimated_completion_time": "ISO-8601"
  },
  "status": {
    "code": 200,
    "message": "OK"
  }
}
```

#### Obtener resultados de workflow (workflow.results)

```
GET /api/v1/workflow.results/{workflow_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `X-Message-ID: {message_id}`
- `X-Correlation-ID: {correlation_id}`

**Respuesta exitosa (200 OK):**
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "results_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "workflow_id": "uuid-v4",
    "status": "completed",
    "results": [
      {
        "item_id": "item-1",
        "status": "success",
        "output": {},
        "processing_time_ms": 1250
      },
      {
        "item_id": "item-2",
        "status": "error",
        "error": {
          "code": "PROCESSING_ERROR",
          "message": "Error al procesar contenido"
        },
        "processing_time_ms": 850
      }
    ],
    "summary": {
      "total_items": 2,
      "successful": 1,
      "failed": 1,
      "total_processing_time_ms": 2100
    }
  },
  "status": {
    "code": 200,
    "message": "OK"
  }
}
```

## Conexión WebSocket para Actualizaciones en Tiempo Real

### 1. Conexión al WebSocket

```
WebSocket URL: wss://api.domain.com/ws/sessions/{session_id}
```

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

### 2. Mensajes del WebSocket al Cliente

#### Actualización de estado de mensaje

```json
{
  "event": "message_status_update",
  "message_id": "uuid-string",
  "status": "processing|completed|failed",
  "timestamp": "ISO-timestamp"
}
```

#### Mensaje completado

```json
{
  "event": "message_completed",
  "message_id": "uuid-string",
  "response": {
    "content": "Contenido de la respuesta",
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
  "timestamp": "ISO-timestamp"
}
```

#### Actualización de estado de tarea

```json
{
  "event": "task_status_update",
  "global_task_id": "uuid-string",
  "status": "queued|processing|completed|failed",
  "progress": 0.75,
  "message": "Procesando documentos...",
  "timestamp": "ISO-timestamp"
}
```

#### Transmisión de contenido en tiempo real (streaming)

```json
{
  "event": "content_stream",
  "message_id": "uuid-string",
  "chunk": "fragmento de texto",
  "is_final": false,
  "timestamp": "ISO-timestamp"
}
```

### 3. Mensajes del Cliente al WebSocket

#### Cancelar tarea en curso

```json
{
  "action": "cancel_task",
  "global_task_id": "uuid-string"
}
```

#### Ping para mantener conexión

```json
{
  "action": "ping",
  "client_timestamp": "ISO-timestamp"
}
```

## Manejo de Errores

### Formato de Error Estándar

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {},
    "request_id": "uuid-string"
  }
}
```

### Códigos de Estado HTTP

- `400 Bad Request`: Parámetros inválidos o formato incorrecto
- `401 Unauthorized`: Autenticación fallida (token inválido)
- `403 Forbidden`: Sin permiso para esta operación
- `404 Not Found`: Recurso no encontrado
- `429 Too Many Requests`: Rate limit excedido
- `500 Internal Server Error`: Error en el servidor
- `503 Service Unavailable`: Servicio temporalmente no disponible

### Códigos de Error Específicos

- `auth_error`: Error en autenticación
- `validation_error`: Datos inválidos
- `rate_limited`: Límite de tasa excedido
- `resource_not_found`: Recurso no existe
- `service_error`: Error interno del servicio

## Buenas Prácticas para el Frontend

1. **Reconexión Automática del WebSocket**:
   - Implementar backoff exponencial para reconexiones (comenzando en 1 segundo)
   - Máximo 5 intentos antes de notificar al usuario

2. **Manejo de Estado de Sesión**:
   - Mantener estado local de la sesión
   - Sincronizar periódicamente con backend

3. **Almacenamiento de Mensajes**:
   - Implementar cache local para historial de conversación
   - Usar storage persistente (IndexedDB) para sesiones frecuentes

4. **Tratamiento de Tareas de Larga Duración**:
   - Mostrar indicadores de progreso para operaciones largas
   - Permitir al usuario continuar interactuando durante procesamiento

5. **Seguridad**:
   - Almacenar tokens JWT de forma segura
   - Nunca incluir tenant_id en frontend no protegido
   - Renovar tokens antes de expiración

6. **Multi-dispositivo**:
   - Implementar reconciliación de estado para uso en múltiples dispositivos
   - Gestionar conflictos de edición simultánea

## Ejemplos de Código

### Conexión WebSocket (JavaScript)

```javascript
const connectWebSocket = (sessionId, authToken, tenantId) => {
  const ws = new WebSocket(`wss://api.domain.com/ws/sessions/${sessionId}`);
  
  // Configurar headers de autorización
  ws.onopen = () => {
    ws.send(JSON.stringify({
      action: "authenticate",
      token: authToken,
      tenant_id: tenantId
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
      case "message_completed":
        // Actualizar UI con la respuesta
        displayResponse(data.response);
        break;
        
      case "task_status_update":
        // Actualizar indicador de progreso
        updateProgressBar(data.progress, data.message);
        break;
        
      case "content_stream":
        // Añadir chunk al contenido actual
        appendStreamedContent(data.chunk);
        break;
    }
  };
  
  ws.onclose = (event) => {
    if (event.code !== 1000) {
      // Implementar reconexión con backoff
      reconnectWithBackoff();
    }
  };
  
  // Ping periódico para mantener conexión activa
  const pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: "ping",
        client_timestamp: new Date().toISOString()
      }));
    }
  }, 30000);
  
  return {
    socket: ws,
    close: () => {
      clearInterval(pingInterval);
      ws.close(1000);
    }
  };
};
```

### Envío de Mensaje (Fetch API)

```javascript
const sendMessage = async (sessionId, message, authToken, tenantId) => {
  try {
    const response = await fetch(`https://api.domain.com/api/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: message,
        type: 'text'
      })
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error sending message:', error);
    throw error;
  }
};
```
