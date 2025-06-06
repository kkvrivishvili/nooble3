# Estándares Globales para Agent Orchestrator Service

*Versión: 1.1.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Estándares Globales para Agent Orchestrator Service](#estándares-globales-para-agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Formato Base de Mensajes](#2-formato-base-de-mensajes)
  - [3. Nomenclatura Estándar](#3-nomenclatura-estándar)
  - [4. Estándar de Colas](#4-estándar-de-colas)
  - [5. Catálogo de Eventos WebSocket](#5-catálogo-de-eventos-websocket)
  - [6. Matriz de Errores](#6-matriz-de-errores)
  - [7. Clasificación de Endpoints API](#7-clasificación-de-endpoints-api)
  - [8. Estados de Sesión](#8-estados-de-sesión)
  - [9. Referencias a Documentación Detallada](#9-referencias-a-documentación-detallada)

## 1. Introducción

Este documento establece los estándares globales para toda la documentación del Agent Orchestrator Service. Sirve como fuente única de verdad para formatos, nomenclatura, convenciones y estructuras comunes utilizadas en todos los servicios relacionados. Cada sección proporciona un resumen de los estándares, con referencias a documentos más detallados para cada tema específico.

## 2. Formato Base de Mensajes

### 2.1 Estructura Base Obligatoria

Todos los mensajes intercambiados entre el Agent Orchestrator Service y los servicios Nivel 2 DEBEN seguir esta estructura base:

```json
{
  "message_id": "uuid-v4",                  // OBLIGATORIO: Identificador único del mensaje
  "tenant_id": "tenant-identifier",         // OBLIGATORIO: Identificador del tenant
  "timestamp": "ISO-8601",                  // OBLIGATORIO: Timestamp de creación
  "version": "1.0",                         // OBLIGATORIO: Versión del formato de mensaje
  "correlation_id": "uuid-v4",              // OBLIGATORIO: ID para correlacionar mensajes
  "source": "service-name",                 // OBLIGATORIO: Servicio de origen
  "destination": "service-name",            // OBLIGATORIO: Servicio de destino
  "type": "request|response|event",         // OBLIGATORIO: Tipo de mensaje
  "payload": {                              // OBLIGATORIO: Datos específicos del mensaje
    // Contenido específico del mensaje
  }
}
```

### 2.2 Campos Opcionales Comunes

Adicionalmente, los mensajes pueden incluir estos campos opcionales:

```json
{
  // ... campos obligatorios ...
  "status": "pending|processing|completed|failed", // OPCIONAL: Estado del mensaje
  "priority": 1-10,                        // OPCIONAL: Prioridad (1=alta, 10=baja)
  "task_id": "uuid-v4",                    // OPCIONAL: ID de tarea asociada
  "session_id": "uuid-v4",                 // OPCIONAL: ID de sesión asociada
  "error": {                               // OPCIONAL: Presente solo si hay error
    "code": "error_code",
    "message": "Descripción del error",
    "details": {}
  },
  "retries": 0                             // OPCIONAL: Contador de reintentos
}
```

### 2.3 Sección "Adherencia al Formato Base"

Todos los documentos de servicios específicos DEBEN incluir esta sección:

```markdown
## Adherencia al Formato Base

Todos los mensajes en este servicio cumplen con el formato base definido en [message_schemas.md](../internal/message_schemas.md), incluyendo los campos obligatorios: `message_id`, `tenant_id`, `timestamp`, `version`, `correlation_id`, `source`, `destination`, `type` y `payload`.

Los ejemplos en este documento pueden omitir algunos de estos campos para mayor claridad, pero todos son requeridos en la implementación real.
```

## 3. Nomenclatura Estándar

### 3.1 Nombres de Servicios

| Servicio | Nombre Estandarizado | Variable de Entorno |
|---------|---------------------|---------------------|
| Agent Orchestrator | `agent_orchestrator` | `AGENT_ORCHESTRATOR_URL` |
| Agent Execution | `agent_execution` | `AGENT_EXECUTION_URL` |
| Agent Management | `agent_management` | `AGENT_MANAGEMENT_URL` |
| Conversation Service | `conversation` | `CONVERSATION_URL` |
| Tool Registry | `tool_registry` | `TOOL_REGISTRY_URL` |
| Workflow Engine | `workflow_engine` | `WORKFLOW_ENGINE_URL` |

### 3.2 Formatos de Nombres

- **Variables de entorno**: MAYÚSCULAS_CON_GUIONES_BAJOS
- **Nombres de servicios**: snake_case
- **Nombres de endpoints**: kebab-case
- **Nombres de campos JSON**: camelCase
- **Nombres de tablas en BD**: snake_case

## 4. Estándar de Colas

### 4.1 Formato de Nombres de Cola

Todas las colas deben seguir esta estructura:

```
{servicio}:{tipo}:{tenant_id}:{identificador_opcional}
```

Ejemplos:
- `agent_execution:tasks:{tenant_id}`
- `tool_registry:results:{tenant_id}:{session_id}`
- `workflow_engine:status:{tenant_id}`

### 4.2 Tipos de Cola Estándar

| Tipo | Descripción | Ejemplos |
|------|-------------|----------|
| `tasks` | Tareas por procesar | `agent_execution:tasks:{tenant_id}` |
| `results` | Resultados de procesamiento | `agent_execution:results:{tenant_id}` |
| `events` | Eventos de notificación | `orchestrator:events:{tenant_id}` |
| `status` | Actualizaciones de estado | `workflow_engine:status:{tenant_id}` |
| `dlq` | Dead Letter Queue | `orchestrator:dlq:{tenant_id}` |

## 5. Catálogo de Eventos WebSocket

### 5.1 Eventos de Servidor a Cliente

| Nombre del Evento | Origen | Destino | Payload |
|------------------|--------|---------|---------|
| `content_stream` | Agent Execution | Cliente | `{ chunk: string, is_final: boolean, message_id: string }` |
| `message_completed` | Orchestrator | Cliente | `{ message_id: string, response: object }` |
| `message_status_update` | Orchestrator | Cliente | `{ message_id: string, status: string, timestamp: string }` |
| `tool_call` | Agent Execution | Cliente | `{ tool_id: string, params: object, tool_call_id: string }` |
| `tool_response` | Tool Registry | Cliente | `{ tool_call_id: string, result: object }` |
| `error` | Cualquiera | Cliente | `{ code: string, message: string, details: object }` |

### 5.2 Eventos de Cliente a Servidor

| Nombre del Evento | Origen | Destino | Payload |
|------------------|--------|---------|---------|
| `cancel_task` | Cliente | Orchestrator | `{ task_id: string }` |
| `ping` | Cliente | Orchestrator | `{ client_timestamp: string }` |
| `tool_response` | Cliente | Orchestrator | `{ tool_call_id: string, result: object }` |

## 6. Matriz de Errores

### 6.1 Mapeo HTTP a Códigos de Error

| Código HTTP | Código Error | Escenario | Reintentable |
|------------|-------------|----------|-------------|
| `400` | `validation_error` | Datos inválidos o mal formados | No |
| `401` | `auth_error` | Token inválido o expirado | Solo con nuevo token |
| `403` | `permission_denied` | Sin permiso para la operación | No |
| `404` | `resource_not_found` | Recurso (sesión, agente, etc.) no existe | No |
| `409` | `concurrent_modification` | Conflicto de edición concurrente | Sí, con nuevo estado |
| `429` | `rate_limited` | Límite de tasa excedido | Sí, con backoff |
| `500` | `service_error` | Error interno del servidor | Sí |
| `502` | `bad_gateway` | Error en servicio dependiente | Sí |
| `503` | `service_unavailable` | Servicio no disponible | Sí |
| `504` | `timeout` | Timeout en la operación | Sí |

### 6.2 Códigos de Error Específicos por Servicio

Cada servicio puede definir códigos específicos siguiendo este formato:
`{SERVICIO}_{CATEGORIA}_{NUMERO}`

Ejemplos:
- `ORCH_AUTH_001`: Error de autenticación en Orchestrator
- `AGEX_EXEC_002`: Error de ejecución en Agent Execution

## 7. Clasificación de Endpoints API

### 7.1 Endpoints Públicos (Frontend)

Los endpoints para uso frontend siguen este patrón:

```
/api/{recurso}[/{id}][/{subrecurso}]
```

Ejemplos:
- `POST /api/sessions` - Crear una sesión
- `GET /api/sessions/{id}` - Obtener una sesión
- `POST /api/sessions/{id}/messages` - Enviar mensaje a sesión

### 7.2 Endpoints Internos (Entre Servicios)

Los endpoints para comunicación entre servicios siguen este patrón:

```
/api/internal/v1/{recurso}[/{id}][/{subrecurso}]
```

Ejemplos:
- `POST /api/internal/v1/agent-execution` - Solicitar ejecución de agente
- `GET /api/internal/v1/conversation/{id}` - Obtener conversación

## 8. Estados de Sesión

### 8.1 Estados Estándar de Sesión

| Estado | Descripción | Representación en BD |
|--------|-------------|----------------------|
| `created` | Sesión creada pero sin actividad | `status = 'created'` |
| `active` | Sesión con actividad reciente | `status = 'active'` |
| `inactive` | Sesión sin actividad por 10+ minutos | `status = 'inactive'` |
| `closed` | Sesión cerrada explícitamente o inactiva por 24+ horas | `status = 'closed'` |

### 8.2 Transiciones de Estado

```
created -> active -> inactive -> closed
        ^            |
        |            v
        +------------+
```

La tabla `sessions` en la base de datos debe implementar:
```sql
ALTER TABLE sessions ADD CONSTRAINT status_check 
CHECK (status IN ('created', 'active', 'inactive', 'closed'));
```

## 9. Referencias a Documentación Detallada

Esta sección proporciona enlaces a los documentos detallados para cada uno de los estándares globales. Estos documentos contienen la implementación completa y detallada de cada estándar.

### 9.1 Mensajes y Comunicación

| Documento | Descripción | Ruta |
|-----------|-------------|------|
| Esquemas de Mensajes | Formatos detallados para todos los mensajes entre servicios | [communication/internal/message_schemas.md](../communication/internal/message_schemas.md) |
| Catálogo de Eventos WebSocket | Definiciones completas de todos los eventos WebSocket | [communication/websocket/websocket_events.md](../communication/websocket/websocket_events.md) |
| Integración Frontend | Guía completa de integración para clientes frontend | [communication/frontend/frontend_integration.md](../communication/frontend/frontend_integration.md) |

### 9.2 API y Servicios

| Documento | Descripción | Ruta |
|-----------|-------------|------|
| Clasificación de Endpoints | Catálogo completo de endpoints API y sus tipos | [api/endpoints_classification.md](../api/endpoints_classification.md) |
| Flujos End-to-End | Diagramas de secuencia y flujos completos entre servicios | [structure/end_to_end_flows.md](../structure/end_to_end_flows.md) |
| Configuración de Servicio | Referencia completa de variables y configuraciones | [configuration/service_configuration.md](../configuration/service_configuration.md) |

### 9.3 Modelos y Errores

| Documento | Descripción | Ruta |
|-----------|-------------|------|
| Estados de Sesión | Definiciones detalladas de estados y transiciones | [models/session_states.md](../models/session_states.md) |
| Matriz de Errores | Catálogo completo de errores con códigos y estrategias | [errors/error_matrix.md](../errors/error_matrix.md) |
