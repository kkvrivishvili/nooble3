# Integración del Frontend con Workflow Engine Service - Parte 2

## Endpoints de API REST para Ejecución y Monitoreo de Workflows

### Publicar workflow (cambiar a activo)

```
POST /api/workflows/{workflow_id}/publish
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "version_notes": "Primera versión estable",
  "notify_subscribers": true
}
```

**Respuesta exitosa (200):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Data Enrichment Workflow",
  "version": "1.0.0",
  "previous_status": "draft",
  "status": "active",
  "published_at": "ISO-timestamp",
  "published_by": "user-id"
}
```

### Ejecutar workflow para pruebas

```
POST /api/workflows/{workflow_id}/test-execute
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "input": {
    "customer_id": "CUST-12345",
    "email": "test@example.com"
  },
  "version": "1.0.0",
  "environment": "sandbox",
  "debug_mode": true
}
```

**Respuesta exitosa (202 Accepted):**
```json
{
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "status": "started",
  "started_at": "ISO-timestamp",
  "monitor_url": "/api/workflow-executions/{execution_id}"
}
```

### Obtener estado de ejecución

```
GET /api/workflow-executions/{execution_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "workflow_version": "1.0.0",
  "status": "completed",
  "started_at": "ISO-timestamp",
  "completed_at": "ISO-timestamp",
  "duration_ms": 2450,
  "current_step": null,
  "completed_steps": ["input", "lookup", "enrich_data", "decision", "output_success"],
  "input": {
    "customer_id": "CUST-12345",
    "email": "test@example.com"
  },
  "output": {
    "customer": {
      "name": "Test Company",
      "company_domain": "example.com"
    },
    "enriched_data": {
      "company_size": "101-250",
      "industry": "Technology",
      "founded_year": 2010
    },
    "success": true
  },
  "debug_logs": [
    {
      "timestamp": "ISO-timestamp",
      "step": "lookup",
      "message": "Ejecutando lookup con customer_id=CUST-12345",
      "level": "info"
    },
    {
      "timestamp": "ISO-timestamp",
      "step": "enrich_data",
      "message": "Datos enriquecidos correctamente",
      "level": "info"
    },
    {
      "timestamp": "ISO-timestamp",
      "step": "decision",
      "message": "Condición '$.enrich_data.success == true' evaluada como verdadera",
      "level": "debug"
    }
  ]
}
```

### Listar ejecuciones de workflow

```
GET /api/workflows/{workflow_id}/executions
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `limit`: Número máximo de resultados (default: 20)
- `offset`: Desplazamiento para paginación (default: 0)
- `status`: Filtrar por estado (`running`, `completed`, `failed`, `timeout`)
- `from_date`: Filtrar desde fecha (ISO-timestamp)
- `to_date`: Filtrar hasta fecha (ISO-timestamp)

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "execution_id": "uuid-string",
      "workflow_id": "uuid-string",
      "workflow_version": "1.0.0",
      "status": "completed",
      "started_at": "ISO-timestamp",
      "completed_at": "ISO-timestamp",
      "duration_ms": 2450,
      "triggered_by": "user-id",
      "trigger_type": "api"
    },
    {
      "execution_id": "uuid-string-2",
      "workflow_id": "uuid-string",
      "workflow_version": "1.0.0",
      "status": "failed",
      "started_at": "ISO-timestamp",
      "completed_at": "ISO-timestamp",
      "duration_ms": 1320,
      "error": "Error en el paso 'enrich_data': API externa no disponible",
      "triggered_by": "system",
      "trigger_type": "scheduled"
    },
    // más ejecuciones...
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

### Cancelar ejecución en curso

```
POST /api/workflow-executions/{execution_id}/cancel
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "execution_id": "uuid-string",
  "status": "cancelling",
  "cancel_requested_at": "ISO-timestamp",
  "previous_step": "enrich_data"
}
```

### Versiones y versionado

```
GET /api/workflows/{workflow_id}/versions
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Data Enrichment Workflow",
  "versions": [
    {
      "version": "1.0.0",
      "status": "active",
      "created_at": "ISO-timestamp",
      "created_by": "user-id",
      "published_at": "ISO-timestamp",
      "notes": "Primera versión estable",
      "is_current": false
    },
    {
      "version": "1.1.0",
      "status": "active",
      "created_at": "ISO-timestamp",
      "created_by": "user-id",
      "published_at": "ISO-timestamp",
      "notes": "Añadido soporte para múltiples fuentes",
      "is_current": true
    },
    {
      "version": "2.0.0-beta",
      "status": "draft",
      "created_at": "ISO-timestamp",
      "created_by": "user-id",
      "notes": "Rediseño completo del workflow",
      "is_current": false
    }
  ],
  "total_versions": 3
}
```

## Endpoints para Plantillas de Workflows

### Listar plantillas de workflows

```
GET /api/workflow-templates
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Parámetros de consulta opcionales:**
- `category`: Filtrar por categoría
- `complexity`: Filtrar por complejidad (`simple`, `medium`, `complex`)

**Respuesta exitosa (200):**
```json
{
  "items": [
    {
      "template_id": "data-processing-basic",
      "name": "Basic Data Processing",
      "description": "Plantilla simple para procesamiento básico de datos",
      "category": "data_processing",
      "complexity": "simple",
      "steps_count": 3,
      "preview_image_url": "https://api.domain.com/images/templates/data-processing-basic.png",
      "popularity": 95
    },
    {
      "template_id": "customer-onboarding",
      "name": "Customer Onboarding",
      "description": "Flujo completo de incorporación de nuevos clientes",
      "category": "automation",
      "complexity": "medium",
      "steps_count": 7,
      "preview_image_url": "https://api.domain.com/images/templates/customer-onboarding.png",
      "popularity": 87
    },
    // más plantillas...
  ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

### Obtener plantilla

```
GET /api/workflow-templates/{template_id}
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

**Respuesta exitosa (200):**
```json
{
  "template_id": "data-processing-basic",
  "name": "Basic Data Processing",
  "description": "Plantilla simple para procesamiento básico de datos",
  "category": "data_processing",
  "complexity": "simple",
  "created_at": "ISO-timestamp",
  "last_updated": "ISO-timestamp",
  "preview_image_url": "https://api.domain.com/images/templates/data-processing-basic.png",
  "popularity": 95,
  "steps": [
    // Definición completa de los pasos
  ],
  "input_schema": {
    // Schema de entrada
  },
  "output_schema": {
    // Schema de salida
  },
  "customization_points": [
    {
      "path": "steps[1].config.tool_id",
      "name": "Herramienta de procesamiento",
      "description": "Herramienta a utilizar para el procesamiento de datos",
      "type": "tool_selector",
      "categories": ["data_processing"]
    },
    {
      "path": "input_schema.properties",
      "name": "Campos de entrada",
      "description": "Define los campos que recibirá el workflow",
      "type": "schema_editor"
    }
  ]
}
```

### Crear workflow desde plantilla

```
POST /api/workflow-templates/{template_id}/create
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "name": "Mi Workflow de Procesamiento",
  "description": "Procesamiento de datos personalizado",
  "customizations": {
    "steps[1].config.tool_id": "mi-herramienta-procesamiento",
    "steps[2].config.condition": "$.processing.status == 'success'",
    "input_schema.properties": {
      "file_id": {
        "type": "string",
        "description": "ID del archivo a procesar"
      },
      "format": {
        "type": "string",
        "enum": ["json", "csv", "xml"],
        "default": "csv"
      }
    }
  },
  "tags": ["datos", "personalizado", "csv"],
  "metadata": {
    "department": "marketing"
  }
}
```

**Respuesta exitosa (201):**
```json
{
  "workflow_id": "uuid-string",
  "name": "Mi Workflow de Procesamiento",
  "description": "Procesamiento de datos personalizado",
  "version": "1.0.0",
  "status": "draft",
  "created_at": "ISO-timestamp",
  "created_from_template": "data-processing-basic"
}
```
