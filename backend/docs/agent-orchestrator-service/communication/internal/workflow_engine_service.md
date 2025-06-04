# Comunicación con Workflow Engine Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Comunicación con Workflow Engine Service](#comunicación-con-workflow-engine-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Integración en Flujos de Trabajo](#2-integración-en-flujos-de-trabajo)
  - [3. Estructura de Colas](#3-estructura-de-colas)
  - [4. Formato de Mensajes](#4-formato-de-mensajes)
  - [5. Comunicación WebSocket](#5-comunicación-websocket)
  - [6. REST API](#6-rest-api)
  - [7. Gestión de Errores](#7-gestión-de-errores)

## 1. Visión General

El Agent Orchestrator Service interactúa con el Workflow Engine Service para la definición, ejecución y seguimiento de flujos de trabajo complejos multi-etapa. Esta comunicación es fundamental para orquestar secuencias de tareas condicionadas que involucran múltiples servicios y decisiones basadas en reglas de negocio.

### 1.1 Principios de Interacción

- **Orquestación de Alto Nivel**: El Agent Orchestrator inicia y monitorea workflows, mientras que el Workflow Engine gestiona su ejecución detallada
- **Estado Distribuido**: El estado de ejecución de los workflows se mantiene tanto en el Orchestrator (visión general) como en el Workflow Engine (detalle)
- **Comunicación Bidireccional**: El Orchestrator solicita ejecuciones y recibe actualizaciones de progreso y resultados
- **Delegación Controlada**: El Workflow Engine tiene autonomía para ejecutar los pasos definidos, pero consulta al Orchestrator en puntos críticos o para acceder a otros servicios

![Diagrama de Comunicación](../diagrams/orchestrator_workflow_communication.png)

## 2. Integración en Flujos de Trabajo

### 2.1 Workflow Multi-Etapa (Nivel 2)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant WE as Workflow Engine
    participant AE as Agent Execution
    participant TR as Tool Registry
    participant Q as Query Service
    
    C->>O: Consulta compleja
    O->>WE: Iniciar workflow
    WE->>WE: Planificar flujo
    WE->>AE: Ejecutar agente (paso 1)
    AE->>Q: Consulta LLM
    Q->>AE: Respuesta
    AE->>WE: Resultado paso 1
    WE->>O: Actualización progreso
    WE->>TR: Llamada a herramienta (paso 2)
    TR->>WE: Resultado de herramienta
    WE->>AE: Ejecutar con contexto (paso 3)
    AE->>WE: Respuesta final
    WE->>O: Resultado completo
    O->>C: Respuesta orquestada
```

### 2.2 Workflow con Ramificación Condicional (Nivel 3)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant WE as Workflow Engine
    participant S1 as Servicio A
    participant S2 as Servicio B
    
    C->>O: Solicitud
    O->>WE: Iniciar workflow con ramificación
    WE->>WE: Evaluar condición
    
    alt Condición verdadera
        WE->>S1: Ejecutar flujo A
        S1->>WE: Resultado A
    else Condición falsa
        WE->>S2: Ejecutar flujo B
        S2->>WE: Resultado B
    end
    
    WE->>WE: Paso final
    WE->>O: Resultado workflow
    O->>C: Respuesta final
```

### 2.3 Workflow con Entrada de Usuario (Nivel 2)

```mermaid
sequenceDiagram
    participant C as Cliente
    participant O as Orchestrator
    participant WE as Workflow Engine
    participant S as Servicio
    
    C->>O: Iniciar proceso
    O->>WE: Crear workflow interactivo
    WE->>S: Paso inicial
    S->>WE: Resultado parcial
    WE->>O: Solicitud información adicional
    O->>C: Formulario/Pregunta
    C->>O: Datos proporcionados
    O->>WE: Continuar workflow
    WE->>S: Procesar con datos nuevos
    S->>WE: Resultado final
    WE->>O: Workflow completado
    O->>C: Confirmación final
```

## 3. Estructura de Colas

Siguiendo el estándar global de comunicación, el Orchestrator interactúa con el Workflow Engine Service a través de colas Redis con la estructura estandarizada `service-name.[priority].[domain].[action]`.

### 3.1 Colas que Produce el Orchestrator 

| Cola | Domain | Action | Prioridad | Propósito | Productor | Consumidor |
|------|--------|--------|----------|-----------|----------|------------|
| `orchestrator.medium.workflow.define` | `workflow` | `define` | Media | Definición de nuevos workflows | Orchestrator | Workflow Engine |
| `orchestrator.high.workflow.execute` | `workflow` | `execute` | Alta | Solicitar ejecución de workflows | Orchestrator | Workflow Engine |
| `orchestrator.high.workflow.input` | `workflow` | `input` | Alta | Entrada adicional para workflows en espera | Orchestrator | Workflow Engine |
| `orchestrator.low.workflow.cancel` | `workflow` | `cancel` | Baja | Cancelar workflow en ejecución | Orchestrator | Workflow Engine |

### 3.2 Colas que Consume el Orchestrator

| Cola | Domain | Action | Prioridad | Propósito | Productor | Consumidor |
|------|--------|--------|----------|-----------|----------|------------|
| `workflow_engine.high.workflow.result` | `workflow` | `result` | Alta | Resultados finales de workflows | Workflow Engine | Orchestrator |
| `workflow_engine.medium.workflow.status` | `workflow` | `status` | Media | Actualización de estado de workflow | Workflow Engine | Orchestrator |
| `workflow_engine.high.workflow.input_request` | `workflow` | `input_request` | Alta | Solicitar input de usuario durante workflow | Workflow Engine | Orchestrator |
| `workflow_engine.high.workflow.error` | `workflow` | `error` | Alta | Notificación de errores en workflow | Workflow Engine | Orchestrator |

## 4. Formato de Mensajes

### 4.1 Estructura Base de Mensajes

Todos los mensajes intercambiados entre Agent Orchestrator Service y Workflow Engine Service siguen esta estructura base:

```json
{
  "message_id": "uuid-v4",           // ID único del mensaje
  "tenant_id": "tenant-identifier",  // ID del tenant 
  "timestamp": "ISO-8601-datetime",  // Momento de creación
  "version": "1.0",                  // Versión del formato
  "type": "request|response|event",  // Tipo de mensaje
  "source": "orchestrator",          // Servicio origen

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "define"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:50:15Z",
  "tenant_id": "tenant-identifier",
  "source_service": "orchestrator",
  "target_service": "workflow-engine",
  "priority": 5,
  "metadata": {
    "conversation_id": "conversation-id",
    "user_id": "user-uuid",
    "agent_id": "agent-identifier",
    "source_request_id": "original-request-id",
    "session_id": "session-identifier",
    "timeout_ms": 120000
  },
  "payload": {
    "workflow_id": "document-processor-workflow",
    "name": "Flujo de procesamiento de documentos",
    "version": "1.0.0",
    "description": "Workflow para procesar, analizar y extraer información de documentos",
    "nodes": [
      {
        "id": "start",
        "type": "start",
        "next": "document_processing"
      },
      {
        "id": "document_processing",
        "type": "task",
        "task": "document_processor",
        "config": {
          "extraction_level": "full"
        },
        "next": "language_detection"
      },
      {
        "id": "language_detection",
        "type": "decision",
        "condition": "${document.language} == 'es'",
        "branches": {
          "true": "spanish_processing",
          "false": "other_language_processing"
        }
      },
      // ... más nodos ...
    ],
    "default_timeout_ms": 60000
  }
}
```

<a id="42-workflowexecutionmessage"></a>
### 4.2 WorkflowExecutionMessage

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "execute"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:52:30Z",
  "tenant_id": "tenant-identifier",
  "source_service": "orchestrator",
  "target_service": "workflow-engine",
  "priority": 5,
  "metadata": {
    "conversation_id": "conversation-id",
    "user_id": "user-uuid",
    "agent_id": "agent-identifier",
    "source_request_id": "original-request-id",
    "session_id": "session-identifier",
    "timeout_ms": 120000
  },
  "payload": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "input": {
      "document_url": "https://example.com/document.pdf",
      "extraction_type": "full",
      "language_preference": "auto"
    },
    "context": {
      "user_preferences": {
        "output_format": "summary"
      }
    },
    "execution_options": {
      "callback_url": "https://api.example.com/callback",
      "wait_for_completion": false
    }
  }
}
```

<a id="43-workflowresultmessage"></a>
### 4.3 WorkflowResultMessage

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "original_task_id": "uuid-from-request",
  "type": {
    "domain": "workflow",
    "action": "result"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:54:45Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "target_service": "orchestrator",
  "priority": 5,
  "status": "completed",  // También puede ser 'failed' o 'paused'
  "metadata": {
    "execution_time_ms": 5200,
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "result": {
      "document_analysis": {
        "language": "es",
        "page_count": 5,
        "extracted_text": "Texto extraído del documento...",
        "summary": "Resumen del documento procesado..."
      },
      "processed_sections": [
        {
          "title": "Introducción",
          "content": "Contenido de la sección...",
          "relevance_score": 0.85
        }
        // ... más secciones ...
      ]
    },
    "execution_details": {
      "steps_completed": 5,
      "steps_total": 5,
      "node_path": ["start", "document_processing", "language_detection", "spanish_processing", "end"],
      "error": null
    }
  }
}
```

<a id="44-workflowinputmessage"></a>
### 4.4 WorkflowInputMessage

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "original-workflow-execution-id",
  "task_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "input"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:56:15Z",
  "tenant_id": "tenant-identifier",
  "source_service": "orchestrator",
  "target_service": "workflow-engine",
  "priority": 7,
  "metadata": {
    "user_id": "user-uuid",
    "input_request_id": "input-request-uuid",
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "input_data": {
      "user_confirmation": true,
      "selected_option": "opción 2",
      "additional_parameters": {
        "format": "PDF",
        "include_images": true
      }
    },
    "node_id": "user_input_node"
  }
}
```

<a id="45-workfloweventmessage"></a>
### 4.5 WorkflowEventMessage

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "task_id": "task-uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "status"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:57:30Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "target_service": "orchestrator",
  "priority": 4,
  "event_type": "step_completed",
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id"
  },
  "payload": {
    "step_id": "language_detection",
    "next_node": "spanish_processing",
    "progress_percentage": 60,
    "decision_made": "La condición '${document.language} == 'es'' fue evaluada como verdadera",
    "step_result": {
      "language": "es",
      "confidence": 0.95
    }
  }
}
```

<a id="46-servicerequestmessage"></a>
### 4.6 ServiceRequestMessage

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "type": {
    "domain": "tool",
    "action": "execute"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T16:59:00Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "target_service": "tool-registry",
  "priority": 6,
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "step_id": "document_processing",
    "session_id": "session-identifier"
  },
  "payload": {
    "tool_id": "document_processor",
    "inputs": {
      "document_url": "https://example.com/document.pdf",
      "extraction_type": "full"
    },
    "callback": {
      "queue": "workflow_engine.high.tool.result.{tenant_id}.{execution_id}",
      "response_key": "{step_id}"
    }
  }
}
```
## 5. Comunicación WebSocket

El Agent Orchestrator Service se suscribe a eventos de Workflow Engine Service a través de WebSockets para proporcionar actualizaciones en tiempo real a los clientes sobre el progreso y estado de los workflows. Siguiendo el estándar global domain/action, todos los eventos se estructuran con la forma `domain.action` para facilitar el enrutamiento y monitoreo.

### 5.1 Eventos Emitidos por el Orchestrator

| Evento | Domain | Action | Descripción | Destinatario |
|--------|--------|--------|------------|-------------|
| `workflow.started` | `workflow` | `started` | Notifica que se ha iniciado un workflow | Cliente Frontend |
| `workflow.step_update` | `workflow` | `step_update` | Informa sobre actualización de un paso | Cliente Frontend |
| `workflow.completed` | `workflow` | `completed` | Notifica que un workflow ha finalizado | Cliente Frontend |
| `workflow.input_request` | `workflow` | `input_request` | Solicita entrada del usuario | Cliente Frontend |

### 5.2 Formato de Eventos

Todos los eventos WebSocket siguen una estructura común que incluye:

- `event_id`: Identificador único del evento
- `type`: Objeto que contiene `domain` y `action` para clasificar el evento
- `created_at`: Timestamp ISO 8601 de creación del evento
- `tenant_id`: Identificador del tenant
- `source_service`: Servicio que origina el evento
- `correlation_id`: ID para correlacionar con otras operaciones
- `metadata`: Metadatos adicionales para trazabilidad
- `payload`: Contenido específico del evento

<a id="51-workflowstartedevent"></a>
#### 5.1 WorkflowStartedEvent

```json
{
  "event_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "started"
  },
  "created_at": "2025-06-03T17:10:00Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "correlation_id": "orchestrator-task-id",
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "workflow_name": "Flujo de procesamiento de documentos",
    "estimated_steps": 5,
    "estimated_duration_ms": 120000,
    "initiator_id": "user-uuid",
    "input_summary": {
      "document_type": "PDF",
      "action": "extract"
    }
  }
}
```

<a id="52-workflowstepupdateevent"></a>
#### 5.2 WorkflowStepUpdateEvent

```json
{
  "event_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "step_update"
  },
  "created_at": "2025-06-03T17:11:30Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "correlation_id": "orchestrator-task-id",
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "step_id": "document_processing",
    "step_name": "Procesamiento de Documento",
    "status": "completed",
    "progress": {
      "current_step": 2,
      "total_steps": 5,
      "percentage": 40
    },
    "duration_ms": 15200,
    "result_summary": "Documento procesado exitosamente. Se detectó idioma Español."
  }
}
```

<a id="53-workflowcompletedevent"></a>
#### 5.3 WorkflowCompletedEvent

```json
{
  "event_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "completed"
  },
  "created_at": "2025-06-03T17:15:45Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "correlation_id": "orchestrator-task-id",
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "status": "successful",
    "steps_executed": 5,
    "total_duration_ms": 350000,
    "result_summary": "Procesamiento completo. Se extrajeron 15 secciones relevantes.",
    "output_location": "/results/document-analysis-123.json",
    "next_actions": [
      {
        "type": "download",
        "url": "/api/v1/documents/123/download",
        "label": "Descargar análisis"
      }
    ]
  }
}
```

<a id="54-workflowinputrequestevent"></a>
#### 5.4 WorkflowInputRequestEvent

```json
{
  "event_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "input_request"
  },
  "created_at": "2025-06-03T17:13:20Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "correlation_id": "orchestrator-task-id",
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "session_id": "session-identifier"
  },
  "payload": {
    "request_id": "input-request-uuid",
    "step_id": "user_input_node",
    "prompt": "Por favor seleccione el formato de salida preferido:",
    "input_type": "select",
    "options": [
      {
        "value": "pdf",
        "label": "PDF"
      },
      {
        "value": "docx",
        "label": "Word Document"
      },
      {
        "value": "txt",
        "label": "Texto plano"
      }
    ],
    "timeout_ms": 300000,
    "required": true
  }
}
```
## 6. REST API

El Agent Orchestrator Service se comunica con el Workflow Engine Service a través de APIs REST que siguen el estándar domain/action. Todos los endpoints y headers reflejan esta estructura para mantener la coherencia en todo el sistema.

### 6.1 Headers Estandarizados

Todas las llamadas REST incluyen los siguientes headers estándar:

| Header | Descripción | Ejemplo |
|--------|-------------|--------|
| `Authorization` | Token Bearer JWT para autenticación | `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `X-Tenant-ID` | Identificador del tenant | `tenant-identifier` |
| `X-Correlation-ID` | ID de correlación para trazabilidad | `uuid-v4` |
| `X-Request-ID` | ID único de la solicitud | `uuid-v4` |
| `X-Domain-Action` | Domain y action de la operación | `workflow.execute` |
| `Content-Type` | Tipo de contenido (generalmente application/json) | `application/json` |

### 6.2 APIs que Consume el Orchestrator

| Endpoint | Método | Domain | Action | Propósito |
|----------|---------|--------|--------|----------|
| `/api/v1/workflow/definitions` | `GET` | `workflow` | `list` | Listar definiciones de workflows disponibles |
| `/api/v1/workflow/definitions/{workflow_id}` | `GET` | `workflow` | `get` | Obtener detalle de definición de workflow |
| `/api/v1/workflow/executions/{execution_id}` | `GET` | `workflow` | `status` | Obtener estado de ejecución de workflow |
| `/api/v1/workflow/executions` | `GET` | `workflow` | `list_executions` | Listar ejecuciones de workflows filtradas |
| `/api/v1/workflow/validate` | `POST` | `workflow` | `validate` | Validar definición de workflow |
| `/api/v1/workflow/execute` | `POST` | `workflow` | `execute` | Iniciar ejecución de workflow |
| `/api/v1/workflow/executions/{execution_id}/cancel` | `POST` | `workflow` | `cancel` | Cancelar ejecución de workflow |

### 6.3 APIs que Expone el Orchestrator para el Workflow Engine

| Endpoint | Método | Domain | Action | Propósito |
|----------|---------|--------|--------|----------|
| `/api/v1/orchestrator/workflows/callback` | `POST` | `workflow` | `callback` | Recibir callbacks de workflow |
| `/api/v1/orchestrator/tools/execute` | `POST` | `tool` | `execute` | Ejecutar herramientas desde workflow |
| `/api/v1/orchestrator/integrations/{integration_id}/invoke` | `POST` | `integration` | `invoke` | Invocar integraciones externas |

### 6.4 Ejemplos de Llamadas

#### Consulta de Estado de Workflow

```http
GET /api/v1/workflow/executions/exec-12345 HTTP/1.1
Host: workflow-engine.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Tenant-ID: tenant-identifier
X-Correlation-ID: corr-abc-123
X-Request-ID: req-xyz-789
X-Domain-Action: workflow.status
```

**Respuesta:**

```json
{
  "request_id": "req-xyz-789",
  "correlation_id": "corr-abc-123",
  "type": {
    "domain": "workflow",
    "action": "status"
  },
  "schema_version": "1.0",
  "status": "success",
  "data": {
    "execution_id": "exec-12345",
    "workflow_id": "doc-processor-v1",
    "status": "in_progress",
    "current_step": {
      "step_id": "language_detection",
      "started_at": "2025-06-03T17:11:00Z"
    },
    "progress": {
      "completed_steps": 1,
      "total_steps": 5,
      "percentage": 20
    },
    "started_at": "2025-06-03T17:10:00Z",
    "estimated_completion": "2025-06-03T17:15:00Z",
    "logs": [
      {
        "timestamp": "2025-06-03T17:10:30Z",
        "level": "info",
        "message": "Documento recibido para procesamiento"
      }
    ]
  }
}
```

#### Callback desde Workflow Engine

```http
POST /api/v1/orchestrator/workflows/callback HTTP/1.1
Host: orchestrator.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
X-Tenant-ID: tenant-identifier
X-Correlation-ID: corr-abc-123
X-Request-ID: req-workflow-456
X-Domain-Action: workflow.input_request

{
  "request_id": "req-workflow-456",
  "correlation_id": "corr-abc-123",
  "type": {
    "domain": "workflow",
    "action": "input_request"
  },
  "schema_version": "1.0",
  "data": {
    "execution_id": "exec-12345",
    "workflow_id": "doc-processor-v1",
    "request_id": "input-req-789",
    "prompt": "¿Desea continuar con la traducción del documento?",
    "input_type": "confirm",
    "timeout_ms": 300000
  }
}
```
## 7. Gestión de Errores

La gestión de errores del Workflow Engine Service sigue el estándar domain/action, utilizando códigos de error estructurados y políticas de manejo específicas para cada tipo de error.

### 7.1 Estructura de Errores

Todos los errores siguen la estructura estándar:

```json
{
  "type": {
    "domain": "workflow",
    "action": "error"
  },
  "error": {
    "code": "workflow.execution.step_failed",
    "http_status": 400,
    "message": "Error descriptivo del problema",
    "details": {},
    "retryable": true|false,
    "retry_after_ms": 5000
  },
  "correlation_id": "uuid-v4",
  "request_id": "uuid-v4"
}
```

### 7.2 Códigos de Error Estándar

Los códigos de error siguen la convención `domain.action.error_type` para mantener consistencia con el resto del sistema:

| Código de Error | HTTP Status | Descripción | Reintentable | Backoff |
|----------------|------------|-------------|-------------|--------|
| `workflow.define.validation_error` | 400 | Error en validación de definición de workflow | No | - |
| `workflow.execute.timeout` | 408 | Timeout en ejecución de workflow | Sí | Exponencial |
| `workflow.execute.step_failed` | 400 | Error en paso específico de workflow | Sí | Lineal |
| `workflow.service.unavailable` | 503 | Servicio dependiente no disponible | Sí | Exponencial |
| `workflow.input.timeout` | 408 | Timeout esperando entrada de usuario | Sí | Lineal |
| `workflow.access.forbidden` | 403 | Permisos insuficientes para la operación | No | - |
| `tool.execute.failed` | 400 | Error en ejecución de herramienta | Sí | Lineal |
| `integration.invoke.failed` | 502 | Error en invocación de integración externa | Sí | Exponencial |

### 7.3 Estrategias de Manejo de Errores

| Tipo de Error | Estrategia | Implementación | Circuit Breaker | Máx. Reintentos |
|---------------|------------|----------------|----------------|----------------|
| **Errores de Validación** | Fallo rápido | Respuesta inmediata sin reintentos | No | 0 |
| **Errores de Timeout** | Reintento con backoff | Reintentos con intervalos exponenciales | Sí | 3 |
| **Errores de Paso** | Reintento con diagnóstico | Reintentos con análisis previo de causa | Sí | 3 |
| **Errores de Servicio** | Circuit breaker | Apertura de circuito tras múltiples fallos | Sí | 5 |
| **Errores de Entrada** | Recordatorio y valores por defecto | Notificaciones y continuación con valores por defecto | No | 2 |
| **Errores de Permiso** | Log y notificación | Registro detallado para auditoría | No | 0 |

### 7.4 Ejemplo de Mensaje de Error

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "request_id": "req-xyz-789",
  "type": {
    "domain": "workflow",
    "action": "error"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-03T17:12:30Z",
  "tenant_id": "tenant-identifier",
  "source_service": "workflow-engine",
  "target_service": "orchestrator",
  "priority": 8,
  "error": {
    "code": "workflow.execute.step_failed",
    "http_status": 400,
    "message": "Error en paso de workflow 'document_processing'",
    "retryable": true,
    "retry_after_ms": 5000,
    "details": {
      "workflow_id": "doc-processor-v1",
      "execution_id": "exec-12345",
      "step_id": "document_processing",
      "error_type": "tool_execution_failed",
      "error_details": "El documento proporcionado está dañado o en un formato no soportado",
      "retry_count": 3,
      "recommendation": "Verificar el formato del documento o intentar con un documento diferente"
    }
  }
}
```

### 7.5 Monitoreo y Alertas

El Agent Orchestrator Service implementa las siguientes métricas específicas para la comunicación con Workflow Engine Service, siguiendo la convención domain/action en los nombres de las métricas:

| Métrica | Tipo | Tags | Propósito |
|---------|------|------|----------|
| `workflow.execute.duration_ms` | Histograma | domain, action, workflow_id | Medir tiempo de ejecución de workflows |
| `workflow.step.duration_ms` | Histograma | domain, action, workflow_id, step_id | Medir tiempo de ejecución por paso |
| `workflow.error.count` | Contador | domain, action, error_code | Contar errores por tipo |
| `workflow.retry.count` | Contador | domain, action, workflow_id, step_id | Contar reintentos por paso |
| `workflow.queue.depth` | Gauge | domain, action, queue | Monitorear profundidad de las colas |
| `workflow.active.executions` | Gauge | domain, action, tenant_id | Monitorear workflows activos |

### 7.6 Ejemplos de Implementación de Manejo de Errores

#### Cliente Python con Manejo de Errores

```python
class WorkflowEngineClient:
    def __init__(self, base_url, tenant_id, api_key):
        self.base_url = base_url
        self.tenant_id = tenant_id
        self.session = self._create_session(api_key)
    
    def _create_session(self, api_key):
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'X-Tenant-ID': self.tenant_id,
            'Content-Type': 'application/json'
        })
        
        # Configurar retry con backoff exponencial
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def execute_workflow(self, workflow_id, input_data):
        correlation_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        headers = {
            'X-Correlation-ID': correlation_id,
            'X-Request-ID': request_id,
            'X-Domain-Action': 'workflow.execute'
        }
        
        payload = {
            "message_id": str(uuid.uuid4()),
            "correlation_id": correlation_id,
            "type": {
                "domain": "workflow",
                "action": "execute"
            },
            "schema_version": "1.0",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "source_service": "orchestrator",
            "target_service": "workflow-engine",
            "priority": 5,
            "payload": {
                "workflow_id": workflow_id,
                "input": input_data
            }
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/workflow/execute",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_data = e.response.json()
            if 'error' in error_data and error_data['error'].get('retryable', False):
                # Implementar lógica de reintento específica si es necesario
                retry_after = error_data['error'].get('retry_after_ms', 5000) / 1000
                time.sleep(retry_after)
                return self.execute_workflow(workflow_id, input_data)
            else:
                # Propagar error con contexto mejorado
                raise WorkflowEngineError(
                    error_data.get('error', {}).get('message', 'Error desconocido'),
                    error_data.get('error', {}).get('code', 'unknown'),
                    error_data
                )
        except requests.exceptions.Timeout:
            # Manejar timeouts específicamente
            raise WorkflowEngineError(
                "Timeout al ejecutar el workflow",
                "workflow.execute.timeout",
                {"workflow_id": workflow_id}
            )
        except Exception as e:
            # Capturar y transformar otros errores
            raise WorkflowEngineError(
                f"Error inesperado: {str(e)}",
                "workflow.client.unexpected_error",
                {"exception": str(e)}
            )
```

---

## Registro de Cambios

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2025-06-03 | Equipo Nooble Backend | Versión inicial |
