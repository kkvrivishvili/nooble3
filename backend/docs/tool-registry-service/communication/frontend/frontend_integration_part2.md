# Integración del Frontend con Tool Registry Service - Parte 2

## Endpoints de API REST Avanzados

### Validar herramienta

```
POST /api/tools/{tool_id}/validate
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "test_parameters": {
    "to": "test@example.com",
    "subject": "Test Email",
    "body": "This is a test email"
  },
  "environment": "sandbox",
  "validation_mode": "schema_only|full_execution"
}
```

**Respuesta exitosa (200):**
```json
{
  "tool_id": "email-tool",
  "validation_id": "uuid-string",
  "status": "success|failed|pending",
  "schema_validation": {
    "status": "valid",
    "issues": []
  },
  "execution_validation": {
    "status": "pending",
    "test_execution_id": "uuid-string"
  },
  "timestamp": "ISO-timestamp"
}
```

### Obtener resultado de validación

```
GET /api/tools/validations/{validation_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "validation_id": "uuid-string",
  "tool_id": "email-tool",
  "status": "completed",
  "schema_validation": {
    "status": "valid",
    "issues": []
  },
  "execution_validation": {
    "status": "success",
    "execution_time_ms": 347,
    "response": {
      "success": true,
      "message_id": "test-msg-123"
    }
  },
  "created_at": "ISO-timestamp",
  "completed_at": "ISO-timestamp"
}
```

### Actualizar configuración de herramienta

```
PUT /api/tools/{tool_id}/config
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "configuration": {
    "default_timeout": 8000,
    "rate_limit": {
      "requests_per_minute": 20,
      "requests_per_hour": 500
    }
  },
  "integration_config": {
    "endpoint": "https://api.example.com/email/v2",
    "auth_type": "oauth2",
    "credentials": {
      "client_id": "client-id-value"
    }
  },
  "status": "active"
}
```

**Respuesta exitosa (200):**
```json
{
  "tool_id": "email-tool",
  "updated_at": "ISO-timestamp",
  "updated_fields": ["configuration", "integration_config", "status"],
  "requires_validation": false
}
```

### Eliminar herramienta

```
DELETE /api/tools/{tool_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `force`: Boolean (default: false) - Si es true, elimina incluso herramientas en uso

**Respuesta exitosa (204):**
No content

**Respuesta de error (409) si la herramienta está en uso y `force=false`:**
```json
{
  "error": {
    "code": "tool_in_use",
    "message": "No se puede eliminar la herramienta porque está en uso por agentes activos",
    "details": {
      "agents_using_tool": [
        "agent-id-1",
        "agent-id-2"
      ]
    },
    "request_id": "uuid-string"
  }
}
```

### Asignación de herramientas a agentes

```
POST /api/tools/{tool_id}/assign
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "agent_ids": [
    "agent-id-1",
    "agent-id-2"
  ],
  "permissions": {
    "can_execute": true,
    "auto_suggest": true
  },
  "configuration_overrides": {
    "timeout": 15000
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "tool_id": "email-tool",
  "assigned_count": 2,
  "successful_assignments": [
    "agent-id-1",
    "agent-id-2"
  ],
  "failed_assignments": []
}
```

## Conexión WebSocket para Actualizaciones en Tiempo Real

```
WebSocket URL: wss://api.domain.com/api/tools/ws
```

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

### Eventos del WebSocket

#### Actualización de estado de herramienta

```json
{
  "event": "tool_status_updated",
  "tool_id": "email-tool",
  "previous_status": "draft",
  "new_status": "active",
  "timestamp": "ISO-timestamp"
}
```

#### Validación completada

```json
{
  "event": "tool_validation_completed",
  "validation_id": "uuid-string",
  "tool_id": "email-tool",
  "status": "success|failed",
  "issues": [
    {
      "severity": "error|warning",
      "field": "integration_config.endpoint",
      "message": "El endpoint no respondió correctamente durante la prueba"
    }
  ],
  "timestamp": "ISO-timestamp"
}
```

#### Ejecución de herramienta (solo admin)

```json
{
  "event": "tool_execution",
  "tool_id": "email-tool",
  "execution_id": "uuid-string",
  "agent_id": "agent-uuid",
  "status": "started|completed|failed",
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

- `tool_not_found`: Herramienta no existe
- `invalid_tool_schema`: Esquema de herramienta inválido
- `validation_failed`: Validación fallida
- `tier_restriction`: Herramienta no disponible en este tier
- `duplicate_tool_id`: ID de herramienta ya existe
- `integration_error`: Error con la integración externa
