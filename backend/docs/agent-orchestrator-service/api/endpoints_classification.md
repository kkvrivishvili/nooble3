# Clasificación de Endpoints API del Agent Orchestrator Service

*Versión: 2.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

> **IMPORTANTE**: El estándar Domain/Action se ha consolidado en [domain_action.md](../standards/domain_action.md).  
> Por favor, consulte la sección [11. API REST y Endpoints](../standards/domain_action.md#11-api-rest-y-endpoints) para los principios generales y convenciones de nomenclatura.

## Introducción

Este documento complementa el estándar Domain/Action con detalles específicos sobre la clasificación y catalogación de los endpoints API REST implementados en el Agent Orchestrator Service.

## Índice
- [Clasificación de Endpoints API del Agent Orchestrator Service](#clasificación-de-endpoints-api-del-agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Convenciones de Nomenclatura](#2-convenciones-de-nomenclatura)
  - [3. Endpoints Frontend (Públicos)](#3-endpoints-frontend-públicos)
    - [3.1 Gestión de Sesiones](#31-gestión-de-sesiones)
    - [3.2 Comunicación en Chat](#32-comunicación-en-chat)
    - [3.3 WebSocket](#33-websocket)
    - [3.4 Tareas Asíncronas](#34-tareas-asíncronas)
    - [3.5 Configuración de Agentes](#35-configuración-de-agentes)
  - [4. Endpoints de Servicio (Internos)](#4-endpoints-de-servicio-internos)
    - [4.1 Comunicación Inter-Servicio](#41-comunicación-inter-servicio)
    - [4.2 Gestión de Estado](#42-gestión-de-estado)
    - [4.3 Webhooks de Servicio](#43-webhooks-de-servicio)
    - [4.4 Monitoreo y Diagnóstico](#44-monitoreo-y-diagnóstico)
  - [5. Autenticación y Autorización](#5-autenticación-y-autorización)
  - [6. Versionado de API](#6-versionado-de-api)
  - [7. Ejemplos de Uso](#7-ejemplos-de-uso)

## 1. Introducción

Este documento complementa el estándar Domain/Action con detalles específicos sobre la clasificación y catalogación de los endpoints API REST implementados en el Agent Orchestrator Service. asegura trazabilidad, consistencia y facilita el mantenimiento de la API.

## 2. Convenciones de Nomenclatura con Estándar Domain/Action

### Estructura Base de Endpoints

Todos los endpoints siguen la estructura domain/action en su URL:

| Tipo de Endpoint | Formato de Path | Ejemplo |
|-----------------|----------------|---------|  
| Frontend (Público) | `/api/v{n}/{domain}.{action}` | `/api/v1/chat.message` |
| Interno (Servicio) | `/internal/v{n}/{domain}.{action}` | `/internal/v1/workflow.execute` |
| WebSocket | `/ws/v{n}/{domain}` | `/ws/v1/chat/{session_id}` |
| Salud y Diagnóstico | `/health/{check}`, `/metrics` | `/health/ready` |

### Dominios Principales y sus Endpoints

| Dominio | Descripción | Ejemplos de Endpoints |
|---------|-------------|---------------------|
| `session` | Gestión de sesiones | `/api/v1/session.create`, `/api/v1/session.close` |
| `chat` | Interacciones conversacionales | `/api/v1/chat.send`, `/api/v1/chat.history` |
| `workflow` | Flujos de trabajo | `/api/v1/workflow.execute`, `/api/v1/workflow.status` |
| `agent` | Operaciones con agentes | `/api/v1/agent.configure`, `/api/v1/agent.list` |
| `tool` | Herramientas y extensiones | `/api/v1/tool.register`, `/api/v1/tool.execute` |
| `system` | Operaciones del sistema | `/api/v1/system.status`, `/api/v1/system.config` |

### Convención para Parámetros REST

- IDs de recursos siempre como path params: `/api/v1/session.get/{session_id}`
- Filtros y opciones como query params: `/api/v1/chat.history?limit=10&offset=0`
- Solicitudes POST/PUT incluyen en el body la estructura domain/action completa:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "message"
  },
  "schema_version": "1.0",
  "data": {
    "session_id": "uuid-v4",
    "content": "Mensaje de usuario",
    "metadata": {}
  }
}
```

### Headers Estándar

Todos los endpoints requieren estos headers estándar:

```
Authorization: Bearer {jwt_token}
X-Tenant-ID: {tenant_id}
X-Message-ID: {message_id}
X-Correlation-ID: {correlation_id}
X-Request-Priority: {0-9}
Content-Type: application/json
```

## 3. Endpoints Frontend (Públicos) con Domain/Action

Endpoints expuestos para uso directo por aplicaciones frontend, organizados por dominio funcional.

### 3.1 Dominio: Session

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/api/v1/session.create` | create | Crear nueva sesión | JWT |
| GET | `/api/v1/session.get/{session_id}` | get | Obtener detalles de sesión | JWT |
| GET | `/api/v1/session.list` | list | Listar sesiones del usuario | JWT |
| PUT | `/api/v1/session.update/{session_id}` | update | Actualizar estado o configuración | JWT |
| PUT | `/api/v1/session.pause/{session_id}` | pause | Pausar sesión activa | JWT |
| PUT | `/api/v1/session.resume/{session_id}` | resume | Reanudar sesión pausada | JWT |
| DELETE | `/api/v1/session.close/{session_id}` | close | Terminar sesión | JWT |

### 3.2 Dominio: Chat

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/api/v1/chat.message` | message | Enviar mensaje | JWT |
| GET | `/api/v1/chat.history/{session_id}` | history | Obtener historial de mensajes | JWT |
| DELETE | `/api/v1/chat.delete/{message_id}` | delete | Eliminar mensaje | JWT |
| POST | `/api/v1/chat.cancel/{message_id}` | cancel | Cancelar procesamiento | JWT |
| GET | `/api/v1/chat.summary/{session_id}` | summary | Obtener resumen de conversación | JWT |

### 3.3 Dominio: WebSocket

| Método | Path | Descripción | Autenticación |
|--------|------|------------|---------------|
| WebSocket | `/ws/v1/chat/{session_id}` | Conexión WebSocket para chat | JWT |
| WebSocket | `/ws/v1/workflow/{task_id}` | Conexión WebSocket para workflows | JWT |

### 3.4 Dominio: Workflow

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/api/v1/workflow.execute` | execute | Ejecutar workflow o tarea | JWT |
| POST | `/api/v1/workflow.batch` | batch | Crear nueva tarea por lotes | JWT |
| GET | `/api/v1/workflow.status/{workflow_id}` | status | Verificar estado de workflow | JWT |
| DELETE | `/api/v1/workflow.cancel/{workflow_id}` | cancel | Cancelar workflow | JWT |
| GET | `/api/v1/workflow.results/{workflow_id}` | results | Obtener resultados | JWT |

### 3.5 Dominio: Agent

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| GET | `/api/v1/agent.list` | list | Listar agentes disponibles | JWT |
| GET | `/api/v1/agent.get/{agent_id}` | get | Obtener configuración | JWT |
| PUT | `/api/v1/agent.assign/{session_id}` | assign | Asignar agente a sesión | JWT |
| POST | `/api/v1/agent.feedback` | feedback | Enviar feedback sobre agente | JWT |

## 4. Endpoints de Servicio (Internos) con Domain/Action

Endpoints para comunicación exclusiva entre servicios del backend, organizados por dominio funcional.

### 4.1 Dominio: Workflow (Interno)

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/internal/v1/workflow.register` | register | Registrar nuevo workflow | API Key + mTLS |
| PUT | `/internal/v1/workflow.update/{workflow_id}` | update | Actualizar estado del workflow | API Key + mTLS |
| GET | `/internal/v1/workflow.status/{workflow_id}` | status | Consultar estado de workflow | API Key + mTLS |
| POST | `/internal/v1/workflow.complete/{workflow_id}` | complete | Marcar workflow como completado | API Key + mTLS |
| POST | `/internal/v1/workflow.results/{workflow_id}` | results | Enviar resultados de workflow | API Key + mTLS |

### 4.2 Dominio: Notification

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/internal/v1/notification.send` | send | Enviar notificación a cliente | API Key + mTLS |
| GET | `/internal/v1/notification.pending/{user_id}` | pending | Obtener notificaciones pendientes | API Key + mTLS |
| PUT | `/internal/v1/notification.acknowledge/{notification_id}` | acknowledge | Confirmar recepción de notificación | API Key + mTLS |

### 4.3 Dominio: Orchestrator

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/internal/v1/orchestrator.register_session` | register_session | Registrar nueva sesión | API Key + mTLS |
| GET | `/internal/v1/orchestrator.load` | load | Obtener carga actual | API Key + mTLS |
| POST | `/internal/v1/orchestrator.register_agent_load` | register_agent_load | Registrar carga de agente | API Key + mTLS |
| POST | `/internal/v1/orchestrator.heartbeat` | heartbeat | Enviar señal de vida | API Key + mTLS |

### 4.4 Dominio: Telemetry

| Método | Path | Acción | Descripción | Autenticación |
|--------|------|------|------------|---------------|
| POST | `/internal/v1/telemetry.log` | log | Enviar registros para agregación | API Key + mTLS |
| POST | `/internal/v1/telemetry.metric` | metric | Registrar métricas de rendimiento | API Key + mTLS |
| POST | `/internal/v1/telemetry.trace` | trace | Enviar trazas de ejecución | API Key + mTLS |
| GET | `/internal/v1/telemetry.health` | health | Verificar estado de telemetría | API Key + mTLS |
| GET | `/metrics` | Métricas Prometheus | API Key |
| GET | `/internal/v1/debug/sessions/{session_id}` | Información de depuración | mTLS |

## 5. Convenciones de Respuesta HTTP con Domain/Action

### 5.1 Códigos de Estado

Códigos de estado HTTP estándar utilizados:

| Código | Descripción | Uso |
|--------|------------|-----|
| 200 OK | Éxito | Operación completada con éxito |
| 201 Created | Recurso creado | Nuevo recurso creado |
| 204 No Content | Sin contenido | Operación exitosa, sin contenido que devolver |
| 400 Bad Request | Solicitud incorrecta | Error en parámetros o estructura domain/action |
| 401 Unauthorized | No autorizado | Credenciales no válidas o faltantes |
| 403 Forbidden | Prohibido | No tiene permisos para esta operación |
| 404 Not Found | No encontrado | Recurso o domain.action no encontrado |
| 409 Conflict | Conflicto | Estado de recurso conflictivo |
| 422 Unprocessable Entity | Entidad no procesable | Estructura domain/action inválida |
| 429 Too Many Requests | Demasiadas solicitudes | Límite de tasa excedido |
| 500 Internal Server Error | Error interno | Error inesperado en el servidor |

### 5.2 Formato de Respuesta Estándar Domain/Action

Todas las respuestas HTTP siguen la estructura domain/action consistente:

```json
{
  "message_id": "uuid-v4", 
  "correlation_id": "uuid-v4", // Mismo ID de la solicitud original
  "type": {
    "domain": "domain_name",
    "action": "response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    // Datos específicos de la respuesta
  },
  "status": {
    "code": 200,
    "message": "OK"
  },
  "error": {
    // Solo presente si hay error
    "code": "ERROR_CODE",
    "message": "Mensaje descriptivo",
    "details": {}
  },
  "meta": {
    "request_id": "uuid-v4",
    "processing_time_ms": 235,
    "source_service": "agent-orchestrator"
  }
}
```

### 5.3 Estructura de Paginación con Domain/Action

Estructura estándar para respuestas paginadas:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "chat",
    "action": "history_response"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601",
  "data": {
    "items": [...], // Array de mensajes u otros elementos
    "session_id": "uuid-v4"
  },
  "status": {
    "code": 200,
    "message": "OK"
  },
  "meta": {
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total_items": 45,
      "total_pages": 3,
      "has_more": true,
      "next_cursor": "cursor-hash"
    },
    "request_id": "uuid-v4",
    "processing_time_ms": 87,
    "source_service": "agent-orchestrator"
  }
}
```

## 6. Autenticación y Autorización con Domain/Action

### 6.1 Métodos de Autenticación

| Tipo | Mecanismo | Uso | Header |
|------|-----------|-----|-------|
| JWT | Bearer Token | Endpoints frontend | `Authorization: Bearer {jwt_token}` |
| mTLS | Certificados de cliente | Comunicación entre servicios | N/A (TLS mutuo) |
| API Key | Header de API Key | Endpoints internos y métricas | `X-API-Key: {api_key}` |
| HMAC | Firma de solicitud | Webhooks externos | `X-Signature: {hmac}` |

### 6.2 Claims JWT con Domain/Action

Los tokens JWT incluyen claims específicos para domain/action:

```json
{
  "sub": "user_id",
  "iss": "nooble-auth",
  "exp": 1684830077,
  "iat": 1684743677,
  "tenant_id": "tenant-uuid",
  "permissions": [
    "session:read",
    "session:write",
    "chat:read",
    "chat:write",
    "workflow:execute",
    "agent:read"
  ],
  "domains": ["session", "chat", "workflow", "agent"],
  "role": "user"
}
```

### 6.3 Permisos por Rol usando Domain/Action

| Rol | Permisos |
|-----|----------|
| Usuario | `session:read`, `session:write`, `chat:read`, `chat:write`, `agent:read`, `workflow:execute` |
| Administrador | `*:*` (acceso total) |
| Servicio | Permisos específicos por servicio (ej. `workflow:*`, `notification:send`) |
| Monitor | `system:read`, `telemetry:read`, `workflow:status` |

## 7. Versionado de API

### Estrategia de Versionado

- Versionado en URL para cambios incompatibles (`/api/v{n}/{domain}.{action}` → `/api/v{n+1}/{domain}.{action}`)
- Adición de campos nuevos opcionales sin cambio de versión
- Al menos 6 meses de soporte para versiones anteriores
- Cabecera `Sunset` para indicar endpoints obsoletos

### Ciclo de Vida de Versiones

1. **Desarrollo**: `/api/beta/{feature}/`
2. **Estable**: `/api/v{n}/`
3. **Desaprobado**: Cabecera `Deprecated: true`
4. **Retirado**: Endpoint eliminado

## 7. Ejemplos de Uso

### Crear Sesión y Enviar Mensaje (Frontend)

```javascript
// 1. Crear una nueva sesión
const sessionResponse = await fetch('https://api.nooble.ai/api/v1/sessions', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwt}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    agent_id: 'customer-support',
    metadata: { source: 'web-client' }
  })
});

const { session_id } = await sessionResponse.json();

// 2. Establecer conexión WebSocket
const ws = new WebSocket(`wss://api.nooble.ai/ws/v1/sessions/${session_id}`);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Evento recibido:', data);
};

// 3. Enviar mensaje
const messageResponse = await fetch(`https://api.nooble.ai/api/v1/sessions/${session_id}/messages`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwt}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    content: 'Hola, necesito ayuda con mi cuenta.',
    type: 'text'
  })
});
```

### Comunicación entre Servicios (Interna)

```javascript
// Enviar tarea desde Workflow Engine a Orchestrator
const taskResponse = await fetch('https://orchestrator-svc/internal/v1/tasks', {
  method: 'POST',
  // Certificado mTLS configurado en el cliente HTTP
  headers: {
    'Content-Type': 'application/json',
    'X-Correlation-ID': correlationId,
    'X-Source-Service': 'workflow-engine'
  },
  body: JSON.stringify({
    task_type: 'agent_execution',
    priority: 2,
    payload: {
      query: 'Analiza estos datos',
      context: [...],
      agent_id: 'data-analyst'
    }
  })
});
```
