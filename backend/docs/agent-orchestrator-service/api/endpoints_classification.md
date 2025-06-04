# Clasificación de Endpoints API del Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

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

Este documento establece una clasificación clara de todos los endpoints API del Agent Orchestrator Service, distinguiendo entre los endpoints públicos orientados al frontend y los endpoints internos para comunicación entre servicios. La clasificación ayuda a mantener una separación clara de responsabilidades, simplifica la documentación y mejora la seguridad.

## 2. Convenciones de Nomenclatura

### Prefijos de Path

Los endpoints siguen estas convenciones de nomenclatura:

| Tipo de Endpoint | Prefijo de Path | Ejemplo |
|-----------------|----------------|---------|
| Frontend (Público) | `/api/v{n}/` | `/api/v1/sessions` |
| Interno (Servicio) | `/internal/v{n}/` | `/internal/v1/tasks` |
| WebSocket | `/ws/v{n}/` | `/ws/v1/sessions/{session_id}` |
| Salud y Diagnóstico | `/health`, `/metrics` | `/health/ready` |

### Convención para Parámetros REST

- IDs de recursos siempre como path params: `/api/v1/sessions/{session_id}`
- Filtros y opciones como query params: `/api/v1/messages?limit=10&offset=0`
- Acciones específicas como subrecursos: `/api/v1/sessions/{session_id}/pause`

## 3. Endpoints Frontend (Públicos)

Endpoints expuestos para uso directo por aplicaciones frontend.

### 3.1 Gestión de Sesiones

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| POST | `/api/v1/sessions` | Crear nueva sesión | JWT |
| GET | `/api/v1/sessions/{session_id}` | Obtener detalles de sesión | JWT |
| GET | `/api/v1/sessions` | Listar sesiones del usuario | JWT |
| PUT | `/api/v1/sessions/{session_id}/pause` | Pausar sesión | JWT |
| PUT | `/api/v1/sessions/{session_id}/resume` | Reanudar sesión | JWT |
| DELETE | `/api/v1/sessions/{session_id}` | Terminar sesión | JWT |

### 3.2 Comunicación en Chat

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| POST | `/api/v1/sessions/{session_id}/messages` | Enviar mensaje | JWT |
| GET | `/api/v1/sessions/{session_id}/messages` | Obtener historial de mensajes | JWT |
| DELETE | `/api/v1/sessions/{session_id}/messages/{message_id}` | Eliminar mensaje | JWT |
| POST | `/api/v1/sessions/{session_id}/messages/{message_id}/cancel` | Cancelar procesamiento | JWT |

### 3.3 WebSocket

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| WebSocket | `/ws/v1/sessions/{session_id}` | Conexión WebSocket para streaming | JWT |

### 3.4 Tareas Asíncronas

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| POST | `/api/v1/tasks` | Crear nueva tarea por lotes | JWT |
| GET | `/api/v1/tasks/{task_id}` | Verificar estado de tarea | JWT |
| DELETE | `/api/v1/tasks/{task_id}` | Cancelar tarea | JWT |
| GET | `/api/v1/tasks/{task_id}/results` | Obtener resultados de tarea | JWT |

### 3.5 Configuración de Agentes

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| GET | `/api/v1/agents` | Listar agentes disponibles | JWT |
| GET | `/api/v1/agents/{agent_id}` | Obtener configuración de agente | JWT |
| POST | `/api/v1/sessions/{session_id}/agent` | Cambiar agente para la sesión | JWT |

## 4. Endpoints de Servicio (Internos)

Endpoints para comunicación entre servicios, no destinados al uso por frontend.

### 4.1 Comunicación Inter-Servicio

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| POST | `/internal/v1/tasks` | Crear tarea desde otro servicio | mTLS |
| POST | `/internal/v1/events` | Publicar evento desde otro servicio | mTLS |
| PUT | `/internal/v1/sessions/{session_id}/state` | Actualizar estado de sesión | mTLS |

### 4.2 Gestión de Estado

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| GET | `/internal/v1/sessions/{session_id}/state` | Consultar estado completo | mTLS |
| PUT | `/internal/v1/sessions/{session_id}/lock` | Adquirir bloqueo distribuido | mTLS |
| DELETE | `/internal/v1/sessions/{session_id}/lock` | Liberar bloqueo distribuido | mTLS |

### 4.3 Webhooks de Servicio

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| POST | `/internal/v1/webhooks/tool_completed` | Callback de herramienta completada | HMAC |
| POST | `/internal/v1/webhooks/workflow_step` | Callback de paso de workflow | HMAC |

### 4.4 Monitoreo y Diagnóstico

| Método | Path | Descripción | Autenticación |
|--------|------|------------|--------------|
| GET | `/health/live` | Verificación de vivacidad | Ninguna |
| GET | `/health/ready` | Verificación de disponibilidad | Ninguna |
| GET | `/metrics` | Métricas Prometheus | API Key |
| GET | `/internal/v1/debug/sessions/{session_id}` | Información de depuración | mTLS |

## 5. Autenticación y Autorización

### Métodos de Autenticación

| Tipo | Mecanismo | Uso |
|------|-----------|-----|
| JWT | Bearer Token en Authorization header | Endpoints frontend |
| mTLS | Certificados de cliente | Comunicación entre servicios |
| HMAC | Firma de solicitud | Webhooks externos |
| API Key | Header X-API-Key | Endpoints de diagnóstico |

### Permisos por Rol

| Rol | Permisos |
|-----|----------|
| Usuario | Gestión de sus propias sesiones y mensajes |
| Administrador | Acceso a todas las sesiones y configuración |
| Servicio | Acceso a endpoints internos específicos |
| Monitor | Solo acceso a métricas y estado |

## 6. Versionado de API

### Estrategia de Versionado

- Versionado en URL para cambios incompatibles (`/api/v1/` → `/api/v2/`)
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
