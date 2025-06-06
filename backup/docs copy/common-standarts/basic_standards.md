# Estándares de Comunicación para Microservicios Nooble

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Estándares de Naming](#2-estándares-de-naming)
3. [Estructura de Mensajes](#3-estructura-de-mensajes)
4. [Comunicación por Colas](#4-comunicación-por-colas)
5. [Eventos WebSocket](#5-eventos-websocket)
6. [REST API](#6-rest-api)
7. [Gestión de Errores](#7-gestión-de-errores)
8. [Integración con Flujos de Trabajo](#8-integración-con-flujos-de-trabajo)

## 1. Introducción

Este documento establece los estándares de comunicación entre los microservicios de la plataforma Nooble AI. El objetivo es garantizar la consistencia, facilitar la integración y simplificar el mantenimiento de la comunicación entre servicios.

### 1.1 Principios Generales

- **Consistencia**: Usar patrones comunes en todos los servicios
- **Minimalismo**: Mantener la comunicación tan simple como sea posible
- **Trazabilidad**: Facilitar el seguimiento de mensajes entre servicios
- **Extensibilidad**: Permitir la evolución sin romper compatibilidad
- **Multi-tenancy**: Garantizar el aislamiento completo entre tenants

## 2. Estándares de Naming

### 2.1 Nombres de Eventos

Los nombres de eventos deben seguir el formato `dominio.acción`, donde:
- `dominio`: El área funcional del evento (ej: `workflow`, `tool`, `conversation`)
- `acción`: La acción que ocurrió (ej: `started`, `completed`, `failed`)

**Ejemplos correctos**:
- `workflow.started`
- `tool.completed`
- `conversation.updated`

**Ejemplos incorrectos**:
- `task_completed` (no usa formato dominio.acción)
- `workflow-started` (usa guion en lugar de punto)
- `StartedWorkflow` (usa CamelCase en lugar del formato estándar)

### 2.2 Nombres de Colas

Las colas deben seguir el formato `servicio:propósito:{tenant_id}[:recurso_id]`, donde:
- `servicio`: El servicio que gestiona la cola
- `propósito`: El propósito de la cola
- `{tenant_id}`: Identificador único del tenant (obligatorio)
- `[:recurso_id]`: ID opcional de un recurso específico

**Ejemplos correctos**:
- `orchestrator:session:{tenant_id}:{session_id}`
- `workflow:execution:{tenant_id}`
- `tool:registry:{tenant_id}`

## 3. Estructura de Mensajes

### 3.1 Estructura Estándar de Mensajes

Todos los mensajes intercambiados entre servicios deben contener los siguientes campos base:

```json
{
  "message_id": "uuid-v4",           // Identificador único del mensaje
  "tenant_id": "tenant-identifier",  // Identificador del tenant
  "timestamp": "ISO-8601-datetime",  // Momento de creación del mensaje
  "version": "1.0",                  // Versión del formato del mensaje
  "type": "request|response|event",  // Tipo de mensaje
  "source": "service-name",          // Servicio que origina el mensaje
  "destination": "service-name",     // Servicio destino (opcional en eventos)
  "correlation_id": "uuid-v4",       // ID para correlacionar secuencias de mensajes
  "payload": {                       // Contenido específico del mensaje
    // Datos específicos del tipo de mensaje
  }
}
```

### 3.2 Estructura de Mensajes de Tarea

Los mensajes relacionados con tareas deben extender la estructura base con:

```json
{
  // Campos básicos...
  "task_id": "uuid-v4",
  "status": "pending|processing|completed|failed",
  "priority": 0-9,
  "metadata": {
    "source_request_id": "uuid-original-request",
    "session_id": "session-identifier",
    "user_id": "user-identifier",
    "timeout_ms": 30000
  }
}
```

### 3.3 Estructura de Eventos

Los eventos deben seguir esta estructura:

```json
{
  // Campos básicos...
  "event": "dominio.acción",
  "timestamp": "ISO-8601-datetime",
  "data": {
    // Datos específicos del evento
  }
}
```

## 4. Comunicación por Colas

### 4.1 Principios de Comunicación Asíncrona

- Cada servicio debe definir claramente las colas que produce y las que consume
- Las colas deben tener un único productor, pero pueden tener múltiples consumidores
- Todos los mensajes en cola deben incluir `tenant_id` para garantizar aislamiento
- Las operaciones de larga duración deben incluir mensajes de progreso

### 4.2 Patrones de Comunicación por Cola

- **Request-Response Asíncrono**: Para operaciones que requieren respuesta pero pueden tardar
- **Publicación de Eventos**: Para notificaciones sin respuesta esperada
- **Streaming de Eventos**: Para actualizaciones continuas de estado

## 5. Eventos WebSocket

### 5.1 Categorías de Eventos Estándar

| Categoría | Propósito | Formato |
|-----------|-----------|---------|
| `.started` | Notificar inicio de operación | `{dominio}.started` |
| `.progress` | Actualizar progreso | `{dominio}.progress` |
| `.completed` | Notificar finalización exitosa | `{dominio}.completed` |
| `.failed` | Notificar error | `{dominio}.failed` |
| `.input_requested` | Solicitar entrada del usuario | `{dominio}.input_requested` |

### 5.2 Estructura de Eventos WebSocket

Todos los eventos WebSocket deben seguir esta estructura:

```json
{
  "event": "dominio.acción",
  "service": "service-name",
  "tenant_id": "tenant-identifier",
  "task_id": "task-uuid-v4",
  "correlation_id": "correlation-uuid",
  "timestamp": "ISO-8601-datetime",
  "data": {
    // Datos específicos del evento
  }
}
```

## 6. REST API

### 6.1 Estándares de URL

- Usar kebab-case para los nombres de recursos en URLs
- Incluir versión de API en la URL (ej: `/api/v1/resources`)
- Seguir principios RESTful para operaciones CRUD
- Usar plural para colecciones (ej: `/agents` en lugar de `/agent`)

### 6.2 Estándares de Métodos HTTP

| Método | Uso | Ejemplo |
|--------|-----|---------|
| GET | Recuperar recursos | `GET /api/v1/tools` |
| POST | Crear recursos | `POST /api/v1/tools` |
| PUT | Actualizar recurso completo | `PUT /api/v1/tools/{id}` |
| PATCH | Actualizar parcialmente | `PATCH /api/v1/tools/{id}` |
| DELETE | Eliminar recurso | `DELETE /api/v1/tools/{id}` |

### 6.3 Estándares de Respuesta

Todas las respuestas deben seguir esta estructura:

```json
{
  "status": "success|error",
  "data": {
    // Datos de respuesta en caso de éxito
  },
  "error": {
    "code": "ERROR_CODE",
    "message": "Descripción del error",
    "details": {}
  },
  "metadata": {
    "request_id": "uuid-v4",
    "timestamp": "ISO-8601-datetime",
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 100
    }
  }
}
```

## 7. Gestión de Errores

### 7.1 Códigos de Error Estándar

Los códigos de error deben seguir el formato `DOMINIO_ERROR_TIPO`:

| Prefijo | Descripción | Ejemplo |
|---------|-------------|---------|
| `ORCH_` | Error del Orchestrator | `ORCH_SESSION_NOT_FOUND` |
| `CONV_` | Error del Conversation Service | `CONV_STORAGE_ERROR` |
| `TOOL_` | Error del Tool Registry Service | `TOOL_EXECUTION_TIMEOUT` |
| `WFLOW_` | Error del Workflow Engine | `WFLOW_VALIDATION_ERROR` |
| `AGENT_` | Error del Agent Execution | `AGENT_EXECUTION_FAILED` |

### 7.2 Estrategias de Manejo de Errores

- **Reintentos Exponenciales**: Para errores temporales
- **Circuit Breaking**: Para evitar cascada de fallos
- **Degradación Elegante**: Para mantener servicio parcial en fallos
- **Logs Detallados**: Para facilitar diagnóstico y solución
- **Propagación Controlada**: Traducir errores internos a mensajes adecuados

## 8. Integración con Flujos de Trabajo

### 8.1 Mapeo con Catálogo de Flujos

Cada documento de comunicación entre servicios debe referenciar explícitamente a qué flujos del catálogo responde:

| Nivel | Flujo | Servicios Involucrados |
|-------|-------|------------------------|
| **Nivel 1** | Conversación Simple | Orchestrator, Agent Execution, Query Service |
| **Nivel 1** | Consulta con Contexto | Orchestrator, Conversation Service, Agent Execution, Query Service |
| **Nivel 1** | Búsqueda RAG Básica | Orchestrator, Agent Execution, Query Service, Embedding Service |
| **Nivel 2** | Uso de Herramientas Simples | Orchestrator, Agent Execution, Tool Registry, Query Service |
| **Nivel 3** | Workflow Multi-etapa | Orchestrator, Workflow Engine, Agent Execution, Tool Registry |
| **Nivel 3** | Herramientas Encadenadas | Orchestrator, Agent Execution, Tool Registry |

### 8.2 Diagramas de Secuencia Estandarizados

Los diagramas de secuencia deben:
- Usar la misma nomenclatura para los participantes en todos los documentos
- Incluir referencia explícita al nivel y nombre del flujo del catálogo
- Mostrar claramente los mensajes de WebSocket/eventos con línea punteada
- Resaltar operaciones asíncronas con notas o estilos específicos

---

## Registro de Cambios

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2025-06-03 | Equipo Nooble Backend | Versión inicial |
