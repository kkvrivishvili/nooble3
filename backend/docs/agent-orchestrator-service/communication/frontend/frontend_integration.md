# Integración del Frontend con Agent Orchestrator Service

## Introducción

Este documento describe los detalles técnicos para la integración del frontend con el Agent Orchestrator Service, el cual actúa como punto de entrada único para todas las interacciones del cliente con el sistema de microservicios.

## Endpoints de API REST

### 1. Gestión de Sesiones

#### Crear nueva sesión

```
POST /api/sessions
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "user_id": "string",
  "agent_id": "string",
  "metadata": {
    "client_version": "string",
    "user_timezone": "string", 
    "additional_context": {}
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "session_id": "uuid-string",
  "created_at": "ISO-timestamp",
  "status": "active",
  "agent_id": "string",
  "websocket_url": "wss://api.domain.com/ws/sessions/{session_id}"
}
```

#### Obtener sesión existente

```
GET /api/sessions/{session_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "session_id": "uuid-string",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "status": "active|inactive|closed",
  "agent_id": "string",
  "messages_count": 24,
  "last_activity": "ISO-timestamp"
}
```

### 2. Envío de Mensajes

#### Enviar nuevo mensaje

```
POST /api/sessions/{session_id}/messages
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "message": "Texto del mensaje del usuario",
  "type": "text",
  "metadata": {
    "source": "chat|voice|email",
    "attachments": []
  }
}
```

**Respuesta exitosa (202 Accepted):**
```json
{
  "message_id": "uuid-string",
  "status": "processing",
  "global_task_id": "uuid-string",
  "estimated_time_seconds": 5
}
```

### 3. Procesamiento por Lotes

#### Iniciar procesamiento por lotes

```
POST /api/batch
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "operation_type": "embedding|ingestion|analysis",
  "items": [
    {
      "id": "item-1",
      "content": "contenido a procesar"
    },
    {
      "id": "item-2",
      "content": "otro contenido"
    }
  ],
  "config": {
    "priority": 1,
    "callback_url": "https://optional-callback.com"
  }
}
```

**Respuesta exitosa (202 Accepted):**
```json
{
  "batch_id": "uuid-string",
  "status": "queued",
  "global_task_id": "uuid-string",
  "items_count": 2
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
