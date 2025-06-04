# Estándar de Comunicación Domain/Action

*Versión: 2.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo de Arquitectura Nooble*

## Índice
- [Estándar de Comunicación Domain/Action](#estándar-de-comunicación-domainaction)
  - [1. Descripción General](#1-descripción-general)
  - [2. Principios Fundamentales](#2-principios-fundamentales)
  - [3. Estructura de Mensaje Estándar](#3-estructura-de-mensaje-estándar)
  - [4. Catálogo de Dominios](#4-catálogo-de-dominios)
  - [5. Convenciones de Nomenclatura](#5-convenciones-de-nomenclatura)
  - [6. Headers HTTP Estándar](#6-headers-http-estándar)
  - [7. Manejo de Errores](#7-manejo-de-errores)
  - [8. Versionado](#8-versionado)
  - [9. Implementación](#9-implementación)
  - [10. Eventos WebSocket](#10-eventos-websocket)
  - [11. API REST y Endpoints](#11-api-rest-y-endpoints)
  - [12. Referencias e Integraciones](#12-referencias-e-integraciones)

## 1. Descripción General

El estándar **Domain/Action** es una convención de comunicación unificada para todos los mensajes, eventos y APIs del ecosistema Nooble AI, diseñado para garantizar consistencia, trazabilidad y mantenibilidad a través de los diferentes servicios de la plataforma.

> **IMPORTANTE**: Este estándar es OBLIGATORIO para todas las comunicaciones del Agent Orchestrator Service, tanto internas entre microservicios como externas con clientes frontend.

## 2. Principios Fundamentales

### 2.1 Estructura Básica

Cada mensaje en el ecosistema debe seguir el formato Domain/Action donde:

- **Domain**: Representa el contexto o área funcional del mensaje (ej: `chat`, `session`, `workflow`)
- **Action**: Especifica la operación o evento dentro del dominio (ej: `create`, `update`, `status`)

### 2.2 Identificación de Mensajes

Todos los mensajes deben identificarse mediante:

- **Tipo**: Combinación de `{domain}.{action}` (ej: `chat.message`, `session.create`)
- **Nombres de Recursos**: Las URLs de API siguen el patrón `/api/v1/{domain}.{action}`
- **WebSocket**: Conexiones en la forma `wss://api.domain.com/ws/v1/{domain}/{session_id}`

### 2.3 Trazabilidad End-to-End

Todos los mensajes DEBEN incluir:

- **message_id**: Identificador único UUID v4 para el mensaje
- **correlation_id**: Identificador para correlacionar mensajes relacionados en flujos complejos
- **created_at**: Timestamp ISO-8601 de creación del mensaje

## 3. Estructura de Mensaje Estándar

Todos los mensajes Domain/Action utilizan esta estructura JSON estándar:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "string",
    "action": "string"
  },
  "schema_version": "string",
  "created_at": "ISO-8601",
  "tenant_id": "string",
  "source_service": "string",
  "data": {
    // Payload específico del mensaje
  },
  "status": {
    "code": 200,
    "message": "string"
  }
}
```

### 3.1 Campos Obligatorios

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `message_id` | string (UUID v4) | Identificador único del mensaje |
| `correlation_id` | string (UUID v4) | ID para correlacionar mensajes relacionados |
| `type` | object | Objeto con domain y action |
| `type.domain` | string | Dominio funcional del mensaje |
| `type.action` | string | Acción específica dentro del dominio |
| `schema_version` | string | Versión del esquema (ej: "1.0") |
| `created_at` | string (ISO-8601) | Timestamp de creación |
| `data` | object | Payload específico del mensaje |

### 3.2 Campos Opcionales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `tenant_id` | string | Identificador del tenant (obligatorio en producción) |
| `source_service` | string | Servicio de origen (ej: "agent-orchestrator") |
| `status` | object | Estado de la operación (obligatorio en respuestas) |

## 4. Catálogo de Dominios

El Agent Orchestrator Service implementa los siguientes dominios principales:

### 4.1 Dominio: `system`

Para operaciones y notificaciones a nivel de sistema.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `ping` | Verificación de conectividad | `system.ping` |
| `error` | Notificación de error | `system.error` |
| `status` | Estado del sistema | `system.status` |
| `metrics` | Métricas de rendimiento | `system.metrics` |

### 4.2 Dominio: `session`

Para gestión del ciclo de vida de sesiones.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `create` | Crear sesión | `session.create` |
| `get` | Obtener información de sesión | `session.get` |
| `list` | Listar sesiones | `session.list` |
| `update` | Actualizar sesión | `session.update` |
| `delete` | Eliminar sesión | `session.delete` |
| `sync` | Sincronizar estado | `session.sync` |

### 4.3 Dominio: `chat`

Para mensajería y conversaciones.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `message` | Envío de mensaje | `chat.message` |
| `response` | Respuesta completa | `chat.response` |
| `stream` | Chunk de respuesta streaming | `chat.stream` |
| `status` | Estado de procesamiento | `chat.status` |
| `cancel` | Cancelar procesamiento | `chat.cancel` |
| `history` | Historial de mensajes | `chat.history` |
| `message_accepted` | Confirmación de recepción | `chat.message_accepted` |

### 4.4 Dominio: `workflow`

Para procesamiento de flujos de trabajo por lotes.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `batch` | Iniciar batch | `workflow.batch` |
| `status` | Estado de workflow | `workflow.status` |
| `results` | Resultados de workflow | `workflow.results` |
| `cancel` | Cancelar workflow | `workflow.cancel` |
| `update` | Actualizar workflow | `workflow.update` |

### 4.5 Dominio: `tool`

Para ejecución de herramientas.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `execute` | Ejecutar herramienta | `tool.execute` |
| `result` | Resultado de herramienta | `tool.result` |
| `list` | Listar herramientas | `tool.list` |
| `register` | Registrar nueva herramienta | `tool.register` |

### 4.6 Dominio: `agent`

Para gestión de agentes IA.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `configure` | Configurar agente | `agent.configure` |
| `status` | Estado de agente | `agent.status` |
| `capabilities` | Capacidades del agente | `agent.capabilities` |

## 5. Convenciones de Nomenclatura

### 5.1 Dominios y Acciones

- **Dominios**: Siempre en singular y minúsculas (ej: `chat`, no `chats`)
- **Acciones**: Verbo en forma simple o sustantivo descriptivo (ej: `create`, `status`)
- **Combinación**: Siempre en formato `{dominio}.{acción}` (ej: `chat.message`)

### 5.2 URLs y Endpoints REST

- **Base**: `/api/v1/{dominio}.{acción}`
- **Recursos específicos**: `/api/v1/{dominio}.{acción}/{recurso_id}`
- **Subcategorías**: `/api/v1/{dominio}.{acción}/{recurso_id}/{subcategoría}`

### 5.3 WebSocket

- **Conexión**: `wss://api.domain.com/ws/v1/{dominio}/{session_id}`
- **Subprotocolo**: Usar `domain-action` como subprotocolo WebSocket

## 6. Headers HTTP Estándar

### 6.1 Headers de Solicitud Obligatorios 

- **`Authorization`**: Token JWT para autenticación
- **`X-Tenant-ID`**: Identificador del tenant
- **`X-Message-ID`**: UUID único para cada solicitud
- **`X-Correlation-ID`**: ID para correlacionar mensajes relacionados

### 6.2 Headers de Respuesta

- **`X-Message-ID`**: UUID del mensaje de respuesta
- **`X-Correlation-ID`**: Mismo valor enviado en la solicitud
- **`X-Request-Time`**: Tiempo de procesamiento en ms

## 7. Manejo de Errores

Los errores siguen el mismo estándar Domain/Action como `{domain}.error` o `system.error`:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4", 
  "type": {
    "domain": "system", 
    "action": "error"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-uuid",
  "source_service": "agent-orchestrator",
  "data": {
    "code": "ERROR_CODE",
    "message": "Mensaje descriptivo del error",
    "details": { ... }
  },
  "status": {
    "code": 400,
    "message": "Bad Request"
  }
}
```

### 7.1 Códigos de Error HTTP

Se utilizan códigos de error HTTP estándar:

| Código | Descripción | Uso |
|--------|------------|-----|
| 400 | Bad Request | Error en parámetros o formato de mensaje |
| 401 | Unauthorized | Autenticación inválida o faltante |
| 403 | Forbidden | Sin permisos para la operación solicitada |
| 404 | Not Found | Recurso no encontrado |
| 409 | Conflict | Estado de recurso conflictivo |
| 422 | Unprocessable Entity | Datos de solicitud inválidos |
| 429 | Too Many Requests | Límite de tasa excedido |
| 500 | Internal Server Error | Error interno del servidor |
| 503 | Service Unavailable | Servicio no disponible temporalmente |

## 8. Versionado

### 8.1 Versionado de API

- Todas las APIs deben incluir versión en la URL: `/api/v1/...`
- Cambios mayores requieren nueva versión: `/api/v2/...`

### 8.2 Versionado de Esquema

- Todos los mensajes incluyen `schema_version` para compatibilidad
- Formato semántico: `MAJOR.MINOR` (ej: "1.0")

## 9. Implementación

### 9.1 Validación de Mensaje

- Implementar validación JSON Schema para todos los mensajes
- Rechazar mensajes que no cumplan con el estándar

### 9.2 Middleware de Tracking

- Recopilar `message_id` y `correlation_id` para trazabilidad
- Registrar todos los intercambios en logs estructurados

## 10. Eventos WebSocket

Los eventos WebSocket siguen el estándar Domain/Action igual que las APIs REST, pero con un enfoque orientado a comunicación en tiempo real.

### 10.1 Eventos Principales de Servidor a Cliente

#### Evento: chat.stream

Evento para transmisión en tiempo real (streaming) del contenido generado.

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
  "tenant_id": "tenant-123",
  "source_service": "agent-execution-service",
  "data": {
    "chunk": "fragmento de texto",
    "is_final": false,
    "parent_message_id": "uuid-v4",
    "sequence_number": 5
  }
}
```

#### Evento: chat.completed

Evento emitido cuando un mensaje ha sido completamente procesado.

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "completed"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "content": "Contenido completo de la respuesta",
    "content_type": "text",
    "sources": [],
    "processing_time_ms": 1200,
    "token_count": 250
  }
}
```

#### Evento: tool.execute

Evento para solicitar la ejecución de una herramienta al cliente.

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
  "tenant_id": "tenant-123",
  "source_service": "agent-execution-service",
  "data": {
    "tool_call_id": "uuid-v4",
    "parent_message_id": "uuid-v4",
    "tool_id": "nombre-herramienta",
    "params": {
      "param1": "valor1",
      "param2": "valor2"
    },
    "timeout_ms": 30000
  }
}
```

#### Evento: system.error

Evento para notificar errores.

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "system",
    "action": "error"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "code": "ERROR_CODE",
    "message": "Descripción del error",
    "details": {
      "component": "agent-execution",
      "trace_id": "uuid-v4"
    }
  },
  "status": {
    "code": 500,
    "message": "Internal Server Error"
  }
}
```

### 10.2 Eventos Principales de Cliente a Servidor

#### Evento: workflow.cancel

Evento para cancelar un workflow en ejecución.

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "workflow",
    "action": "cancel"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "frontend",
  "data": {
    "workflow_id": "uuid-v4"
  }
}
```

#### Evento: tool.result

Evento para enviar el resultado de una ejecución de herramienta.

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "tenant_id": "tenant-123",
  "source_service": "frontend",
  "data": {
    "tool_call_id": "uuid-v4",
    "status": "success",
    "result": {
      // Resultado específico de la herramienta
    }
  }
}
```

### 10.3 Gestión de Estados y Reconexión

- Cada cliente debe implementar reconexión automática con retroceso exponencial
- Al reconectar, solicitar sincronización de estado mediante `session.sync`
- Mantener heartbeats con `system.ping` para detectar desconexiones

## 11. API REST y Endpoints

Los endpoints API REST siguen el estándar Domain/Action para mantener la consistencia con el resto del sistema.

### 11.1 Convenciones de Endpoints

| Tipo de Endpoint | Formato de Path | Ejemplo |
|-----------------|----------------|--------|
| Frontend (Público) | `/api/v{n}/{domain}.{action}` | `/api/v1/chat.message` |
| Interno (Servicio) | `/internal/v{n}/{domain}.{action}` | `/internal/v1/workflow.execute` |
| WebSocket | `/ws/v{n}/{domain}` | `/ws/v1/chat/{session_id}` |
| Salud y Diagnóstico | `/health/{check}`, `/metrics` | `/health/ready` |

### 11.2 Ejemplo: Crear sesión (session.create)

**Solicitud:**

```http
POST /api/v1/session.create HTTP/1.1
Authorization: Bearer eyJhbG...
X-Tenant-ID: tenant-123
X-Message-ID: 550e8400-e29b-41d4-a716-446655440000
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440001
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "type": {
    "domain": "session",
    "action": "create"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:00:00Z",
  "tenant_id": "tenant-123",
  "source_service": "frontend",
  "data": {
    "user_id": "user-456",
    "agent_id": "agent-789",
    "metadata": {
      "client_version": "3.2.1",
      "user_timezone": "America/Santiago"
    }
  }
}
```

**Respuesta:**

```http
HTTP/1.1 201 Created
X-Message-ID: 550e8400-e29b-41d4-a716-446655440002
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440001
X-Request-Time: 45
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440002",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "type": {
    "domain": "session",
    "action": "created"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:00:00Z",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "session-abc123",
    "created_at": "2025-06-04T08:00:00Z",
    "status": "active",
    "agent_id": "agent-789",
    "websocket_url": "wss://api.nooble.ai/ws/v1/chat/session-abc123"
  },
  "status": {
    "code": 201,
    "message": "Created"
  }
}
```

### 11.3 Ejemplo: Enviar mensaje (chat.message)

**Solicitud:**

```http
POST /api/v1/chat.message HTTP/1.1
Authorization: Bearer eyJhbG...
X-Tenant-ID: tenant-123
X-Message-ID: 550e8400-e29b-41d4-a716-446655440003
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440004
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440003",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440004",
  "type": {
    "domain": "chat",
    "action": "message"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:05:00Z",
  "tenant_id": "tenant-123",
  "source_service": "frontend",
  "data": {
    "session_id": "session-abc123",
    "content": "Hola, ¿cómo estás?",
    "content_type": "text"
  }
}
```

**Respuesta:**

```http
HTTP/1.1 202 Accepted
X-Message-ID: 550e8400-e29b-41d4-a716-446655440005
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440004
X-Request-Time: 35
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440005",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440004",
  "type": {
    "domain": "chat",
    "action": "message_accepted"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:05:00Z",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "session-abc123",
    "chat_message_id": "msg-def456",
    "estimated_completion_time": 8000,
    "position_in_queue": 1
  },
  "status": {
    "code": 202,
    "message": "Accepted"
  }
}
```

## 12. Referencias e Integraciones

Este documento consolida la información del estándar Domain/Action que antes se encontraba distribuida en múltiples archivos. Para implementaciones específicas, consulte:

- [Detalles de Implementación Frontend](../communication/frontend/frontend_integration.md)
- [SDK Cliente](../communication/frontend/client_sdk.md)
- [Protocolos de Comunicación Interna](../communication/internal/internal_communication.md)
- [Matriz de Errores](../errors/error_matrix.md)

---

*Este estándar está sujeto a revisiones periódicas para garantizar su eficacia y adecuación a las necesidades del sistema.*
