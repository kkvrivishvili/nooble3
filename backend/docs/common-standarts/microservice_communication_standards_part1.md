# Estándares de Comunicación entre Microservicios - Nooble AI

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Estándares de Comunicación entre Microservicios - Nooble AI](#estándares-de-comunicación-entre-microservicios---nooble-ai)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Principios de Diseño](#2-principios-de-diseño)
  - [3. Estructura de Colas Estándar](#3-estructura-de-colas-estándar)
  - [4. Formato de Mensajes](#4-formato-de-mensajes)
  - [5. Comunicación WebSocket](#5-comunicación-websocket)
  - [6. Patrones de Comunicación por Nivel de Flujo](#6-patrones-de-comunicación-por-nivel-de-flujo)

## 1. Introducción

Este documento establece los estándares de comunicación para todos los microservicios de la plataforma Nooble AI. Su objetivo es garantizar la interoperabilidad, escalabilidad y mantenibilidad de los flujos de comunicación entre servicios, desde los más básicos hasta los más complejos.

Estos estándares son de aplicación obligatoria para todos los servicios de la plataforma y deben ser seguidos en el desarrollo de nuevos componentes o en la modificación de los existentes.

### 1.1 Propósito del Documento

- Unificar la forma en que los microservicios se comunican entre sí
- Establecer estándares claros para colas, mensajes y eventos
- Facilitar la implementación de flujos de trabajo complejos
- Asegurar la trazabilidad end-to-end de las solicitudes
- Optimizar la recuperación ante fallos y degradación controlada

### 1.2 Audiencia Objetivo

- Desarrolladores de backend de la plataforma Nooble AI
- Equipos de QA y DevOps encargados de pruebas e infraestructura
- Arquitectos de solución para integraciones y extensiones

### 1.3 Visión General de la Arquitectura

La arquitectura de comunicación de Nooble AI se basa en:

1. **Comunicación Asíncrona**: Sistema de colas Redis para comunicación entre servicios
2. **Notificaciones en Tiempo Real**: Eventos WebSocket para actualizaciones inmediatas
3. **APIs HTTP**: Interfaces sincrónicas para operaciones que requieren respuesta inmediata
4. **Orquestación Centralizada**: Agent Orchestrator Service como punto central de coordinación
5. **Multi-tenancy**: Aislamiento estricto de datos y procesamiento por tenant

## 2. Principios de Diseño

### 2.1 Principios Fundamentales

- **Asincronía Primero**: Preferir comunicación asíncrona sobre sincrónica siempre que sea posible
- **Idempotencia**: Todas las operaciones deben ser idempotentes para permitir reintentos seguros
- **Aislamiento Multi-tenant**: Estricta separación de datos y procesamiento por tenant
- **Trazabilidad**: IDs de correlación para seguimiento end-to-end de solicitudes
- **Degradación Controlada**: Estrategias claras para manejar indisponibilidad de servicios
- **Observabilidad**: Métricas y logs consistentes en todos los servicios

### 2.2 Consistencia vs. Disponibilidad

Siguiendo el teorema CAP, la plataforma Nooble AI prioriza la disponibilidad sobre la consistencia inmediata, implementando:

- **Consistencia Eventual**: Los datos pueden estar temporalmente desincronizados
- **Compensación**: Mecanismos para corregir inconsistencias detectadas
- **Optimistic Locking**: Para operaciones que requieren consistencia estricta

### 2.3 Resiliencia y Tolerancia a Fallos

Cada servicio debe implementar:

- **Circuit Breaker**: Protección contra fallos en cascada
- **Backoff Exponencial**: Estrategia de reintentos con jitter
- **Timeouts Configurables**: Por operación y tenant
- **Fallbacks**: Alternativas para funcionalidad degradada

## 3. Estructura de Colas Estándar

### 3.1 Convención de Nomenclatura

Todas las colas de Redis deben seguir la siguiente convención:

```
{servicio}.{tipo}.{tenant_id}[.{identificador_adicional}]
```

Donde:
- **servicio**: Nombre corto del servicio (orchestrator, agent_execution, query, etc.)
- **tipo**: Categoría de la cola (tasks, execution, status, etc.)
- **tenant_id**: Identificador único del tenant
- **identificador_adicional**: Opcional, para mayor granularidad (session_id, batch_id, etc.)

### 3.2 Tipos de Colas Estándar

| Tipo de Cola | Descripción | Ejemplo |
|--------------|-------------|---------|
| `tasks` | Cola principal de tareas | `agent_execution.tasks.tenant123` |
| `status` | Estado de tareas | `ingestion.status.tenant123.batch456` |
| `execution` | Ejecución de operaciones | `tool_registry.execution.tenant123` |
| `notification` | Notificaciones de eventos | `orchestrator.notification.tenant123` |
| `retry` | Tareas para reintento | `query.retry.tenant123` |
| `dead_letter` | Tareas fallidas | `embedding.dead_letter.tenant123` |

### 3.3 Prioridades y TTL

| Nivel de Flujo | Prioridad | TTL Predeterminado |
|----------------|-----------|-------------------|
| Nivel 1 (Básico) | Alta (0-3) | 300 segundos |
| Nivel 2 (Intermedio) | Media-Alta (3-5) | 600 segundos |
| Nivel 3 (Avanzado) | Media (5-7) | 1800 segundos |
| Nivel 4 (Complejo) | Baja (7-9) | 3600 segundos |
| Nivel 5 (Gestión) | Varía por subtipo | 7200 segundos |

## 4. Formato de Mensajes

### 4.1 Esquema Básico de Mensaje

Todos los mensajes enviados entre servicios deben seguir este esquema básico:

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "tipo-de-tarea",
  "priority": 0-9,
  "metadata": {
    "source_service": "servicio-origen",
    "correlation_id": "id-correlación",
    "session_id": "optional-session-id",
    "user_id": "optional-user-id"
  },
  "payload": {
    // Datos específicos de la tarea
  }
}
```

### 4.2 Campos Obligatorios

| Campo | Tipo | Descripción | Reglas |
|-------|------|-------------|--------|
| `task_id` | UUID | Identificador único de la tarea | UUID v4, generado por el productor |
| `tenant_id` | String | Identificador del tenant | Debe existir en la BD |
| `created_at` | ISO Date | Timestamp de creación | UTC, formato ISO 8601 |
| `status` | String | Estado de la tarea | Enum de valores permitidos |
| `type` | String | Tipo de tarea | Específico de cada servicio |
| `payload` | Object | Datos de la tarea | Schema según tipo |

### 4.3 Códigos de Estado Estándar

| Estado | Descripción | Uso |
|--------|-------------|-----|
| `pending` | Pendiente de procesamiento | Estado inicial |
| `processing` | En procesamiento | Tarea tomada por un worker |
| `completed` | Completada con éxito | Resultado disponible |
| `failed` | Fallida | Error no recuperable |
| `retrying` | En proceso de reintento | Error recuperable |
| `canceled` | Cancelada | Por solicitud o timeout |
| `partial` | Completada parcialmente | Algunos subprocesos exitosos |

## 5. Comunicación WebSocket

### 5.1 Estructura de Canales WebSocket

La plataforma utiliza un sistema centralizado de WebSockets a través del Agent Orchestrator Service, siguiendo esta estructura:

```
ws://agent-orchestrator:8000/ws/{tenant_id}/{tipo}/{identificador}
```

Donde:
- **tenant_id**: Identificador del tenant
- **tipo**: Categoría de eventos (task_updates, session_updates, system)
- **identificador**: Opcional, para subscripción específica (session_id, agent_id)

### 5.2 Formato Estándar de Eventos

```json
{
  "event": "nombre_del_evento",
  "service": "servicio-origen",
  "task_id": "uuid-correlación",
  "tenant_id": "tenant-id",
  "timestamp": "ISO-timestamp",
  "data": {
    // Datos específicos del evento
  }
}
```

### 5.3 Eventos Estándar del Sistema

| Categoría | Eventos | Descripción |
|-----------|---------|-------------|
| Tareas | `task_created`, `task_started`, `task_completed`, `task_failed` | Ciclo de vida de tareas |
| Agentes | `agent_thinking`, `agent_executing_tool`, `agent_response` | Estados de ejecución de agentes |
| Herramientas | `tool_execution_started`, `tool_execution_progress`, `tool_execution_completed` | Ciclo de ejecución de herramientas |
| Sistema | `service_unavailable`, `fallback_activated`, `system_alert` | Estados del sistema |

## 6. Patrones de Comunicación por Nivel de Flujo

### 6.1 Flujos Básicos (Nivel 1)

Para los flujos básicos como Conversación Simple, Consulta con Contexto y Búsqueda RAG Básica, se aplican estos patrones:

- **Comunicación primaria**: 70% asíncrona, 30% sincrónica
- **Latencia esperada**: 2-8 segundos máximo
- **Patrón dominante**: Solicitud-respuesta simple
- **Colas críticas**: 
  - `orchestrator.session.{tenant}.{session}`
  - `agent_execution.tasks.{tenant}`
  - `query.generation.{tenant}`
  - `embedding.tasks.{tenant}`

**Ejemplo de secuencia para Búsqueda RAG Básica**:

1. Orchestrator publica mensaje en `agent_execution.tasks.{tenant}`
2. Agent Execution procesa y solicita embedding mediante `embedding.tasks.{tenant}`
3. Agent Execution recibe vector y solicita búsqueda+generación mediante `query.search.{tenant}`
4. Query Service responde con resultado combinado
5. Respuesta notificada vía WebSocket y en `orchestrator.results.{tenant}.{session}`
