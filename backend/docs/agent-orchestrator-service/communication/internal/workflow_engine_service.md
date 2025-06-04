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

El Orchestrator interactúa con el Workflow Engine Service a través de las siguientes colas Redis:

### 3.1 Colas que Produce el Orchestrator 

| Cola | Propósito | Formato de Mensaje | Consumidor |
|------|-----------|-------------------|------------|
| `workflow_tasks:{tenant_id}` | Cola principal para tareas de workflow | [WorkflowTaskMessage](#41-workflowtaskmessage) | Workflow Engine Service |
| `workflow_executions:{tenant_id}:{workflow_id}` | Iniciar ejecuciones de workflows | [WorkflowExecutionMessage](#42-workflowexecutionmessage) | Workflow Engine Service |
| `workflow_input:{tenant_id}:{execution_id}` | Entrada adicional para workflows en espera | [WorkflowInputMessage](#44-workflowinputmessage) | Workflow Engine Service |

### 3.2 Colas que Consume el Orchestrator

| Cola | Propósito | Formato de Mensaje | Productor |
|------|-----------|-------------------|-----------|
| `workflow_results:{tenant_id}:{execution_id}` | Resultados de workflows | [WorkflowResultMessage](#43-workflowresultmessage) | Workflow Engine Service |
| `workflow_events:{tenant_id}:{execution_id}` | Notificaciones de eventos de workflow | [WorkflowEventMessage](#45-workfloweventmessage) | Workflow Engine Service |
| `workflow_service_request:{tenant_id}` | Solicitudes de workflow a otros servicios | [ServiceRequestMessage](#46-servicerequestmessage) | Workflow Engine Service |

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
  "destination": "workflow-engine",   // Servicio destino
  "correlation_id": "uuid-v4",       // ID de correlación
  "task_id": "uuid-v4",              // ID único de la tarea
  "session_id": "session-id",        // ID de la sesión (si aplica)
  "status": "pending|completed|failed", // Estado
  "priority": 0-9,                   // Prioridad (0-9)
  "payload": {}                      // Datos específicos
}
```

<a id="41-workflowdefinitionmessage"></a>
### 4.2 WorkflowDefinitionMessage

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:50:00Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "workflow-engine",
  "correlation_id": "admin-operation-id",
  "task_id": "uuid-v4",
  "status": "pending",
  "priority": 3,
  "metadata": {
    "source_request_id": "admin-api-request",
    "user_id": "admin-uuid",
    "timeout_ms": 30000
  },
  "payload": {
    "operation": "define_workflow",
    "workflow": {
      "id": "document-extraction-workflow",
      "name": "Extracción y Análisis de Documentos",
      "description": "Workflow para extraer, procesar y analizar documentos",
      "version": "1.0.0",
      "tags": ["document", "extraction", "analysis"],
      "nodes": [
        {
          "id": "start",
          "type": "start",
          "next": "document_extraction"
        },
        {
          "id": "document_extraction",
          "type": "task",
          "service": "agent_execution",
          "action": "execute_tool",
          "parameters": {
            "tool_id": "document_extractor"
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
}
```

<a id="42-workflowexecutionmessage"></a>
### 4.3 WorkflowExecutionMessage

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:52:30Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "workflow-engine",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 5,
  "metadata": {
    "conversation_id": "conversation-id",
    "user_id": "user-uuid",
    "agent_id": "agent-identifier",
    "source_request_id": "original-request-id",
    "timeout_ms": 120000
  },
  "payload": {
    "operation": "execute_workflow",
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
### 4.4 WorkflowResultMessage

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:54:45Z",
  "version": "1.0",
  "type": "response",
  "source": "workflow-engine",
  "destination": "orchestrator",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "original_task_id": "uuid-from-request",
  "session_id": "session-identifier",
  "status": "completed|failed|paused",
  "metadata": {
    "execution_time_ms": 5200,
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id"
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
### 4.5 WorkflowInputMessage

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:56:15Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "workflow-engine",
  "correlation_id": "original-workflow-execution-id",
  "task_id": "uuid-v4",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 7,
  "metadata": {
    "user_id": "user-uuid",
    "input_request_id": "input-request-uuid",
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id"
  },
  "payload": {
    "operation": "provide_input",
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
  "event": "workflow.step_completed",
  "service": "workflow-engine",
  "task_id": "task-uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:57:30Z",
  "data": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
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
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:59:00Z",
  "version": "1.0",
  "type": "request",
  "source": "workflow-engine",
  "destination": "tool-registry",
  "correlation_id": "orchestrator-task-id",
  "task_id": "uuid-v4",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 6,
  "metadata": {
    "workflow_id": "workflow-definition-id",
    "execution_id": "execution-instance-id",
    "step_id": "document_processing"
  },
  "payload": {
    "operation": "execute_tool",
    "parameters": {
      "tool_id": "document_processor",
      "inputs": {
        "document_url": "https://example.com/document.pdf",
        "extraction_type": "full"
      }
    },
    "callback": {
      "queue": "workflow.tool.results.{tenant_id}.{execution_id}",
      "response_key": "tool.result.{step_id}"
    }
  }
}
```
## 5. Comunicación WebSocket

El Agent Orchestrator Service se suscribe a eventos de Workflow Engine Service a través de WebSockets para proporcionar actualizaciones en tiempo real a los clientes sobre el progreso y estado de los workflows.

### 5.1 Eventos Emitidos por el Orchestrator

| Evento | Descripción | Payload | Destinatario |
|--------|------------|---------|-------------|
| `workflow.started` | Notifica que se ha iniciado un workflow | [WorkflowStartedEvent](#51-workflowstartedevent) | Cliente Frontend |
| `workflow.step_update` | Informa sobre actualización de un paso | [WorkflowStepUpdateEvent](#52-workflowstepupdateevent) | Cliente Frontend |
| `workflow.completed` | Notifica que un workflow ha finalizado | [WorkflowCompletedEvent](#53-workflowcompletedevent) | Cliente Frontend |
| `workflow.input_request` | Solicita entrada del usuario | [WorkflowInputRequestEvent](#54-workflowinputrequestevent) | Cliente Frontend |

### 5.2 Formato de Eventos

<a id="51-workflowstartedevent"></a>
#### 5.1 WorkflowStartedEvent

```json
{
  "event": "workflow.started",
  "tenant_id": "tenant-identifier",
  "workflow_id": "workflow-definition-id",
  "execution_id": "execution-instance-id",
  "timestamp": "2025-06-03T17:10:00Z",
  "data": {
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
  "event": "workflow.step_update",
  "tenant_id": "tenant-identifier",
  "workflow_id": "workflow-definition-id",
  "execution_id": "execution-instance-id",
  "timestamp": "2025-06-03T17:11:30Z",
  "data": {
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
  "event": "workflow.completed",
  "tenant_id": "tenant-identifier",
  "workflow_id": "workflow-definition-id",
  "execution_id": "execution-instance-id",
  "timestamp": "2025-06-03T17:15:45Z",
  "data": {
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
  "event": "workflow.input_request",
  "tenant_id": "tenant-identifier",
  "workflow_id": "workflow-definition-id",
  "execution_id": "execution-instance-id",
  "timestamp": "2025-06-03T17:13:20Z",
  "data": {
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

El Agent Orchestrator Service se comunica con el Workflow Engine Service a través de las siguientes APIs REST:

### 6.1 APIs que Consume el Orchestrator

| Endpoint | Método HTTP | Propósito | Formato de Respuesta |
|----------|------------|-----------|---------------------|
| `/api/v1/workflows` | `GET` | Listar definiciones de workflows disponibles | Lista de WorkflowDefinition |
| `/api/v1/workflows/{workflow_id}` | `GET` | Obtener detalle de definición de workflow | WorkflowDefinition |
| `/api/v1/workflows/{workflow_id}/executions/{execution_id}` | `GET` | Obtener estado de ejecución de workflow | WorkflowExecutionStatus |
| `/api/v1/workflows/executions` | `GET` | Listar ejecuciones de workflows filtradas | Lista de WorkflowExecutionStatus |
| `/api/v1/workflows/validate` | `POST` | Validar definición de workflow | ValidationResult |

### 6.2 APIs que Expone el Orchestrator para el Workflow Engine

| Endpoint | Método HTTP | Propósito | Formato de Respuesta |
|----------|------------|-----------|---------------------|
| `/api/v1/orchestrator/callback/{execution_id}` | `POST` | Recibir callbacks de workflow | CallbackResponse |
| `/api/v1/orchestrator/services/{service_name}/invoke` | `POST` | Invocar otros servicios desde workflow | ServiceResponse |

### 6.3 Ejemplos de Llamadas

#### Consulta de Estado de Workflow

```http
GET /api/v1/workflows/doc-processor-v1/executions/exec-12345 HTTP/1.1
Host: workflow-engine.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Tenant-ID: tenant-identifier
```

**Respuesta:**

```json
{
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
```

#### Callback desde Workflow Engine

```http
POST /api/v1/orchestrator/callback/exec-12345 HTTP/1.1
Host: orchestrator.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
X-Tenant-ID: tenant-identifier

{
  "execution_id": "exec-12345",
  "workflow_id": "doc-processor-v1",
  "status": "needs_input",
  "input_request": {
    "request_id": "input-req-789",
    "prompt": "¿Desea continuar con la traducción del documento?",
    "input_type": "confirm",
    "timeout_ms": 300000
  }
}
```
## 7. Gestión de Errores

### 7.1 Estrategias de Manejo de Fallos

| Tipo de Error | Estrategia | Implementación |
|---------------|------------|----------------|
| **Timeout de Workflow** | Cancelación y notificación | El Orchestrator monitorea tiempos de ejecución y cancela workflows que exceden su timeout configurado |
| **Fallo en Paso de Workflow** | Reintentos con backoff | Pasos fallidos se reintentan hasta 3 veces con intervalos exponenciales antes de marcar el workflow como fallido |
| **Servicio Dependiente Caído** | Circuit breaker | Se implementa circuit breaker para evitar llamadas a servicios que están experimentando fallos |
| **Error de Validación** | Respuesta inmediata | Los errores de validación se reportan inmediatamente sin intentos de reintento |
| **Fallo de Comunicación** | Cola dead-letter | Los mensajes que no pueden ser procesados después de múltiples intentos se envían a una cola dead-letter para análisis |

### 7.2 Códigos de Error Específicos

| Código de Error | Descripción | Acción Recomendada |
|----------------|-------------|---------------------|
| `WFLOW_VALIDATION_001` | Error en validación de definición de workflow | Revisar la sintaxis de la definición del workflow |
| `WFLOW_EXECUTION_101` | Timeout en ejecución de workflow | Aumentar el timeout o optimizar los pasos del workflow |
| `WFLOW_EXECUTION_102` | Error en paso de workflow | Revisar logs para identificar el paso específico y su error |
| `WFLOW_SERVICE_201` | Servicio dependiente no disponible | Verificar la disponibilidad del servicio y credenciales |
| `WFLOW_INPUT_301` | Timeout esperando entrada de usuario | Configurar recordatorios o establecer valores por defecto |
| `WFLOW_PERMISSION_401` | Permisos insuficientes para ejecutar workflow | Verificar roles y permisos del usuario o servicio iniciador |

### 7.3 Ejemplo de Mensaje de Error

```json
{
  "error": {
    "code": "WFLOW_EXECUTION_102",
    "message": "Error en paso de workflow 'document_processing'",
    "details": {
      "workflow_id": "doc-processor-v1",
      "execution_id": "exec-12345",
      "step_id": "document_processing",
      "error_type": "tool_execution_failed",
      "error_details": "El documento proporcionado está dañado o en un formato no soportado",
      "timestamp": "2025-06-03T17:12:30Z",
      "retry_count": 3,
      "recommendation": "Verificar el formato del documento o intentar con un documento diferente"
    }
  }
}
```

### 7.4 Monitoreo y Alertas

El Agent Orchestrator Service implementa las siguientes métricas específicas para la comunicación con Workflow Engine Service:

| Métrica | Tipo | Propósito |
|---------|------|----------|
| `workflow_execution_duration_ms` | Histograma | Medir tiempo de ejecución de workflows |
| `workflow_step_duration_ms` | Histograma | Medir tiempo de ejecución por paso |
| `workflow_error_count` | Contador | Contar errores por tipo y workflow |
| `workflow_retry_count` | Contador | Contar reintentos por paso y workflow |
| `workflow_queue_depth` | Gauge | Monitorear profundidad de las colas de workflow |
| `workflow_active_executions` | Gauge | Monitorear workflows en ejecución |

---

## Registro de Cambios

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2025-06-03 | Equipo Nooble Backend | Versión inicial |
