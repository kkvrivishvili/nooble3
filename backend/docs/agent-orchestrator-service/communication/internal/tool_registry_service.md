# Comunicación con Tool Registry Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Visión General](#1-visión-general)
2. [Integración en Flujos de Trabajo](#2-integración-en-flujos-de-trabajo)
3. [Estructura de Colas](#3-estructura-de-colas)
4. [Formato de Mensajes](#4-formato-de-mensajes)
5. [Comunicación WebSocket](#5-comunicación-websocket)
6. [REST API](#6-rest-api)
7. [Gestión de Errores](#7-gestión-de-errores)

## 1. Visión General

El Tool Registry Service es responsable del registro, validación y ejecución de herramientas (tools) que pueden ser utilizadas por los agentes en la plataforma Nooble. Este servicio proporciona un mecanismo central para descubrir y utilizar herramientas de forma segura y controlada.

### 1.1 Principios de Comunicación

La comunicación entre el Agent Orchestrator Service y el Tool Registry Service se rige por los siguientes principios:

1. **Centralización**: El Agent Orchestrator Service actúa como punto de entrada único para todas las solicitudes de registro, descubrimiento y ejecución de herramientas.

2. **Aislamiento Multi-tenant**: Toda comunicación incluye identificación de tenant para garantizar el aislamiento de datos.

3. **Asincronía**: Las operaciones de larga duración (como validación y ejecución de herramientas externas) se procesan de forma asíncrona mediante colas.

4. **Notificaciones en Tiempo Real**: El uso de WebSockets para recibir actualizaciones inmediatas sobre el estado de ejecución de herramientas.

### 1.2 Responsabilidades del Orchestrator

En la comunicación con el Tool Registry Service, el Agent Orchestrator Service es responsable de:

1. **Enrutar solicitudes** de agentes y workflows para la ejecución de herramientas
2. **Validar permisos** de acceso a herramientas específicas
3. **Procesar resultados** de la ejecución de herramientas y reenviarlos a los servicios solicitantes
4. **Propagar eventos** de estado de herramientas a los clientes frontend
5. **Gestionar errores** y reintentos en caso de fallos

## 2. Integración en Flujos de Trabajo

### 2.1 Ejecución de Herramientas desde Agentes

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator as Agent Orchestrator
    participant AES as Agent Execution Service
    participant TRS as Tool Registry Service
    
    Cliente->>Orchestrator: Solicita ejecución con herramientas
    Orchestrator->>AES: Inicia ejecución del agente
    AES->>Orchestrator: Solicita herramientas disponibles
    Orchestrator->>TRS: get_available_tools(tenant_id, agent_id)
    TRS-->>Orchestrator: Lista de herramientas disponibles
    Orchestrator-->>AES: Herramientas disponibles
    AES->>Orchestrator: Solicita ejecutar herramienta
    Orchestrator->>TRS: execute_tool(tool_id, params)
    Note over TRS: Ejecución asíncrona
    TRS-->>Orchestrator: task_id (WebSocket)
    TRS->>TRS: Procesa herramienta
    TRS-->>Orchestrator: Notifica resultado (WebSocket)
    Orchestrator-->>AES: Resultado herramienta
    AES-->>Orchestrator: Respuesta procesada
    Orchestrator-->>Cliente: Entrega respuesta
```

### 2.2 Registro de Nueva Herramienta

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator as Agent Orchestrator
    participant TRS as Tool Registry Service
    
    Cliente->>Orchestrator: Registrar nueva herramienta
    Orchestrator->>TRS: register_tool(tool_config)
    Note over TRS: Validación asíncrona
    TRS-->>Orchestrator: registration_task_id
    TRS->>TRS: Valida configuración
    TRS->>TRS: Prueba conexión (si es API externa)
    alt Validación exitosa
        TRS-->>Orchestrator: Notifica registro completo (WebSocket)
        Orchestrator-->>Cliente: Herramienta registrada
    else Error de validación
        TRS-->>Orchestrator: Notifica error (WebSocket)
        Orchestrator-->>Cliente: Error en registro
    end
```

### 2.3 Ejecución desde Workflow

```mermaid
sequenceDiagram
    participant Orchestrator as Agent Orchestrator
    participant WES as Workflow Engine Service
    participant TRS as Tool Registry Service
    
    WES->>Orchestrator: Ejecutar paso con herramienta
    Orchestrator->>TRS: execute_tool(tool_id, params)
    TRS-->>Orchestrator: task_id
    Note over TRS: Ejecución asíncrona
    TRS->>TRS: Procesa herramienta
    TRS-->>Orchestrator: Notifica resultado (WebSocket)
    Orchestrator-->>WES: Resultado herramienta
    WES->>WES: Continúa workflow
```

## 3. Estructura de Colas

El Agent Orchestrator Service produce y consume varias colas Redis para la comunicación con el Tool Registry Service. Estas colas gestionan operaciones asíncronas relacionadas con herramientas.

### 3.1 Colas que Produce el Orchestrator

| Cola | Propósito | Formato | Consumidor |
|------|----------|---------|------------|
| `tool_execution:{tenant_id}` | Solicitudes de ejecución de herramientas | [ToolExecutionMessage](#41-toolexecutionmessage) | Tool Registry Service |
| `tool_registration:{tenant_id}` | Registro de nuevas herramientas | [ToolRegistrationMessage](#42-toolregistrationmessage) | Tool Registry Service |
| `tool_discovery:{tenant_id}` | Descubrimiento de herramientas disponibles | [ToolDiscoveryMessage](#43-tooldiscoverymessage) | Tool Registry Service |

### 3.2 Colas que Consume el Orchestrator

| Cola | Propósito | Formato | Productor |
|------|----------|---------|-----------|
| `orchestrator_callbacks:{tenant_id}` | Resultados de ejecución de herramientas | [ToolResultMessage](#44-toolresultmessage) | Tool Registry Service |

## 4. Formato de Mensajes

### 4.1 Estructura Base de Mensajes

Todos los mensajes intercambiados entre Agent Orchestrator Service y Tool Registry Service siguen esta estructura base:

```json
{
  "message_id": "uuid-v4",           // ID único del mensaje
  "tenant_id": "tenant-identifier",  // ID del tenant 
  "timestamp": "ISO-8601-datetime",  // Momento de creación
  "version": "1.0",                  // Versión del formato
  "type": "request|response|event",  // Tipo de mensaje
  "source": "orchestrator",          // Servicio origen
  "destination": "tool-registry",    // Servicio destino
  "correlation_id": "uuid-v4",       // ID de correlación
  "task_id": "uuid-v4",              // ID único de la tarea
  "session_id": "session-id",        // ID de la sesión (si aplica)
  "status": "pending|completed|failed", // Estado
  "priority": 0-9,                   // Prioridad (0-9)
  "payload": {}                      // Datos específicos
}
```

### 4.2 ToolExecutionMessage

El Agent Orchestrator Service envía este mensaje para solicitar la ejecución de una herramienta.

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:05:23Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "tool-registry",
  "correlation_id": "session-correlation-id",
  "task_id": "uuid-v4",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 2,
  "metadata": {
    "source_request_id": "original-request-id",
    "user_id": "user-identifier",
    "timeout_ms": 30000
  },
  "payload": {
    "operation": "execute_tool",
    "tool_id": "weather-api-tool",
    "parameters": {
      "city": "Madrid",
      "units": "metric"
    },
    "execution_context": {
      "agent_id": "customer-support-agent",
      "user_query": "Cómo estará el tiempo hoy en Madrid?"
    }
  }
}
```

### 4.3 ToolRegistrationMessage

El Agent Orchestrator Service envía este mensaje para registrar una nueva herramienta en el catálogo.

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T16:42:15Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "tool-registry",
  "correlation_id": "admin-operation-id",
  "task_id": "uuid-v4",
  "status": "pending",
  "priority": 1,
  "metadata": {
    "source_request_id": "admin-api-request",
    "user_id": "admin-identifier",
    "timeout_ms": 10000
  },
  "payload": {
    "operation": "register_tool",
    "tool": {
      "name": "Weather API Tool",
      "id": "weather-api-tool",
      "description": "Obtiene datos meteorológicos actuales y pronósticos",
      "version": "1.0.0",
      "schema": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string",
            "description": "Ciudad para la consulta meteorológica"
          },
          "units": {
            "type": "string",
            "enum": ["metric", "imperial"],
            "default": "metric"
          }
        },
        "required": ["city"]
      },
      "authentication": {
        "type": "api_key",
        "header_name": "X-API-Key"
      },
      "category": "information_retrieval",
      "tags": ["weather", "forecast"],
      "timeout_ms": 15000
    }
  }
}
```

### 4.4 ToolDiscoveryMessage

Mensaje enviado por el Agent Orchestrator Service para consultar herramientas disponibles para un tenant.

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:01:08Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "tool-registry",
  "correlation_id": "agent-execution-correlation-id",
  "task_id": "uuid-v4",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 1,
  "metadata": {
    "source_request_id": "agent-execution-request",
    "user_id": "user-identifier",
    "timeout_ms": 5000
  },
  "payload": {
    "operation": "discover_tools",
    "query": "weather",
    "limit": 10,
    "categories": ["information_retrieval"],
    "include_schemas": true
  }
}
```

### 4.5 ToolResultMessage

Mensaje enviado por el Tool Registry Service al Orchestrator con los resultados de la ejecución.

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:10:05Z",
  "version": "1.0",
  "type": "response",
  "source": "tool-registry",
  "destination": "orchestrator",
  "correlation_id": "session-correlation-id",
  "task_id": "result-task-uuid",
  "session_id": "session-identifier",
  "status": "completed",
  "priority": 2,
  "metadata": {
    "source_task_id": "original-task-id",
    "execution_time_ms": 1253
  },
  "payload": {
    "operation": "tool_result",
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "result": {
      "temperature": 22.5,
      "humidity": 45,
      "conditions": "Parcialmente nublado",
      "forecast": [
        {
          "day": "tomorrow",
          "temperature": 24.0,
          "conditions": "Soleado"
        }
      ]
    }
  }
}
```

### 4.6 ToolErrorMessage

Mensaje enviado por el Tool Registry Service al Orchestrator para notificar errores en la ejecución.

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:06:28Z",
  "version": "1.0",
  "type": "response",
  "source": "tool-registry",
  "destination": "orchestrator",
  "correlation_id": "session-correlation-id",
  "task_id": "error-task-uuid",
  "session_id": "session-identifier",
  "status": "failed",
  "priority": 2,
  "metadata": {
    "source_task_id": "original-task-id",
    "execution_time_ms": 532
  },
  "payload": {
    "operation": "tool_error",
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "error": {
      "code": "TOOL_API_RATE_LIMIT",
      "message": "API rate limit exceeded",
      "type": "ExternalAPIError",
      "details": {
        "status_code": 429,
        "retry_after": 60,
        "retryable": true
      }
    }
  }
}
```

## 5. Comunicación WebSocket

El Agent Orchestrator Service se suscribe a eventos del Tool Registry Service a través de WebSockets para recibir actualizaciones en tiempo real sobre el estado de ejecución de las herramientas.

### 5.1 Eventos Emitidos por el Tool Registry

| Evento | Descripción | Payload | Destinatario |
|--------|------------|---------|-------------|
| `tool.progress` | Actualiza el estado de ejecución | [ToolProgressEvent](#51-toolprogressevent) | Orchestrator |
| `tool.completed` | Notifica ejecución exitosa | [ToolCompletedEvent](#52-toolcompletedevent) | Orchestrator |
| `tool.failed` | Notifica error en ejecución | [ToolFailedEvent](#53-toolfailedevent) | Orchestrator |

### 5.2 Formato de Eventos

<a id="51-toolprogressevent"></a>
#### 5.1 ToolProgressEvent

```json
{
  "event": "tool.progress",
  "service": "tool-registry",
  "task_id": "task-uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:10:02Z",
  "data": {
    "status": "processing",
    "progress": 25,
    "details": {
      "tool_id": "weather-api-tool",
      "message": "Ejecución de herramienta iniciada"
    }
  }
}
```

<a id="52-toolcompletedevent"></a>
#### 5.2 ToolCompletedEvent

```json
{
  "event": "tool.completed",
  "service": "tool-registry",
  "task_id": "task-uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:10:05Z",
  "data": {
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "result": {
      "temperature": 22.5,
      "humidity": 45,
      "conditions": "Parcialmente nublado"
    },
    "execution_time_ms": 3245
  }
}
```

<a id="53-toolfailedevent"></a>
#### 5.3 ToolFailedEvent

```json
{
  "event": "tool.failed",
  "service": "tool-registry",
  "task_id": "task-uuid-v4",
  "correlation_id": "orchestrator-task-id",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T17:10:05Z",
  "data": {
    "tool_id": "weather-api-tool",
    "error": {
      "code": "TOOL_API_RATE_LIMIT",
      "message": "API rate limit exceeded",
      "error_type": "RateLimitError",
      "retryable": true
    }
  }
}
```

## 6. REST API

### 6.1 APIs que Consume el Orchestrator

| Endpoint | Método HTTP | Propósito | Formato de Respuesta |
|----------|------------|-----------|---------------------|
| `/api/v1/tools` | `GET` | Listar herramientas disponibles | Lista de ToolSummary |
| `/api/v1/tools/{tool_id}` | `GET` | Obtener detalles de herramienta | ToolDetail |
| `/api/v1/tools/execute` | `POST` | Ejecutar herramienta sincrónica | ToolExecutionResult |
| `/api/v1/tools/async-execute` | `POST` | Ejecutar herramienta asincrónica | TaskID |

### 6.2 APIs que Expone el Orchestrator para el Tool Registry

| Endpoint | Método HTTP | Propósito | Formato de Respuesta |
|----------|------------|-----------|---------------------|
| `/api/v1/orchestrator/tasks/{task_id}/callback` | `POST` | Recibir resultados de ejecución | CallbackResponse |
| `/api/v1/orchestrator/service-auth/validate` | `POST` | Validar autenticación de servicio | ValidationResult |

### 6.3 Ejemplos de Llamadas

#### Ejecución Sincrónica de Herramienta

```http
POST /api/v1/tools/execute HTTP/1.1
Host: tool-registry.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
X-Tenant-ID: tenant-identifier

{
  "tool_id": "calculator-v1",
  "parameters": {
    "expression": "2*(3+4)"
  },
  "metadata": {
    "agent_id": "math-tutor",
    "session_id": "session-123",
    "execution_id": "exec-456"
  }
}
```

**Respuesta:**

```json
{
  "task_id": "task-789",
  "status": "completed",
  "result": {
    "value": 14,
    "formatted_value": "14",
    "execution_time_ms": 25
  }
}
```

#### Solicitud de Herramientas Disponibles

```http
GET /api/v1/tools?agent_id=research-assistant&types=rag,external_api HTTP/1.1
Host: tool-registry.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Tenant-ID: tenant-identifier
```

**Respuesta:**

```json
{
  "tools": [
    {
      "tool_id": "document-search",
      "tool_name": "Buscador de Documentos",
      "tool_type": "rag",
      "description": "Busca información en documentos del usuario",
      "version": "2.1.0",
      "parameters_schema": {
        "query": {
          "type": "string",
          "required": true,
          "description": "Consulta de búsqueda"
        },
        "limit": {
          "type": "integer",
          "required": false,
          "default": 5
        }
      }
    },
    {
      "tool_id": "weather-api",
      "tool_name": "Weather API",
      "tool_type": "external_api",
      "description": "Obtiene información meteorológica actualizada",
      "version": "1.0.0",
      "parameters_schema": {
        "location": {
          "type": "string",
          "required": true,
          "description": "Ciudad o coordenadas"
        },
        "units": {
          "type": "string",
          "required": false,
          "default": "metric",
          "enum": ["metric", "imperial"]
        }
      }
    }
  ],
  "pagination": {
    "total": 2,
    "page": 1,
    "limit": 20
  }
}
```

## 7. Gestión de Errores

### 7.1 Estrategias de Manejo de Fallos

| Tipo de Error | Estrategia | Implementación |
|---------------|------------|----------------|
| **Error en API Externa** | Reintentos configurables | El Orchestrator reintenta la ejecución de herramientas con problemas temporales |
| **Timeout de Herramienta** | Cancelación | Las herramientas que excedan su tiempo límite se cancelan y reportan error |
| **Permisos Insuficientes** | Validación previa | Se validan permisos antes de solicitar ejecución de herramienta |
| **Error en Parámetros** | Validación de esquema | Validación de estructura y tipos antes de enviar a ejecución |
| **Herramienta no Disponible** | Fallback | Se implementan mecanismos de herramientas alternativas cuando sea posible |

### 7.2 Códigos de Error Específicos

| Código de Error | Descripción | Acción Recomendada |
|----------------|-------------|---------------------|
| `TOOL_NOT_FOUND` | Herramienta solicitada no encontrada | Verificar ID de herramienta y disponibilidad |
| `TOOL_EXECUTION_TIMEOUT` | Timeout en ejecución de herramienta | Ajustar parámetros o aumentar timeout |
| `TOOL_PERMISSION_DENIED` | Permisos insuficientes para usar herramienta | Verificar configuración de permisos |
| `TOOL_INVALID_PARAMETERS` | Parámetros inválidos para la herramienta | Revisar documentación y formato de parámetros |
| `TOOL_EXTERNAL_ERROR` | Error en servicio externo usado por herramienta | Verificar estado del servicio externo |
| `TOOL_RATE_LIMITED` | Límite de tasa excedido | Implementar backoff o reducir frecuencia de llamadas |

### 7.3 Monitoreo y Alertas

El Agent Orchestrator Service implementa las siguientes métricas específicas para la comunicación con Tool Registry Service:

| Métrica | Tipo | Propósito |
|---------|------|----------|
| `tool_execution_duration_ms` | Histograma | Medir tiempo de ejecución de herramientas |
| `tool_execution_success_rate` | Gauge | Monitorear tasa de éxito de ejecuciones |
| `tool_execution_error_count` | Contador | Contar errores por tipo y herramienta |
| `tool_registry_queue_depth` | Gauge | Monitorear profundidad de las colas |

---

## Registro de Cambios

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2025-06-03 | Equipo Nooble Backend | Versión inicial |
