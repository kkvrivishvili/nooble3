# Comunicación Interna - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Comunicación Interna - Agent Management Service](#comunicación-interna---agent-management-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Estructura de Colas](#2-estructura-de-colas)
    - [2.1 Colas de Entrada](#21-colas-de-entrada)
    - [2.2 Colas de Salida](#22-colas-de-salida)
  - [3. Formato de Mensajes](#3-formato-de-mensajes)
    - [3.1 Formato Estándar de Mensaje](#31-formato-estándar-de-mensaje)
    - [3.2 Mensajes Específicos](#32-mensajes-específicos)
  - [4. Flujos de Comunicación](#4-flujos-de-comunicación)
  - [5. Timeouts y Reintentos](#5-timeouts-y-reintentos)
  - [6. Manejo de Fallos](#6-manejo-de-fallos)
  - [7. Registro de Cambios](#7-registro-de-cambios)

## 1. Visión General

Este documento detalla los mecanismos de comunicación interna utilizados por el Agent Management Service para interactuar con otros microservicios del ecosistema Nooble. El servicio utiliza Redis Queue para el procesamiento asíncrono de tareas y Redis PubSub para notificaciones en tiempo real, complementado con comunicación WebSocket para actualizaciones hacia el orquestador.

### 1.1 Principios Fundamentales

- **Atomicidad**: Las operaciones críticas como la creación, actualización y eliminación de agentes se ejecutan con garantías de atomicidad utilizando transacciones Redis y bloqueos distribuidos.

- **Multi-tenencia**: El servicio implementa un estricto aislamiento entre tenants mediante segmentación de datos en todas las capas:
  - Keys de Redis separadas por tenant_id
  - Canales PubSub específicos por tenant
  - WebSockets con canales de notificación por tenant
  - Filtrado de todas las consultas a base de datos por tenant_id

![Diagrama de Comunicación Interna](./diagrams/internal_communication.png)

## 2. Sistema de Cola de Trabajo Redis

### 2.1 Keys de Redis Queue

Redis Queue utiliza claves de Redis para almacenar tareas en cola. Las siguientes son las claves utilizadas por el Agent Management Service:

| Key Redis | Propósito | Formato de Mensaje | Productores |
|----------------|-----------|-------------------|-------------|
| `agent.management.tasks.{tenant_id}` | Cola principal para procesamiento de tareas | [AgentTaskMessage](#agent-task-message) | Agent Orchestrator Service |
| `agent.management.validation.{tenant_id}` | Validación de configuraciones de agentes | [AgentValidationMessage](#agent-validation-message) | Agent Orchestrator Service, Agent Management API |
| `agent.management.templates.{tenant_id}` | Operaciones con plantillas de agentes | [TemplateMessage](#template-message) | Agent Orchestrator Service |

### 2.2 Canales de Redis PubSub

Para notificaciones en tiempo real, el servicio utiliza los siguientes canales de Redis PubSub:

| Canal PubSub | Propósito | Formato de Mensaje | Suscriptores |
|----------------|-----------|-------------------|-------------|
| `agent.management.notifications.{tenant_id}` | Notificaciones de cambios en agentes | [AgentNotificationEvent](#agent-notification-event) | Agent Orchestrator Service, Notification Service |
| `system.health.agent.management` | Estado del servicio y métricas | [HealthStatusEvent](#health-status-event) | Monitoring Service |

## 3. Formato de Mensajes

### 3.1 Formato Estándar de Mensaje

Todos los mensajes intercambiados entre Agent Management Service y otros servicios siguen esta estructura base definida en el documento de estándares:

```json
{
  "message_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "timestamp": "ISO-8601-datetime",
  "version": "1.0",
  "type": "request|response|event",
  "source": "service-name",
  "destination": "service-name",
  "correlation_id": "uuid-v4",
  "task_id": "uuid-v4",
  "session_id": "session-id",
  "status": "pending|processing|completed|failed",
  "priority": 0-9,
  "metadata": {
    "user_id": "user-identifier",
    "operation_type": "agent_create|agent_update|agent_validate|agent_notify"
  },
  "payload": {
    // Contenido específico de la operación
  }
}
```

### 3.2 Mensajes Específicos

<a id="agent-task-message"></a>
**AgentTaskMessage**
```json
{
  "message_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "tenant_id": "tenant-identifier",
  "timestamp": "2025-06-03T15:30:45Z",
  "version": "1.0",
  "type": "request",
  "source": "orchestrator",
  "destination": "agent-management",
  "correlation_id": "22e76683-7ffd-43a4-a8c1-b87e0ec9c387",
  "task_id": "uuid-string",
  "session_id": "session-identifier",
  "status": "pending",
  "priority": 5,
  "metadata": {
    "user_id": "user-identifier",
    "operation_type": "agent_create",
    "source_request_id": "original-request-id"
  },
  "payload": {
    "name": "Marketing Assistant",
    "description": "Asistente para campañas de marketing",
    "system_prompt": "Eres un asistente especializado en marketing...",
    "tools": ["search", "calculator", "calendar"],
    "memory_config": {
      "memory_type": "conversation",
      "window_size": 10
    },
    "llm_config": {
      "model": "gpt-4",
      "temperature": 0.7,
      "max_tokens": 1000
    },
    "metadata": {
      "created_by": "user-id",
      "department": "marketing",
      "tags": ["marketing", "assistant"]
    }
  }
}
```

<a id="agent-validation-message"></a>
**AgentValidationMessage**
```json
{
  "task_id": "uuid-string",
  "tenant_id": "tenant-identifier",
  "created_at": "2025-06-03T15:35:10Z",
  "status": "pending",
  "type": "agent_validate",
  "priority": 7,
  "metadata": {
    "user_id": "user-identifier",
    "source": "api"
  },
  "payload": {
    "agent_id": "agent-uuid",
    "config": {
      "system_prompt": "Eres un asistente especializado en marketing...",
      "tools": ["search", "calculator", "calendar"],
      "llm_config": {
        "model": "gpt-4",
        "temperature": 0.7
      }
    },
    "tier": "pro"
  }
}
```

<a id="template-message"></a>
**TemplateMessage**
```json
{
  "task_id": "uuid-string",
  "tenant_id": "tenant-identifier",
  "created_at": "2025-06-03T15:40:22Z",
  "status": "pending",
  "type": "template_create",
  "priority": 5,
  "metadata": {
    "user_id": "user-identifier",
    "source": "api"
  },
  "payload": {
    "name": "Marketing Template",
    "description": "Template para agentes de marketing",
    "category": "marketing",
    "system_prompt": "Eres un asistente especializado en marketing...",
    "tools": ["search", "calculator", "calendar"],
    "llm_config": {
      "model": "gpt-4",
      "temperature": 0.7
    }
  }
}
```

<a id="agent-notification-event"></a>
**AgentNotificationEvent**
```json
{
  "event": "agent_created",
  "timestamp": "2025-06-03T15:42:30Z",
  "tenant_id": "tenant-identifier",
  "data": {
    "agent_id": "agent-uuid",
    "agent_name": "Marketing Assistant",
    "version": "1.0",
    "status": "active"
  }
}
```

<a id="health-status-event"></a>
**HealthStatusEvent**
```json
{
  "event": "health_status",
  "timestamp": "2025-06-03T15:45:00Z",
  "service": "agent-management",
  "status": "healthy",
  "metrics": {
    "agents_created_last_hour": 5,
    "agents_updated_last_hour": 12,
    "validation_requests": 18,
    "response_time_avg_ms": 240
  }
}
```

## 4. Flujos de Comunicación

### 4.1 Creación y Actualización de Agentes

**Flujo de Creación de Agente:**

1. El frontend envía solicitud directamente a la API REST del Agent Management Service con el payload de configuración del nuevo agente
2. El API Service del Agent Management valida la autenticación y permisos del usuario
3. El Business Service procesa la solicitud y crea una tarea asíncrona en Redis Queue con clave `agent-management.tasks.{tenant_id}` y type: `agent_create`
4. Worker de Agent Management Service obtiene la tarea desde Redis Queue y procesa la creación del agente
5. Durante el procesamiento:
   - Valida la configuración del agente según el tier del tenant
   - Registra la configuración en la base de datos
   - Asigna un ID único y versión inicial
6. Una vez completada la creación, publica una notificación en el canal Redis PubSub `agent-management.notifications.{tenant_id}` con event: `agent_created`
7. Envía notificaciones a los servicios consumidores (Agent Execution Service, Agent Orchestrator Service) para informarles de la nueva configuración disponible
8. Notifica también al canal WebSocket específico del tenant: `tenant:{tenant_id}` para actualizar la UI

> **IMPORTANTE**: El Agent Orchestrator NO debe intermediar estas operaciones CRUD. El frontend debe comunicarse directamente con el Agent Management Service.

**Flujo de Actualización de Agente:**

1. El frontend envía solicitud directamente a la API REST del Agent Management Service para actualizar un agente existente
2. El Business Service valida la solicitud y crea una tarea asíncrona en Redis Queue con clave `agent.management.tasks.{tenant_id}` y type: `agent_update`
3. Worker procesa la actualización:
   - Genera una nueva versión de la configuración
   - Mantiene historial de versiones previas
   - Actualiza referencias a la versión activa
   - Utiliza transacciones Redis para garantizar atomicidad
4. Publica evento `agent.updated` en el canal Redis PubSub `agent.management.notifications.{tenant_id}`
5. Notifica a los servicios consumidores (Agent Execution, Agent Orchestrator) sobre el cambio de configuración
6. Devuelve confirmación al frontend con los detalles de la actualización

### 4.2 Validación de Configuraciones

**Flujo de Validación de Configuración:**

1. Frontend envía directamente al Agent Management Service una solicitud API para validar la configuración de un agente (antes de crear o actualizar)
2. Agent Management Service crea una tarea asíncrona en Redis Queue con clave `agent.management.validation.{tenant_id}`
3. Worker procesa la validación:
   - Verifica límites según tier del usuario (tokens en prompt, herramientas permitidas)
   - Valida existencia y permisos para las herramientas especificadas mediante consulta al Tool Registry Service
   - Verifica compatibilidad de modelos LLM solicitados
   - Valida configuraciones de memoria y otros parámetros
4. Resultado de validación se registra en la base de datos con un ID de validación
5. Se notifica el resultado mediante:
   - Evento en Redis PubSub canal `agent.management.validations.{tenant_id}` con evento: `agent.validated`
   - Actualización del estado en la API para consulta síncrona
   - Notificación WebSocket al frontend para actualizar la UI inmediatamente

> **NOTA**: Los resultados de validación son consumidos principalmente por el frontend para permitir al usuario corregir problemas antes de confirmar la creación o actualización del agente.

### 4.3 Gestión de Templates

**Flujo de Creación de Template:**

1. Agent Management recibe solicitud para convertir un agente en template o crear template nuevo
2. Envía tarea a Redis Queue con clave `agent.management.templates.{tenant_id}`
3. Worker procesa la creación del template y lo registra en el catálogo
4. Publica evento `agent.template.created` para actualizar interfaces de usuario

**Flujo de Instanciación desde Template:**

1. Usuario selecciona un template para crear nuevo agente
2. Agent Orchestrator envía solicitud a Agent Management API
3. Se crea un nuevo agente basado en la configuración del template
4. Se notifica la creación del agente como en el flujo estándar

## 5. Timeouts y Reintentos

### 5.1 Políticas de Timeout

| Operación | Timeout | Contexto |
|----------|---------|----------|
| Validación de Agente | 15 segundos | Timeout para validaciones síncronas vía API |
| Creación de Agente | 30 segundos | Tiempo máximo para procesamiento de creación |
| Actualización de Agente | 30 segundos | Tiempo máximo para procesamiento de actualización |
| Tareas Redis Queue | 60 segundos | Timeout general para tareas en cola |
| Operaciones Redis PubSub | 5 segundos | Timeout para publicación de eventos |
| Conexión WebSocket | Sin timeout | Conexión persistente con orquestador |

### 5.2 Estrategias de Reintento

| Operación | Estrategia | Detalles |
|----------|------------|----------|
| Redis Queue Tasks | Exponential Backoff | 3 reintentos: 1s, 3s, 9s |
| Redis PubSub | Reintento simple | Reintento inmediato (max 2 veces) |
| Validaciones | Circuit Breaker | 5 fallos en 60s activan el breaker |
| Conexión WebSocket | Backoff Exponencial | Min: 1s, Max: 30s, Factor: 1.5 |
| Operaciones BD | Retry con Jitter | 3 reintentos con 300-700ms entre intentos |

## 6. Manejo de Fallos y Garantías Transaccionales

### 6.1 Garantías de Atomicidad

- **Transacciones Redis**: Las operaciones compuestas utilizan transacciones Redis con comandos MULTI/EXEC
- **Bloqueos distribuidos**: Implementación de bloqueos con Redis para garantizar exclusión mutua entre operaciones concurrentes
- **Optimistic locking**: Uso de versiones para prevenir modificaciones concurrentes en configuraciones de agentes
- **Mecanismos de compensación**: Para operaciones parcialmente completadas que necesitan revertirse

### 6.2 Sistema de Recuperación

- **Redis Queue Failed Jobs**: Las tareas fallidas se registran con estado `failed` en Redis Queue y están disponibles para inspección
- **Mecanismo de reintentos**: Redis Queue proporciona reintentos automáticos configurable por tarea
- **Circuit Breaker**: Se implementa un circuit breaker para operaciones hacia APIs externas con umbral de 5 fallos en 60 segundos
- **Notificación de errores WebSocket**: Los errores se notifican mediante el evento `task_failed` al frontend siguiendo el formato estándar mostrado en el README
- **Notificación de errores WebSocket**: Los errores se notifican mediante el evento `task_failed` al Orchestrator siguiendo el formato estándar mostrado en el README
- **Logging estructurado**: Todos los errores de comunicación se registran en formato estructurado JSON
- **Redis Sentinel/Cluster**: Para alta disponibilidad de Redis se usa configuración en cluster

## 7. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
| 1.0.1 | 2025-06-03 | Actualización para reflejar el uso de Redis Queue y Redis PubSub |
