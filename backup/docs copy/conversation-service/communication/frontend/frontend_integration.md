# Integración del Frontend con Conversation Service

## Introducción

Este documento describe la integración directa del frontend con el Conversation Service para operaciones relacionadas con la gestión de conversaciones, historial de mensajes y memoria contextual. Este acceso directo (sin pasar por el orquestador) está diseñado para optimizar operaciones CRUD de conversaciones y acceso al historial, mientras que las interacciones de chat activo siguen fluyendo a través del orquestador.

## Endpoints de API REST

### Gestión de Conversaciones

#### Listar conversaciones

```
GET /api/conversations
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 20)
- `offset`: Desplazamiento para paginación (default: 0)
- `agent_id`: Filtrar por ID de agente
- `user_id`: Filtrar por ID de usuario
- `status`: Filtrar por estado (`active`, `archived`)
- `from_date`: Filtrar desde fecha (ISO-timestamp)
- `to_date`: Filtrar hasta fecha (ISO-timestamp)

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "conversation_id": "uuid-string",
      "title": "Soporte técnico - Problema de red",
      "agent_id": "agent-uuid",
      "user_id": "user-uuid",
      "status": "active",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp",
      "message_count": 24,
      "summary": "Conversación sobre problemas de conectividad de red",
      "last_message_preview": "Voy a revisar tu router remotamente..."
    },
    // más conversaciones...
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

#### Crear conversación

```
POST /api/conversations
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "title": "Consulta sobre facturación",
  "agent_id": "agent-uuid",
  "user_id": "user-uuid",
  "initial_context": {
    "user_timezone": "America/New_York",
    "user_language": "es",
    "previous_interactions": 3
  },
  "metadata": {
    "source": "web",
    "priority": "normal",
    "tags": ["facturación", "consulta"]
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "conversation_id": "uuid-string",
  "title": "Consulta sobre facturación",
  "agent_id": "agent-uuid",
  "user_id": "user-uuid",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "message_count": 0
}
```

#### Obtener conversación

```
GET /api/conversations/{conversation_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "conversation_id": "uuid-string",
  "title": "Consulta sobre facturación",
  "agent_id": "agent-uuid",
  "user_id": "user-uuid",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "message_count": 12,
  "summary": "Discusión sobre factura de abril con cobros incorrectos",
  "metadata": {
    "source": "web",
    "priority": "normal",
    "tags": ["facturación", "consulta"]
  },
  "context": {
    "user_timezone": "America/New_York",
    "user_language": "es",
    "previous_interactions": 3,
    "detected_topics": ["facturación", "reembolso"]
  }
}
```

#### Actualizar conversación

```
PUT /api/conversations/{conversation_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "title": "Disputa de facturación - Abril 2025",
  "status": "active",
  "metadata": {
    "priority": "high",
    "tags": ["facturación", "disputa", "reembolso"]
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "conversation_id": "uuid-string",
  "title": "Disputa de facturación - Abril 2025",
  "status": "active",
  "updated_at": "ISO-timestamp",
  "metadata": {
    "priority": "high",
    "tags": ["facturación", "disputa", "reembolso"]
  }
}
```

#### Eliminar/Archivar conversación

```
DELETE /api/conversations/{conversation_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `hard_delete`: Boolean (default: false) - Si es true, elimina permanentemente; si es false, archiva

**Respuesta exitosa (204):**
No content

### Gestión de Mensajes

#### Obtener mensajes

```
GET /api/conversations/{conversation_id}/messages
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 50)
- `before_id`: Obtener mensajes anteriores a este ID
- `after_id`: Obtener mensajes posteriores a este ID
- `include_metadata`: Boolean para incluir metadata (default: false)

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "message_id": "uuid-string",
      "conversation_id": "conversation-uuid",
      "content": "Hola, tengo un problema con mi factura de abril",
      "role": "user",
      "created_at": "ISO-timestamp",
      "attachments": [],
      "metadata": {
        "client_timestamp": "ISO-timestamp",
        "client_device": "mobile"
      }
    },
    {
      "message_id": "uuid-string-2",
      "conversation_id": "conversation-uuid",
      "content": "Hola, siento escuchar eso. ¿Puede explicarme cuál es el problema específico con su factura?",
      "role": "assistant",
      "created_at": "ISO-timestamp",
      "attachments": [],
      "metadata": {
        "model": "gpt-4",
        "tokens_used": 42
      }
    },
    // más mensajes...
  ],
  "total": 12,
  "has_more": true,
  "next_cursor": "cursor-string"
}
```

#### Añadir mensaje (solo para históricos)

```
POST /api/conversations/{conversation_id}/messages
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "content": "Este es un mensaje histórico para registros",
  "role": "user",
  "timestamp": "ISO-timestamp",
  "metadata": {
    "source": "email",
    "imported_from": "ticket-system",
    "original_id": "ticket-123"
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "message_id": "uuid-string",
  "conversation_id": "conversation-uuid",
  "content": "Este es un mensaje histórico para registros",
  "role": "user",
  "created_at": "ISO-timestamp",
  "timestamp": "ISO-timestamp"
}
```

#### Borrar mensaje

```
DELETE /api/conversations/{conversation_id}/messages/{message_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (204):**
No content

### Gestión de Memoria y Contexto

#### Obtener contexto de conversación

```
GET /api/conversations/{conversation_id}/context
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "conversation_id": "uuid-string",
  "context_items": [
    {
      "key": "user_preference",
      "value": "No le gustan las llamadas telefónicas",
      "source": "agent_detected",
      "timestamp": "ISO-timestamp"
    },
    {
      "key": "previous_issue",
      "value": "Tuvo un problema similar en marzo",
      "source": "system_note",
      "timestamp": "ISO-timestamp"
    },
    {
      "key": "detected_sentiment",
      "value": "frustrated",
      "source": "analysis",
      "confidence": 0.87,
      "timestamp": "ISO-timestamp"
    }
  ],
  "vector_memory": {
    "size": 12,
    "last_updated": "ISO-timestamp"
  }
}
```

#### Agregar elemento de contexto

```
POST /api/conversations/{conversation_id}/context
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "key": "customer_status",
  "value": "premium",
  "source": "crm_sync",
  "ttl_seconds": 3600,
  "importance": "high"
}
```

**Respuesta exitosa (201):**
```json
{
  "key": "customer_status",
  "value": "premium",
  "source": "crm_sync",
  "timestamp": "ISO-timestamp",
  "expires_at": "ISO-timestamp"
}
```

#### Limpiar historia de conversación

```
POST /api/conversations/{conversation_id}/clear
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "retain_context": true,
  "retain_summary": true
}
```

**Respuesta exitosa (200):**
```json
{
  "conversation_id": "uuid-string",
  "cleared_messages": 15,
  "retained_context": true,
  "timestamp": "ISO-timestamp"
}
```

## Conexión WebSocket para Actualizaciones en Tiempo Real

```
WebSocket URL: wss://api.domain.com/api/conversations/ws
```

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

### Eventos del WebSocket

#### Nueva conversación creada

```json
{
  "event": "conversation_created",
  "conversation_id": "uuid-string",
  "title": "Nueva consulta",
  "agent_id": "agent-uuid",
  "timestamp": "ISO-timestamp"
}
```

#### Conversación actualizada

```json
{
  "event": "conversation_updated",
  "conversation_id": "uuid-string",
  "fields_changed": ["title", "status"],
  "timestamp": "ISO-timestamp"
}
```

#### Análisis de conversación completado

```json
{
  "event": "conversation_analysis_completed",
  "conversation_id": "uuid-string",
  "summary": "El cliente está preocupado por cargos duplicados en su factura",
  "detected_topics": ["facturación", "reembolso", "error"],
  "sentiment": "frustrated",
  "next_steps": ["verificar transacciones", "ofrecer reembolso"],
  "timestamp": "ISO-timestamp"
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

### Códigos de Error Específicos

- `conversation_not_found`: Conversación no existe
- `message_not_found`: Mensaje no existe
- `invalid_message_format`: Formato de mensaje inválido
- `permission_denied`: Sin permisos para esta conversación
- `context_key_limit`: Límite de elementos de contexto excedido

## Ejemplos de Código

### Cargar Historial de Mensajes (JavaScript)

```javascript
const loadConversationHistory = async (conversationId, authToken, tenantId) => {
  try {
    const response = await fetch(`https://api.domain.com/api/conversations/${conversationId}/messages`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId
      }
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error loading conversation history:', error);
    throw error;
  }
};
```

### Agregar Notas de Contexto (JavaScript)

```javascript
const addContextNote = async (conversationId, contextData, authToken, tenantId) => {
  try {
    const response = await fetch(`https://api.domain.com/api/conversations/${conversationId}/context`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(contextData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error adding context note:', error);
    throw error;
  }
};
```

### Escuchar Actualizaciones de Conversación (WebSocket)

```javascript
const listenToConversationUpdates = (authToken, tenantId) => {
  const ws = new WebSocket(`wss://api.domain.com/api/conversations/ws`);
  let reconnectAttempts = 0;
  
  ws.onopen = () => {
    reconnectAttempts = 0;
    ws.send(JSON.stringify({
      action: "authenticate",
      token: authToken,
      tenant_id: tenantId
    }));
    
    // Suscribirse a conversaciones específicas (opcional)
    ws.send(JSON.stringify({
      action: "subscribe",
      conversation_ids: ["uuid-1", "uuid-2"]
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
      case "conversation_created":
        // Actualizar lista de conversaciones
        addConversationToList(data);
        break;
      case "conversation_updated":
        // Actualizar detalles de conversación
        updateConversationDetails(data.conversation_id);
        break;
      case "conversation_analysis_completed":
        // Mostrar insights de la conversación
        displayConversationInsights(data);
        break;
    }
  };
  
  // Manejo de reconexión con backoff exponencial
  ws.onclose = (event) => {
    if (event.code !== 1000) {
      reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      
      setTimeout(() => {
        listenToConversationUpdates(authToken, tenantId);
      }, delay);
    }
  };
  
  return ws;
};
```

## Consideraciones por Tier de Servicio

| Tier | Limitaciones | Capacidades |
|------|-------------|-------------|
| Free | - Máximo 100 mensajes por conversación<br>- Retención de 30 días<br>- Máximo 10 elementos de contexto | - Contexto básico<br>- Sin análisis avanzado |
| Professional | - Máximo 1000 mensajes por conversación<br>- Retención de 90 días<br>- Máximo 50 elementos de contexto | - Análisis de sentimiento<br>- Resúmenes automáticos<br>- Detección de temas |
| Enterprise | - Mensajes ilimitados<br>- Retención configurable (hasta 7 años)<br>- Elementos de contexto ilimitados | - Análisis avanzado<br>- Memoria vectorial extendida<br>- Integración con sistemas externos |
