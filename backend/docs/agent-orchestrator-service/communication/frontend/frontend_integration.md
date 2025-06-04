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

## 4. Conexión WebSocket con Domain/Action

### 4.1 Establecer Conexión WebSocket

```
WebSocket URL: wss://api.domain.com/ws/v1/{domain}/{session_id}
```

**Ejemplos de URLs de conexión:**
- Chat: `wss://api.domain.com/ws/v1/chat/{session_id}`
- Workflow: `wss://api.domain.com/ws/v1/workflow/{workflow_id}`

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Sec-WebSocket-Protocol: domain-action`

### 4.2 Mensajes del Servidor al Cliente

#### Actualización de estado de chat (chat.status)

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", 
  "type": {
    "domain": "chat",
    "action": "status"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "chat_message_id": "uuid-v4",
    "session_id": "uuid-v4",
    "status": "processing|completed|failed",
    "progress": 0.45,
    "updated_at": "ISO-8601"
  }
}
```

#### Respuesta de mensaje completada (chat.response)

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "content": "Contenido completo de la respuesta",
    "content_type": "text",
    "role": "assistant",
    "sources": [
      {
        "title": "Documento A",
        "url": "https://url-to-doc.com",
        "snippet": "fragmento relevante..."
      }
    ],
    "metadata": {
      "processing_time_ms": 2350,
      "model_used": "gpt-4"
    }
  }
}
```

#### Actualización de estado de workflow (workflow.status)

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", 
  "type": {
    "domain": "workflow",
    "action": "status"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "workflow_id": "uuid-v4",
    "status": "queued|processing|completed|failed",
    "progress": 0.75,
    "current_step": "processing_documents",
    "message": "Procesando documentos...",
    "steps_completed": 3,
    "steps_total": 5,
    "updated_at": "ISO-8601"
  }
}
```

#### Fragmento de streaming (chat.stream)

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
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "response_message_id": "uuid-v4",
    "chunk": {
      "content": "fragmento de texto",
      "sequence": 3,
      "is_final": false
    }
  }
}
```

#### Ejecutar herramienta en cliente (tool.execute)

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
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "uuid-v4",
    "parent_message_id": "uuid-v4", 
    "tool_call_id": "uuid-v4",
    "tool": {
      "name": "show_calendar",
      "description": "Mostrar calendario del usuario",
      "parameters": {
        "date": "2025-06-15",
        "view": "week"
      },
      "timeout_ms": 30000
    }
  }
}
```

### 4.3 Mensajes del Cliente al Servidor

#### Ping para mantener conexión (system.ping)

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

#### Cancelar workflow (workflow.cancel)

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", // Relacionado con el workflow a cancelar
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

#### Resultado de ejecución de herramienta (tool.result)

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

#### Sincronizar estado de sesión (session.sync)

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

## 5. Manejo de Errores con Domain/Action

### 5.1 Formato de Error Estándar

Los errores mantienen la estructura domain/action con tipo `system.error` o `{domain}.error`:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", // Si está relacionado con una solicitud anterior
  "type": {
    "domain": "system", // o el dominio específico donde ocurrió el error
    "action": "error"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "code": "ERROR_CODE",
    "message": "Mensaje descriptivo del error",
    "details": {
      "field": "campo_con_error",
      "reason": "razón detallada",
      "suggestion": "sugerencia para resolver"
    },
    "request_id": "uuid-v4",
    "transaction_id": "uuid-v4"
  },
  "status": {
    "code": 400, // Código HTTP correspondiente
    "message": "Bad Request"
  }
}
```

### 5.2 Clasificación de Errores por Dominio

Los errores se clasifican según el dominio donde ocurren:

- **system.error**: Errores generales del sistema (autenticación, autorización, formato de mensaje)
- **session.error**: Errores relacionados con la gestión de sesiones
- **chat.error**: Errores específicos de procesamiento de mensajes
- **workflow.error**: Errores en el procesamiento de workflows o tareas por lotes
- **tool.error**: Errores en la ejecución o definición de herramientas
- **agent.error**: Errores específicos del comportamiento del agente

### 5.3 Códigos de Error Estandarizados

Cada dominio implementa sus propios códigos de error con prefijo del dominio:

**Errores de Sistema:**
- `SYSTEM.AUTH_FAILED`: Error en autenticación
- `SYSTEM.AUTH_EXPIRED`: Token expirado
- `SYSTEM.PERMISSION_DENIED`: Sin permisos para la operación
- `SYSTEM.RATE_LIMITED`: Límite de tasa excedido
- `SYSTEM.INVALID_MESSAGE`: Formato de mensaje inválido
- `SYSTEM.SERVICE_UNAVAILABLE`: Servicio no disponible

**Errores de Sesión:**
- `SESSION.NOT_FOUND`: Sesión no encontrada
- `SESSION.EXPIRED`: Sesión expirada
- `SESSION.LIMIT_EXCEEDED`: Límite de sesiones excedido

**Errores de Chat:**
- `CHAT.MESSAGE_TOO_LARGE`: Mensaje excede límite de tamaño
- `CHAT.PROCESSING_FAILED`: Error en procesamiento del mensaje
- `CHAT.CONTENT_POLICY_VIOLATION`: Contenido viola políticas

**Errores de Workflow:**
- `WORKFLOW.INVALID_OPERATION`: Operación no válida para este workflow
- `WORKFLOW.EXECUTION_FAILED`: Error en la ejecución del workflow
- `WORKFLOW.TIMEOUT`: Timeout en la operación del workflow

### 5.4 Manejo de Errores en Clientes

Los clientes deben implementar estrategias para cada tipo de error:

1. **Errores Recuperables vs. No Recuperables**:
   - Recuperables: Reintentar con backoff (SYSTEM.RATE_LIMITED, SYSTEM.SERVICE_UNAVAILABLE)
   - No Recuperables: Notificar al usuario (CHAT.CONTENT_POLICY_VIOLATION)

2. **Acciones según el dominio**:
   - Errores de autenticación: Redirigir a inicio de sesión
   - Errores de sesión: Intentar recuperar/crear nueva sesión
   - Errores de procesamiento: Mostrar mensaje de error apropiado

3. **Correlación de errores**:
   - Utilizar `correlation_id` para asociar errores con sus solicitudes originales
   - Agrupar errores relacionados para debugging

## 6. Buenas Prácticas para el Frontend con Domain/Action

### 6.1 Gestión de la Conexión WebSocket

1. **Reconexión Automática**:
   - Implementar backoff exponencial para reconexiones (comenzando en 1 segundo)
   - Máximo 5 intentos antes de notificar al usuario
   - Utilizar el mensaje `session.sync` al reconectar para recuperar estado

2. **Mantenimiento de Conexión**:
   - Implementar ping periódico con formato domain/action (`system.ping`)
   - Monitorizar y registrar latencia para optimizar rendimiento

### 6.2 Gestión de Estado y Mensajes

1. **Estado de Sesión**:
   - Mantener estado local incluyendo:
     - `session_id` activo
     - Lista de `message_id` con sus `correlation_id` correspondientes
     - `workflow_id` activos
   - Reconciliar estado automáticamente tras reconexión usando `session.sync`

2. **Almacenamiento de Mensajes**:
   - Implementar cache local con esquema compatible con domain/action
   - Guardar mensajes completos con todos sus metadatos (no solo contenido)
   - Usar storage persistente (IndexedDB) estructurado por dominios

### 6.3 Correlación y Trazabilidad

1. **Generación de IDs**:
   - Generar `message_id` y `correlation_id` UUID v4 en el cliente para cada solicitud
   - Almacenar mapeo de correlación para facilitar matching de respuestas

2. **Trazabilidad End-to-End**:
   - Mantener registro de tiempo para cada mensaje enviado/recibido
   - Implementar logs estructurados con campos domain/action para debugging
   - Calcular y monitorizar métricas de rendimiento por dominio/acción

### 6.4 Manejo de Tareas Asíncronas

1. **Indicadores de Progreso**:
   - Mostrar progreso detallado basado en mensajes `workflow.status` y `chat.status` 
   - Implementar timeout adaptativo según tipo de operación
   - Permitir cancelación explícita de cualquier workflow en curso

2. **Interacción Fluida**:
   - Separar operaciones por dominio para evitar bloqueos de UI
   - Implementar caché predictivo para mejorar la experiencia

### 6.5 Seguridad

1. **Autenticación**:
   - Implementar renovación transparente de tokens JWT
   - Mantener encabezados de autenticación consistentes entre REST y WebSocket

2. **Aislamiento de Datos**:
   - Separar almacenamiento por tenant_id
   - Validar tenant_id en cada mensaje recibido
   - Nunca exponer datos de tenant o headers de autenticación en cliente

### 6.6 Compatibilidad Multi-dispositivo

1. **Sincronización de Estado**:
   - Implementar reconciliación basada en timestamps para uso en múltiples dispositivos
   - Utilizar `session.sync` para resolver conflictos de estado
   - Mantener caché local por dispositivo con política de invalidación

## 7. Ejemplos de Código con Domain/Action

### 7.1 Conexión WebSocket con Domain/Action (JavaScript)

```javascript
class DomainActionWebSocket {
  constructor(domain, sessionId, authToken, tenantId) {
    this.url = `wss://api.domain.com/ws/v1/${domain}/${sessionId}`;
    this.authToken = authToken;
    this.tenantId = tenantId;
    this.domain = domain;
    this.sessionId = sessionId;
    this.correlationMap = new Map();
    this.messageHandlers = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    
    // Registrar handlers por tipo de mensaje
    this.registerDefaultHandlers();
  }
  
  connect() {
    this.ws = new WebSocket(this.url, ['domain-action']);
    
    this.ws.onopen = () => {
      console.log(`Conexión establecida a ${this.domain}/${this.sessionId}`);
      this.reconnectAttempts = 0;
      
      // Enviar sync inmediatamente después de conectar
      this.syncSession();
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
    
    this.ws.onclose = (event) => {
      if (event.code !== 1000) {
        this.handleDisconnect();
      }
    };
    
    this.ws.onerror = (error) => {
      console.error('Error en conexión WebSocket:', error);
    };
    
    // Configurar ping periódico
    this.setupPing();
  }
  
  registerDefaultHandlers() {
    // Handler para mensajes de chat.response
    this.registerHandler('chat.response', (message) => {
      const { session_id, content, sources, metadata } = message.data;
      // Actualizar UI con respuesta completa
      this.events.emit('responseReceived', { content, sources, metadata });
    });
    
    // Handler para actualizaciones de estado de chat
    this.registerHandler('chat.status', (message) => {
      const { status, progress } = message.data;
      this.events.emit('statusUpdate', { status, progress });
    });
    
    // Handler para streaming de contenido
    this.registerHandler('chat.stream', (message) => {
      const { chunk } = message.data;
      this.events.emit('streamChunk', chunk);
    });
    
    // Handler para herramientas
    this.registerHandler('tool.execute', (message) => {
      const { tool_call_id, tool } = message.data;
      this.events.emit('toolRequest', { tool_call_id, tool });
    });
    
    // Handler para errores
    this.registerHandler('system.error', (message) => {
      const { code, message: errorMessage } = message.data;
      this.events.emit('error', { code, message: errorMessage });
    });
  }
  
  registerHandler(type, handler) {
    const [domain, action] = type.split('.');
    const key = `${domain}.${action}`;
    this.messageHandlers.set(key, handler);
  }
  
  handleMessage(message) {
    // Extraer domain y action del mensaje
    const domain = message.type.domain;
    const action = message.type.action;
    const handlerKey = `${domain}.${action}`;
    
    // Verificar correlation_id para emparejar con solicitudes pendientes
    if (message.correlation_id && this.correlationMap.has(message.correlation_id)) {
      const pendingRequest = this.correlationMap.get(message.correlation_id);
      pendingRequest.resolve(message);
      this.correlationMap.delete(message.correlation_id);
    }
    
    // Ejecutar handler específico si existe
    if (this.messageHandlers.has(handlerKey)) {
      const handler = this.messageHandlers.get(handlerKey);
      handler(message);
    } else {
      console.warn(`No hay handler registrado para ${handlerKey}`);
    }
  }
  
  syncSession() {
    const lastMessageId = localStorage.getItem(`${this.domain}.${this.sessionId}.lastMessageId`);
    
    const syncMessage = {
      message_id: this.generateUUID(),
      correlation_id: this.generateUUID(),
      type: {
        domain: "session",
        action: "sync"
      },
      schema_version: "1.0",
      created_at: new Date().toISOString(),
      data: {
        session_id: this.sessionId,
        last_message_id: lastMessageId || null,
        client_state: {
          last_event_timestamp: new Date().toISOString(),
          active_workflows: JSON.parse(localStorage.getItem(`${this.domain}.${this.sessionId}.workflows`) || '[]')
        }
      }
    };
    
    this.send(syncMessage);
  }
  
  setupPing() {
    this.pingInterval = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        const pingMessage = {
          message_id: this.generateUUID(),
          type: {
            domain: "system",
            action: "ping"
          },
          schema_version: "1.0",
          created_at: new Date().toISOString(),
          data: {
            client_timestamp: new Date().toISOString(),
            client_info: {
              version: "1.0.0",
              platform: "web"
            }
          }
        };
        
        this.send(pingMessage);
      }
    }, 30000);
  }
  
  handleDisconnect() {
    // Limpiar intervalo de ping al desconectar
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
    }
    
    // Implementar backoff exponencial
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      this.reconnectAttempts++;
      
      console.log(`Intentando reconectar en ${delay}ms (intento ${this.reconnectAttempts})`);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('Máximo número de intentos de reconexión alcanzado');
      this.events.emit('disconnected', { permanent: true });
    }
  }
  
  send(message) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
      return true;
    }
    return false;
  }
  
  async sendWithResponse(message, timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      // Guardar referencia a esta promesa para resolverla cuando llegue la respuesta
      this.correlationMap.set(message.correlation_id, { resolve, reject });
      
      // Enviar mensaje
      if (!this.send(message)) {
        this.correlationMap.delete(message.correlation_id);
        reject(new Error('WebSocket no está conectado'));
        return;
      }
      
      // Configurar timeout
      setTimeout(() => {
        if (this.correlationMap.has(message.correlation_id)) {
          this.correlationMap.delete(message.correlation_id);
          reject(new Error('Timeout esperando respuesta'));
        }
      }, timeoutMs);
    });
  }
  
  generateUUID() {
    // Implementación UUID v4
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
  
  close() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
    }
    if (this.ws) {
      this.ws.close(1000);
    }
  }
}
```

### 7.2 Cliente API REST con Domain/Action

```javascript
class DomainActionApiClient {
  constructor(baseUrl, authToken, tenantId) {
    this.baseUrl = baseUrl;
    this.authToken = authToken;
    this.tenantId = tenantId;
  }
  
  async request(domain, action, data = {}, method = 'POST', pathParams = []) {
    const endpoint = this._buildEndpoint(domain, action, pathParams);
    const messageId = this._generateUUID();
    const correlationId = this._generateUUID();
    
    const headers = {
      'Authorization': `Bearer ${this.authToken}`,
      'X-Tenant-ID': this.tenantId,
      'X-Message-ID': messageId,
      'X-Correlation-ID': correlationId,
      'Content-Type': 'application/json'
    };
    
    const body = method !== 'GET' ? {
      message_id: messageId,
      correlation_id: correlationId,
      type: {
        domain,
        action
      },
      schema_version: "1.0",
      created_at: new Date().toISOString(),
      tenant_id: this.tenantId,
      source_service: "frontend",
      data
    } : null;
    
    try {
      const response = await fetch(endpoint, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
      });
      
      const responseData = await response.json();
      
      if (!response.ok) {
        throw {
          status: response.status,
          data: responseData,
          message: responseData.data?.message || 'Error desconocido'
        };
      }
      
      return responseData;
    } catch (error) {
      console.error(`Error en solicitud ${domain}.${action}:`, error);
      throw error;
    }
  }
  
  // Métodos para endpoints comúnes
  
  async createSession(userId, agentId, metadata = {}) {
    return this.request('session', 'create', { 
      user_id: userId,
      agent_id: agentId,
      metadata 
    });
  }
  
  async sendMessage(sessionId, content, contentType = 'text', metadata = {}) {
    return this.request('chat', 'message', {
      session_id: sessionId,
      content,
      content_type: contentType,
      metadata
    });
  }
  
  async getMessageHistory(sessionId, limit = 20, before = null) {
    const params = [sessionId];
    const queryParams = before ? `?limit=${limit}&before=${before}` : `?limit=${limit}`;
    return this.request('chat', `history${queryParams}`, {}, 'GET', params);
  }
  
  async cancelMessage(sessionId, messageId, reason = 'user_requested') {
    return this.request('chat', 'cancel', {
      session_id: sessionId,
      target_message_id: messageId,
      reason
    }, 'POST', [messageId]);
  }
  
  _buildEndpoint(domain, action, pathParams = []) {
    const path = pathParams.length > 0 ? `/${pathParams.join('/')}` : '';
    return `${this.baseUrl}/api/v1/${domain}.${action}${path}`;
  }
  
  _generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
}

// Ejemplo de uso
const apiClient = new DomainActionApiClient('https://api.domain.com', 'jwt-token', 'tenant-123');

// Crear sesión
apiClient.createSession('user-123', 'agent-456')
  .then(response => {
    const sessionId = response.data.session_id;
    console.log('Sesión creada:', sessionId);
    
    // Enviar mensaje
    return apiClient.sendMessage(sessionId, "Hola, ¿puedes ayudarme?");
  })
  .then(response => {
    console.log('Mensaje enviado, ID:', response.data.chat_message_id);
  })
  .catch(error => {
    console.error('Error:', error);
  });
```
