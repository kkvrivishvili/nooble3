# Integración del Frontend con Tool Registry Service - Parte 1

## Introducción

Este documento describe la primera parte de la integración directa del frontend con el Tool Registry Service para operaciones CRUD y administrativas relacionadas con el registro y gestión de herramientas disponibles para los agentes. El acceso directo a este servicio permite a los administradores y desarrolladores gestionar el catálogo de herramientas sin pasar por el orquestador.

## Endpoints de API REST Básicos

### Listar herramientas disponibles

```
GET /api/tools
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 50)
- `offset`: Desplazamiento para paginación (default: 0)
- `category`: Filtrar por categoría (`data`, `utility`, `external_api`, `custom`)
- `status`: Filtrar por estado (`active`, `deprecated`, `draft`)
- `tier`: Filtrar por nivel requerido (`free`, `professional`, `enterprise`)

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "tool_id": "search-tool",
      "name": "Search Tool",
      "description": "Busca información en fuentes internas y externas",
      "category": "data",
      "version": "1.2.0",
      "status": "active",
      "required_tier": "free",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp"
    },
    {
      "tool_id": "calculator-tool",
      "name": "Calculator",
      "description": "Realiza operaciones matemáticas complejas",
      "category": "utility",
      "version": "1.0.5",
      "status": "active",
      "required_tier": "free",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp"
    },
    // más herramientas...
  ],
  "total": 24,
  "limit": 50,
  "offset": 0
}
```

### Obtener herramienta específica

```
GET /api/tools/{tool_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "tool_id": "search-tool",
  "name": "Search Tool",
  "description": "Busca información en fuentes internas y externas",
  "category": "data",
  "version": "1.2.0",
  "status": "active",
  "required_tier": "free",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "schema": {
    "input_schema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Consulta de búsqueda"
        },
        "limit": {
          "type": "integer",
          "default": 5,
          "description": "Número máximo de resultados"
        }
      },
      "required": ["query"]
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": { "type": "string" },
              "snippet": { "type": "string" },
              "url": { "type": "string" }
            }
          }
        }
      }
    }
  },
  "configuration": {
    "default_timeout": 10000,
    "rate_limit": {
      "requests_per_minute": 60,
      "requests_per_hour": 1000
    }
  },
  "usage_stats": {
    "total_invocations": 12500,
    "success_rate": 98.7,
    "average_latency_ms": 450
  },
  "integration_type": "internal"
}
```

### Obtener herramientas disponibles por tenant

```
GET /api/tools/available/{tenant_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`

**Respuesta exitosa (200):**
```json
{
  "tenant_id": "tenant-id",
  "tier": "professional",
  "available_tools": [
    {
      "tool_id": "search-tool",
      "name": "Search Tool",
      "category": "data",
      "version": "1.2.0",
      "status": "active"
    },
    {
      "tool_id": "weather-api",
      "name": "Weather API",
      "category": "external_api",
      "version": "2.0.1",
      "status": "active"
    },
    // más herramientas disponibles...
  ],
  "custom_tools": [
    {
      "tool_id": "custom-crm-tool",
      "name": "CRM Integration",
      "category": "custom",
      "version": "1.0.0",
      "status": "active"
    }
  ],
  "total_tools": 15
}
```

### Registrar nueva herramienta

```
POST /api/tools/register
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "tool_id": "email-tool",
  "name": "Email Sender",
  "description": "Envía correos electrónicos desde el agente",
  "category": "communication",
  "required_tier": "professional",
  "schema": {
    "input_schema": {
      "type": "object",
      "properties": {
        "to": {
          "type": "string",
          "description": "Destinatario del correo"
        },
        "subject": {
          "type": "string",
          "description": "Asunto del correo"
        },
        "body": {
          "type": "string",
          "description": "Cuerpo del mensaje"
        }
      },
      "required": ["to", "subject", "body"]
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "success": { "type": "boolean" },
        "message_id": { "type": "string" }
      }
    }
  },
  "configuration": {
    "default_timeout": 5000,
    "rate_limit": {
      "requests_per_minute": 10
    }
  },
  "integration_type": "custom_api",
  "integration_config": {
    "endpoint": "https://api.example.com/email",
    "auth_type": "api_key"
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "tool_id": "email-tool",
  "name": "Email Sender",
  "description": "Envía correos electrónicos desde el agente",
  "category": "communication",
  "version": "1.0.0",
  "status": "draft",
  "required_tier": "professional",
  "created_at": "ISO-timestamp",
  "validation_status": "pending"
}
```
