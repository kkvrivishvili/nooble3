# Integración del Frontend con Workflow Engine Service - Parte 1

## Introducción

Este documento describe la primera parte de la integración directa del frontend con el Workflow Engine Service para operaciones relacionadas con la definición, gestión y monitoreo de workflows. El acceso directo a este servicio permite a los administradores y desarrolladores crear y gestionar workflows complejos sin pasar por el orquestador, mientras que la ejecución de workflows en el contexto de una sesión de usuario continuará utilizando el orquestador como intermediario.

## Endpoints de API REST para Gestión de Workflows

### Listar workflows

```
GET /api/workflows
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 20)
- `offset`: Desplazamiento para paginación (default: 0)
- `status`: Filtrar por estado (`active`, `draft`, `archived`)
- `category`: Filtrar por categoría (`data_processing`, `conversation`, `automation`)
- `tag`: Filtrar por etiqueta

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "workflow_id": "uuid-string",
      "name": "Document Processing Workflow",
      "description": "Procesa documentos, extrae información y la almacena",
      "version": "1.2.0",
      "status": "active",
      "category": "data_processing",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp",
      "created_by": "user-id",
      "tags": ["document", "extraction", "storage"],
      "steps_count": 5
    },
    {
      "workflow_id": "uuid-string-2",
      "name": "Customer Onboarding",
      "description": "Flujo automatizado para nuevos clientes",
      "version": "2.0.1",
      "status": "active",
      "category": "automation",
      "created_at": "ISO-timestamp",
      "updated_at": "ISO-timestamp",
      "created_by": "user-id",
      "tags": ["customer", "onboarding"],
      "steps_count": 8
    },
    // más workflows...
  ],
  "total": 12,
  "limit": 20,
  "offset": 0
}
```

### Crear nuevo workflow

```
POST /api/workflows
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Data Enrichment Workflow",
  "description": "Enriquece datos con información externa",
  "category": "data_processing",
  "steps": [
    {
      "id": "input",
      "type": "input",
      "name": "Initial Data",
      "config": {
        "schema": {
          "type": "object",
          "properties": {
            "customer_id": { "type": "string" },
            "email": { "type": "string" }
          },
          "required": ["customer_id"]
        }
      },
      "next": "lookup"
    },
    {
      "id": "lookup",
      "type": "tool",
      "name": "Customer Lookup",
      "config": {
        "tool_id": "crm-lookup",
        "params_mapping": {
          "customer_id": "$.input.customer_id"
        }
      },
      "next": "enrich_data"
    },
    {
      "id": "enrich_data",
      "type": "tool",
      "name": "Data Enrichment",
      "config": {
        "tool_id": "data-enrichment",
        "params_mapping": {
          "email": "$.input.email",
          "company_domain": "$.lookup.results.company_domain"
        }
      },
      "next": "decision"
    },
    {
      "id": "decision",
      "type": "condition",
      "name": "Check Enrichment Success",
      "config": {
        "conditions": [
          {
            "condition": "$.enrich_data.success == true",
            "next": "output_success"
          }
        ],
        "default": "output_failure"
      }
    },
    {
      "id": "output_success",
      "type": "output",
      "name": "Success Result",
      "config": {
        "mapping": {
          "customer": "$.lookup.results",
          "enriched_data": "$.enrich_data.data",
          "success": true
        }
      }
    },
    {
      "id": "output_failure",
      "type": "output",
      "name": "Failure Result",
      "config": {
        "mapping": {
          "error": "$.enrich_data.error",
          "success": false
        }
      }
    }
  ],
  "input_schema": {
    "type": "object",
    "properties": {
      "customer_id": { 
        "type": "string",
        "description": "ID del cliente en el sistema" 
      },
      "email": { 
        "type": "string",
        "description": "Email del cliente (opcional)"
      }
    },
    "required": ["customer_id"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "success": { "type": "boolean" },
      "customer": { 
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "company_domain": { "type": "string" }
        }
      },
      "enriched_data": { "type": "object" },
      "error": { "type": "string" }
    }
  },
  "timeout_seconds": 120,
  "tags": ["data", "enrichment", "customer"],
  "metadata": {
    "owner": "data-team",
    "priority": "medium"
  },
  "status": "draft"
}
```

**Respuesta exitosa (201):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Data Enrichment Workflow",
  "description": "Enriquece datos con información externa",
  "version": "1.0.0",
  "status": "draft",
  "category": "data_processing",
  "created_at": "ISO-timestamp",
  "created_by": "user-id",
  "validation": {
    "status": "valid",
    "issues": []
  }
}
```

### Obtener workflow específico

```
GET /api/workflows/{workflow_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `version`: Versión específica (default: última)

**Respuesta exitosa (200):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Data Enrichment Workflow",
  "description": "Enriquece datos con información externa",
  "version": "1.0.0",
  "status": "draft",
  "category": "data_processing",
  "created_at": "ISO-timestamp",
  "updated_at": "ISO-timestamp",
  "created_by": "user-id",
  "tags": ["data", "enrichment", "customer"],
  "steps": [
    // Definición completa de los pasos como en la solicitud POST
  ],
  "input_schema": {
    // Schema completo como en la solicitud POST
  },
  "output_schema": {
    // Schema completo como en la solicitud POST
  },
  "timeout_seconds": 120,
  "metadata": {
    "owner": "data-team",
    "priority": "medium"
  },
  "stats": {
    "total_executions": 0,
    "success_rate": 0,
    "avg_duration_seconds": 0
  }
}
```

### Actualizar workflow existente

```
PUT /api/workflows/{workflow_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Enhanced Data Enrichment Workflow",
  "description": "Enriquece datos con múltiples fuentes externas",
  "steps": [
    // Definición actualizada de los pasos
  ],
  "input_schema": {
    // Schema actualizado
  },
  "output_schema": {
    // Schema actualizado
  },
  "timeout_seconds": 180,
  "tags": ["data", "enrichment", "customer", "enhanced"],
  "metadata": {
    "owner": "data-team",
    "priority": "high"
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Enhanced Data Enrichment Workflow",
  "version": "1.1.0",
  "status": "draft",
  "updated_at": "ISO-timestamp",
  "validation": {
    "status": "valid",
    "issues": []
  }
}
```
