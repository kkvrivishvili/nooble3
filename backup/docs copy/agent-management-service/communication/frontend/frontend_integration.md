# Integración del Frontend con Agent Management Service

## Introducción

Este documento describe la integración directa del frontend con el Agent Management Service para operaciones CRUD y administrativas relacionadas con la gestión del ciclo de vida de agentes. Este acceso directo (sin pasar por el orquestador) está diseñado para optimizar operaciones administrativas mientras se mantiene la simplicidad y el rendimiento.

## Endpoints de API REST

### Gestión de Agentes

#### Listar agentes

```
GET /api/agents
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 50)
- `offset`: Desplazamiento para paginación (default: 0)
- `status`: Filtrar por estado (`active`, `inactive`, `draft`)
- `search`: Buscar por nombre o descripción

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "id": "uuid-string",
      "name": "Customer Support Agent",
      "description": "Agente para soporte de clientes",
      "status": "active",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp",
      "version": 3,
      "is_template": false
    },
    // más agentes...
  ],
  "total": 24,
  "limit": 50,
  "offset": 0
}
```

#### Crear agente

```
POST /api/agents
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Marketing Assistant",
  "description": "Asistente para campañas de marketing",
  "system_prompt": "Eres un asistente especializado en marketing...",
  "tools": ["search", "calculator", "calendar"],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 10
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000
  },
  "metadata": {
    "created_by": "user-id",
    "department": "marketing",
    "tags": ["marketing", "assistant"]
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "id": "uuid-string",
  "name": "Marketing Assistant",
  "description": "Asistente para campañas de marketing",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "version": 1,
  "system_prompt": "Eres un asistente especializado en marketing...",
  "tools": ["search", "calculator", "calendar"],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 10
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000
  }
}
```

#### Obtener agente

```
GET /api/agents/{agent_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "id": "uuid-string",
  "name": "Marketing Assistant",
  "description": "Asistente para campañas de marketing",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "version": 1,
  "system_prompt": "Eres un asistente especializado en marketing...",
  "tools": ["search", "calculator", "calendar"],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 10
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000
  },
  "metadata": {
    "created_by": "user-id",
    "department": "marketing",
    "tags": ["marketing", "assistant"]
  }
}
```

#### Actualizar agente

```
PUT /api/agents/{agent_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Marketing Assistant Pro",
  "description": "Asistente avanzado para campañas de marketing",
  "system_prompt": "Eres un asistente especializado en marketing digital...",
  "tools": ["search", "calculator", "calendar", "seo_analyzer"],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 15
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.8,
    "max_tokens": 1500
  },
  "metadata": {
    "updated_by": "user-id",
    "department": "marketing",
    "tags": ["marketing", "assistant", "advanced"]
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "id": "uuid-string",
  "name": "Marketing Assistant Pro",
  "description": "Asistente avanzado para campañas de marketing",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "version": 2,
  "system_prompt": "Eres un asistente especializado en marketing digital...",
  "tools": ["search", "calculator", "calendar", "seo_analyzer"],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 15
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.8,
    "max_tokens": 1500
  }
}
```

#### Eliminar agente

```
DELETE /api/agents/{agent_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (204):**
No content

### Configuración y Gestión de Agentes

#### Obtener configuración de agente

```
GET /api/agents/{agent_id}/config
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "system_prompt": "Eres un asistente especializado en marketing...",
  "tools": [
    {
      "name": "search",
      "description": "Busca información en Internet",
      "parameters": {
        "query": {"type": "string", "required": true},
        "limit": {"type": "integer", "default": 5}
      }
    },
    // más herramientas...
  ],
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 10,
    "persistence": true
  },
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000,
    "timeout_ms": 30000
  },
  "rate_limits": {
    "requests_per_hour": 100,
    "tokens_per_day": 10000
  }
}
```

#### Actualizar estado de agente

```
PATCH /api/agents/{agent_id}/status
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "status": "inactive",
  "reason": "maintenance"
}
```

**Respuesta exitosa (200):**
```json
{
  "id": "uuid-string",
  "name": "Marketing Assistant",
  "status": "inactive",
  "updated_at": "ISO-timestamp"
}
```

#### Clonar agente

```
POST /api/agents/{agent_id}/clone
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Marketing Assistant Clone",
  "description": "Copia del asistente de marketing"
}
```

**Respuesta exitosa (201):**
```json
{
  "id": "new-uuid-string",
  "name": "Marketing Assistant Clone",
  "description": "Copia del asistente de marketing",
  "status": "draft",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "version": 1,
  "cloned_from": "original-agent-uuid"
}
```

### Gestión de Plantillas

#### Listar plantillas de agentes

```
GET /api/agent-templates
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "id": "template-uuid",
      "name": "Customer Support Template",
      "description": "Plantilla base para agentes de soporte",
      "category": "support",
      "created_at": "ISO-timestamp",
      "popularity": 95
    },
    // más plantillas...
  ],
  "total": 12,
  "limit": 50,
  "offset": 0
}
```

#### Crear agente desde plantilla

```
POST /api/agent-templates/{template_id}/create
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Mi Agente de Soporte",
  "description": "Agente de soporte personalizado",
  "customizations": {
    "system_prompt_suffix": "Además, especialízate en productos de hardware.",
    "tool_overrides": {
      "knowledge_base": "mi-base-conocimiento-id"
    }
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "id": "uuid-string",
  "name": "Mi Agente de Soporte",
  "description": "Agente de soporte personalizado",
  "status": "active",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "version": 1,
  "template_id": "template-uuid"
}
```

## Conexión WebSocket para Actualizaciones en Tiempo Real

```
WebSocket URL: wss://api.domain.com/api/agents/ws
```

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

### Eventos del WebSocket

#### Actualización de estado de agente

```json
{
  "event": "agent_updated",
  "agent_id": "uuid-string",
  "status": "active|inactive|maintenance",
  "timestamp": "ISO-timestamp",
  "version": 2
}
```

#### Validación completada

```json
{
  "event": "agent_validation_completed",
  "agent_id": "uuid-string",
  "status": "valid|invalid",
  "issues": [
    {
      "severity": "error|warning",
      "field": "system_prompt",
      "message": "El system prompt es demasiado largo (max 4000 caracteres)"
    }
  ],
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

- `validation_error`: Datos inválidos en la creación/actualización
- `resource_not_found`: Agente no existe
- `permission_denied`: Sin permisos para este agente
- `version_conflict`: Conflicto de versión al actualizar
- `tier_limit_exceeded`: Límite de agentes por tier superado

## Ejemplos de Código

### Crear Agente (JavaScript)

```javascript
const createAgent = async (agentData, authToken, tenantId) => {
  try {
    const response = await fetch('https://api.domain.com/api/agents', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(agentData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error creating agent:', error);
    throw error;
  }
};
```

### Escuchar Actualizaciones de Agente (WebSocket)

```javascript
const listenToAgentUpdates = (authToken, tenantId) => {
  const ws = new WebSocket(`wss://api.domain.com/api/agents/ws`);
  
  ws.onopen = () => {
    ws.send(JSON.stringify({
      action: "authenticate",
      token: authToken,
      tenant_id: tenantId
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.event === 'agent_updated') {
      // Actualizar UI con el nuevo estado
      updateAgentStatus(data.agent_id, data.status);
    }
    
    if (data.event === 'agent_validation_completed') {
      // Mostrar resultados de validación
      displayValidationResults(data.agent_id, data.status, data.issues);
    }
  };
  
  // Manejo de reconexión con backoff exponencial
  ws.onclose = (event) => {
    if (event.code !== 1000) {
      setTimeout(() => {
        listenToAgentUpdates(authToken, tenantId);
      }, 1000 * Math.pow(2, reconnectAttempts));
    }
  };
  
  return ws;
};
```

## Consideraciones por Tier de Servicio

| Tier | Limitaciones | Capacidades |
|------|-------------|-------------|
| Free | - Máximo 3 agentes<br>- Sin acceso a LLMs avanzados<br>- Límite de 1 agente activo a la vez | - Plantillas básicas<br>- Herramientas estándar |
| Professional | - Máximo 20 agentes<br>- Acceso a modelos intermedios<br>- Máximo 5 agentes activos simultáneamente | - Todas las plantillas<br>- Herramientas avanzadas<br>- Memoria extendida |
| Enterprise | - Agentes ilimitados<br>- Acceso a todos los modelos<br>- Agentes activos ilimitados | - Plantillas personalizadas<br>- Herramientas personalizadas<br>- Configuración avanzada |
