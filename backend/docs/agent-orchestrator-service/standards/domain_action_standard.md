# Estándar de Comunicación Domain/Action

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo de Arquitectura Nooble*

## Descripción General

El estándar **Domain/Action** es una convención de comunicación unificada para todos los mensajes, eventos y APIs del ecosistema Nooble AI, diseñado para garantizar consistencia, trazabilidad y mantenibilidad a través de los diferentes servicios de la plataforma.

> **IMPORTANTE**: Este estándar es OBLIGATORIO para todas las comunicaciones del Agent Orchestrator Service, tanto internas entre microservicios como externas con clientes frontend.

## 1. Principios Fundamentales

### 1.1 Estructura Básica

Cada mensaje en el ecosistema debe seguir el formato Domain/Action donde:

- **Domain**: Representa el contexto o área funcional del mensaje (ej: `chat`, `session`, `workflow`)
- **Action**: Especifica la operación o evento dentro del dominio (ej: `create`, `update`, `status`)

### 1.2 Identificación de Mensajes

Todos los mensajes deben identificarse mediante:

- **Tipo**: Combinación de `{domain}.{action}` (ej: `chat.message`, `session.create`)
- **Nombres de Recursos**: Las URLs de API siguen el patrón `/api/v1/{domain}.{action}`
- **WebSocket**: Conexiones en la forma `wss://api.domain.com/ws/v1/{domain}/{session_id}`

### 1.3 Trazabilidad End-to-End

Todos los mensajes DEBEN incluir:

- **message_id**: Identificador único UUID v4 para el mensaje
- **correlation_id**: Identificador para correlacionar mensajes relacionados en flujos complejos
- **created_at**: Timestamp ISO-8601 de creación del mensaje

## 2. Estructura de Mensaje Estándar

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

### 2.1 Campos Obligatorios

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

### 2.2 Campos Opcionales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `tenant_id` | string | Identificador del tenant (obligatorio en producción) |
| `source_service` | string | Servicio de origen (ej: "agent-orchestrator") |
| `status` | object | Estado de la operación (obligatorio en respuestas) |

## 3. Catálogo de Dominios

El Agent Orchestrator Service implementa los siguientes dominios principales:

### 3.1 Dominio: `system`

Para operaciones y notificaciones a nivel de sistema.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `ping` | Verificación de conectividad | `system.ping` |
| `error` | Notificación de error | `system.error` |
| `status` | Estado del sistema | `system.status` |
| `metrics` | Métricas de rendimiento | `system.metrics` |

### 3.2 Dominio: `session`

Para gestión del ciclo de vida de sesiones.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `create` | Crear sesión | `session.create` |
| `get` | Obtener información de sesión | `session.get` |
| `list` | Listar sesiones | `session.list` |
| `update` | Actualizar sesión | `session.update` |
| `delete` | Eliminar sesión | `session.delete` |
| `sync` | Sincronizar estado | `session.sync` |

### 3.3 Dominio: `chat`

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

### 3.4 Dominio: `workflow`

Para procesamiento de flujos de trabajo por lotes.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `batch` | Iniciar batch | `workflow.batch` |
| `status` | Estado de workflow | `workflow.status` |
| `results` | Resultados de workflow | `workflow.results` |
| `cancel` | Cancelar workflow | `workflow.cancel` |
| `update` | Actualizar workflow | `workflow.update` |

### 3.5 Dominio: `tool`

Para ejecución de herramientas.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `execute` | Ejecutar herramienta | `tool.execute` |
| `result` | Resultado de herramienta | `tool.result` |
| `list` | Listar herramientas | `tool.list` |
| `register` | Registrar nueva herramienta | `tool.register` |

### 3.6 Dominio: `agent`

Para gestión de agentes IA.

| Action | Descripción | Ejemplo |
|--------|-------------|--------|
| `configure` | Configurar agente | `agent.configure` |
| `status` | Estado de agente | `agent.status` |
| `capabilities` | Capacidades del agente | `agent.capabilities` |

## 4. Convenciones de Nomenclatura

### 4.1 Dominios y Acciones

- **Dominios**: Siempre en singular y minúsculas (ej: `chat`, no `chats`)
- **Acciones**: Verbo en forma simple o sustantivo descriptivo (ej: `create`, `status`)
- **Combinación**: Siempre en formato `{dominio}.{acción}` (ej: `chat.message`)

### 4.2 URLs y Endpoints REST

- **Base**: `/api/v1/{dominio}.{acción}`
- **Recursos específicos**: `/api/v1/{dominio}.{acción}/{recurso_id}`
- **Subcategorías**: `/api/v1/{dominio}.{acción}/{recurso_id}/{subcategoría}`

### 4.3 WebSocket

- **Conexión**: `wss://api.domain.com/ws/v1/{dominio}/{session_id}`
- **Subprotocolo**: Usar `domain-action` como subprotocolo WebSocket

## 5. Headers HTTP Estándar

### 5.1 Headers de Solicitud Obligatorios 

- **`Authorization`**: Token JWT para autenticación
- **`X-Tenant-ID`**: Identificador del tenant
- **`X-Message-ID`**: UUID único para cada solicitud
- **`X-Correlation-ID`**: ID para correlacionar mensajes relacionados

### 5.2 Headers de Respuesta

- **`X-Message-ID`**: UUID del mensaje de respuesta
- **`X-Correlation-ID`**: Mismo valor enviado en la solicitud
- **`X-Request-Time`**: Tiempo de procesamiento en ms

## 6. Manejo de Errores

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

## 7. Versionado

### 7.1 Versionado de API

- Todas las APIs deben incluir versión en la URL: `/api/v1/...`
- Cambios mayores requieren nueva versión: `/api/v2/...`

### 7.2 Versionado de Esquema

- Todos los mensajes incluyen `schema_version` para compatibilidad
- Formato semántico: `MAJOR.MINOR` (ej: "1.0")

## 8. Implementación

### 8.1 Validación de Mensaje

- Implementar validación JSON Schema para todos los mensajes
- Rechazar mensajes que no cumplan con el estándar

### 8.2 Middleware de Tracking

- Recopilar `message_id` y `correlation_id` para trazabilidad
- Registrar todos los intercambios en logs estructurados

### 8.3 Cliente SDK

- Utilizar el [Cliente SDK Domain/Action](../communication/frontend/client_sdk.md) para implementaciones frontend
- Seguir [Guía de Integración Frontend](../communication/frontend/frontend_integration.md) para ejemplos completos

## 9. Ejemplos

### 9.1 Solicitud API REST

```http
POST /api/v1/chat.message HTTP/1.1
Authorization: Bearer eyJhbG...
X-Tenant-ID: tenant-123
X-Message-ID: 550e8400-e29b-41d4-a716-446655440000
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440001
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "type": {
    "domain": "chat",
    "action": "message"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:00:00Z",
  "tenant_id": "tenant-123",
  "source_service": "frontend",
  "data": {
    "session_id": "session-456",
    "content": "Hola, ¿cómo estás?",
    "content_type": "text"
  }
}
```

### 9.2 Respuesta API REST

```http
HTTP/1.1 202 Accepted
X-Message-ID: 550e8400-e29b-41d4-a716-446655440002
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440001
X-Request-Time: 35
Content-Type: application/json

{
  "message_id": "550e8400-e29b-41d4-a716-446655440002",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "type": {
    "domain": "chat",
    "action": "message_accepted"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:00:00Z",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "session-456",
    "chat_message_id": "msg-789",
    "estimated_completion_time": 8000,
    "position_in_queue": 1
  },
  "status": {
    "code": 202,
    "message": "Accepted"
  }
}
```

### 9.3 Evento WebSocket

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440003",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "type": {
    "domain": "chat",
    "action": "stream"
  },
  "schema_version": "1.0",
  "created_at": "2025-06-04T08:00:02Z",
  "tenant_id": "tenant-123",
  "source_service": "agent-orchestrator",
  "data": {
    "session_id": "session-456",
    "chat_message_id": "msg-789",
    "sequence": 1,
    "chunk": "Hola! Estoy bien,"
  }
}
```

## 10. Referencias

- [Integración Frontend](../communication/frontend/frontend_integration.md)
- [Eventos WebSocket](../communication/websocket/websocket_events.md)
- [Clasificación de Endpoints API](../api/endpoints_classification.md)
- [Matriz de Errores](../errors/error_matrix.md)

---

*Este estándar está sujeto a revisiones periódicas para garantizar su eficacia y adecuación a las necesidades del sistema.*
