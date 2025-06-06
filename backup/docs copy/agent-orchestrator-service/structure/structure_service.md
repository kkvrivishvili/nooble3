# Estructura del Servicio - Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Estructura del Servicio - Agent Orchestrator Service](#estructura-del-servicio---agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Propósito y Responsabilidades](#1-propósito-y-responsabilidades)
  - [2. Arquitectura del Servicio](#2-arquitectura-del-servicio)
    - [2.1 Componentes Principales](#21-componentes-principales)
    - [2.2 Flujo de Datos](#22-flujo-de-datos)
  - [3. Dependencias](#3-dependencias)
    - [3.1 Servicios Internos](#31-servicios-internos)
    - [3.2 Servicios Externos](#32-servicios-externos)
    - [3.3 Librerías y Frameworks](#33-librerías-y-frameworks)
  - [4. Configuración y Despliegue](#4-configuración-y-despliegue)
    - [4.1 Variables de Entorno](#41-variables-de-entorno)
    - [4.2 Requisitos de Infraestructura](#42-requisitos-de-infraestructura)
  - [5. Operaciones y Mantenimiento](#5-operaciones-y-mantenimiento)
  - [6. Registro de Cambios](#6-registro-de-cambios)

## 1. Propósito y Responsabilidades

El **Agent Orchestrator Service** es el componente central de coordinación de la arquitectura Nooble AI Platform, actuando como punto de entrada único que coordina las interacciones entre el usuario y los diferentes microservicios del sistema. 

Sus principales responsabilidades son:

- Punto de entrada unificado para solicitudes de usuarios desde la API frontend
- Orquestación de flujos de trabajo complejos entre múltiples servicios
- Gestión y mantenimiento del estado de las sesiones de usuario
- Direccionamiento inteligente de solicitudes a los servicios apropiados
- Coordinación entre servicios para ejecución de workflows multi-etapa
- Garantizar aislamiento entre tenants en todo el sistema
- Manejo de comunicación en tiempo real mediante WebSockets
- Tracking centralizado del estado de tareas asíncronas
- Implementación de mecanismos de recuperación de errores y reintentos

Este servicio es crítico como núcleo de la plataforma, ya que funciona como una capa de abstracción que oculta la complejidad de la arquitectura de microservicios al cliente y garantiza la correcta ejecución de los flujos de trabajo del sistema.

## 2. Arquitectura del Servicio

### 2.1 Componentes Principales

![Diagrama de Arquitectura](./diagrams/agent_orchestrator_architecture.png)

Como servicio de nivel 1 (orquestación), el Agent Orchestrator Service está compuesto por los siguientes componentes principales:

- **API REST (routes/)**:
  - `chat.py`: Endpoint principal para interacciones de chat
  - `sessions.py`: Gestión de sesiones de usuario
  - `batch.py`: APIs para procesamiento por lotes
  - `internal.py`: APIs internas para otros servicios
  - `health.py`: Health check del servicio

- **Servicios de Negocio (services/)**:
  - `orchestrator.py`: Orquestador principal de flujos de trabajo
  - `session_manager.py`: Gestión del ciclo de vida de sesiones
  - `service_coordinator.py`: Coordinación entre servicios
  - `rate_limiter.py`: Control de tasa de peticiones por tenant

- **Sistema de Colas (queue/)**:
  - `consumer.py`: Consumidor de cola de tareas
  - `producer.py`: Productor de tareas
  - `tasks/`:
    - `chat_tasks.py`: Tareas procesamiento de chat
    - `orchestration_tasks.py`: Tareas de orquestación

- **Comunicación en tiempo real (websocket/)**:
  - `connection_manager.py`: Gestión de conexiones WebSocket
  - `events.py`: Definición de tipos de eventos
  - `handlers.py`: Manejadores de eventos específicos

- **Middleware (middleware/)**:
  - `auth.py`: Autenticación de solicitudes
  - `rate_limit.py`: Limitación de tasa de peticiones
  - `context.py`: Propagación de contexto

- **Modelos (models/)**:
  - `message.py`: MessageBase, DomainAction, ServiceMessage
  - `chat.py`: ChatRequest, ChatResponse
  - `session.py`: Session, SessionState
  - `orchestration.py`: OrchestrationPlan, ServiceCall
  - `batch.py`: BatchRequest, BatchResponse
  - `domain_actions.py`: Definición de todos los domain/action soportados

#### Mapa de Responsabilidades del Orquestador con Estándar Domain/Action

```
+----------------------------------------------------------+
|                   AGENT ORCHESTRATOR                     |
+----------------------------------------------------------+
| RESPONSABILIDADES PRINCIPALES:                           |
|                                                          |
| 1. ◆ Punto único de entrada para ejecucion de workflows y conversaciones|
| 2. ◆ Gestión global de sesiones y contexto               |
| 3. ◆ Orquestación de tareas entre servicios via domain/action   |
| 4. ◆ Seguimiento del estado con correlation_id unificado   |
| 5. ◆ Servidor WebSocket para notificaciones domain/action  |
| 6. ◆ Aplicación de políticas de seguridad y tenancy      |
| 7. ◆ Validación de mensajes con estándar domain/action   |
+----------------------------------------------------------+
```


### 2.2 Implementación del Estándar Domain/Action

El Agent Orchestrator Service implementa un estándar de comunicación unificado basado en el patrón domain/action para todas las interacciones entre servicios, flujos asíncronos y notificaciones en tiempo real.

#### 2.2.1 Estructura Base de Mensajes

Todos los mensajes intercambiados entre servicios siguen esta estructura estándar:

```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "type": {
    "domain": "string",
    "action": "string"
  },
  "schema_version": "1.0",
  "created_at": "ISO-8601 timestamp",
  "tenant_id": "string",
  "source_service": "string",
  "target_service": "string",
  "priority": 0-9,
  "data": {} // payload específico del mensaje
}
```

#### 2.2.2 Dominios Principales

| Dominio | Descripción | Ejemplos de Acciones |
|---------|-------------|---------------------|
| `session` | Gestión de sesiones de usuario | create, update, close |
| `chat` | Interacciones conversacionales | message, typing, history |
| `workflow` | Definición y ejecución de workflows | define, execute, status, cancel |
| `agent` | Operaciones con agentes | invoke, configure, feedback |
| `tool` | Herramientas y extensiones | register, execute, list |
| `system` | Operaciones del sistema | notification, error, metric |

#### 2.2.3 Beneficios para la Arquitectura

- **Desacoplamiento**: Los servicios se comunican mediante mensajes con un formato estandarizado
- **Trazabilidad**: Cada mensaje mantiene su cadena de correlación completa
- **Escalabilidad**: Se pueden enrutar mensajes basados en dominio y acción
- **Mantenibilidad**: Estructura consistente en todo el sistema
- **Documentación Autogenerada**: Los mensajes son autodocumentados

### 2.3 Flujo de Datos con Estándar Domain/Action

1. Las solicitudes llegan desde el frontend a través de la API REST o WebSocket y son clasificadas por dominio y acción
2. Se valida la autenticación y pertenencia al tenant correcto mediante middleware
3. El controlador correspondiente procesa la solicitud y la envía al orquestador con un formato domain/action estandarizado
4. El orquestador determina el plan de ejecución basándose en el dominio y acción de la solicitud
5. El coordinador de servicios distribuye las tareas usando colas específicas por dominio y acción con la estructura:
   ```
   service-name.[priority].[domain].[action]
   ```
6. Las tareas se envían a Redis Queue con metadatos estándar: `message_id`, `correlation_id`, `task_id`, etc.
7. El sistema mantiene seguimiento del estado usando el `correlation_id` para relacionar solicitudes y respuestas
8. Los servicios individuales notifican su progreso y resultados manteniendo el mismo `correlation_id` y formato domain/action
9. El orquestador combina los resultados intermedios según el plan de orquestación
10. Se envían respuestas y actualizaciones al cliente vía HTTP o WebSocket, siguiendo la estructura domain/action en eventos WebSocket

Este flujo permite la ejecución coordinada de operaciones complejas que involucran múltiples servicios, manteniendo el control centralizado del proceso y el feedback en tiempo real al usuario. El estándar domain/action facilita el enrutamiento, trazabilidad y escalabilidad del sistema.

#### Sistema de Colas Multi-tenant con Estándar Domain/Action

##### Estructura Jerárquica de Colas

Las colas del orquestador implementan el estándar domain/action para unificar la comunicación entre servicios, manteniendo la estructura jerárquica original con un esquema de nomenclatura mejorado:

```
                  +---------------------------+
                  |    COLAS DE ORQUESTADOR   |
                  +---------------------------+
                               |
         +--------------------+-----------------+
         |                    |                 |
+----------------+  +------------------+  +---------------+
| Nivel Sesión   |  | Nivel Tarea     |  | Nivel Sistema |
+----------------+  +------------------+  +---------------+
|                |  |                  |  |               |
| orchestrator.  |  | orchestrator.    |  | orchestrator. |
| [priority].    |  | [priority].      |  | [priority].   |
| session.       |  | workflow.        |  | system.       |
| [action]       |  | [action]         |  | [action]      |
+----------------+  +------------------+  +---------------+
```

##### Estándar de Nomenclatura Domain/Action

Cada cola sigue la convención estandarizada:
```
service-name.[priority].[domain].[action]
```
Donde:
- **service-name**: Nombre del servicio (ej. orchestrator, workflow-engine)
- **priority**: Prioridad de la cola (high, medium, low)
- **domain**: Dominio funcional (session, workflow, tool, agent)
- **action**: Operación específica (define, execute, status, cancel)

##### Tipos de Colas

1. **Colas de Nivel Sesión**:
   - `orchestrator.high.session.create`
   - `orchestrator.medium.session.update`
   - `orchestrator.medium.session.state`
   - Propósito: Gestión de sesiones activas y su estado
   - Datos: Estado de la conversación, historial, contexto activo

2. **Colas de Nivel Tarea**:
   - `orchestrator.high.workflow.execute`
   - `orchestrator.medium.workflow.status`
   - `orchestrator.high.agent.invoke`
   - Propósito: Tracking global de todas las tareas del tenant
   - Estructura: Registro central de tareas distribuidas en otros servicios

3. **Colas de Sistema**:
   - `orchestrator.medium.system.notification`
   - `orchestrator.high.system.error`
   - Propósito: Gestión de notificaciones y errores internos del sistema

##### Beneficios de la Implementación Domain/Action

- **Enrutamiento Inteligente**: Los mensajes se dirigen automáticamente al servicio correcto basado en el dominio
- **Priorización Clara**: Niveles de prioridad explícitos para gestión de carga
- **Trazabilidad Mejorada**: Facilitación de seguimiento end-to-end de operaciones
- **Escalabilidad**: Permite escalar consumidores específicamente por dominio y acción

## 3. Dependencias

### 3.1 Servicios Internos

| Servicio | Propósito | Tipo de Interacción | Naturaleza de la Interacción |
|----------|-----------|---------------------|----------------------------|
| Conversation Service | Historial y contexto de conversación | Redis Queue, Redis PubSub, REST API | Bidireccional, coordinación de conversaciones |
| Agent Execution Service | Ejecución específica de agentes | Redis Queue, Redis PubSub, REST API | Bidireccional, delegación de tareas |
| Workflow Engine | Flujos de trabajo complejos | Redis Queue, Redis PubSub, REST API | Bidireccional, coordinación de workflows |
| Tool Registry Service | Registro y ejecución de herramientas | Redis Queue, Redis PubSub, REST API | Bidireccional, ejecución de herramientas |
| Agent Management Service | Configuración de agentes | Redis PubSub, REST API | Consumidor (sólo lectura) |
| Query Service | Procesamiento RAG y LLM | Redis Queue, REST API | Bidireccional, delegación |
| Embedding Service | Generación de embeddings | Redis Queue, REST API | Unidireccional, delegación |
| Ingestion Service | Procesamiento de documentos | Redis Queue, Redis PubSub | Bidireccional, delegación y monitoreo |
| Identity Service | Autenticación/Autorización | REST API | Validación de tokens y permisos |
| Monitoring Service | Métricas y salud del servicio | REST API | Recolección de telemetría |

### 3.2 Servicios Externos

| Servicio | Propósito | Tipo de Interacción |
|----------|-----------|---------------------|
| PostgreSQL | Base de datos principal | TCP/IP |
| Redis | Procesamiento asíncrono (Redis Queue) + Mensajería (PubSub) + Caché + Estado de sesión | TCP/IP |
| Prometheus | Monitoreo y alertas | TCP/IP |
| CloudWatch/DataDog | Logging centralizado | TCP/IP |

### 3.3 Librerías y Frameworks

- **FastAPI**: Framework web principal
- **SQLAlchemy**: ORM para acceso a base de datos
- **Pydantic**: Validación de modelos y esquemas
- **Redis/aioredis**: Cliente asíncrono para Redis
- **RQ (Redis Queue)**: Procesamiento asíncrono de tareas
- **Websockets**: Gestión de conexiones websocket
- **AsyncIO**: Programación asíncrona
- **OpenTelemetry**: Distributed tracing
- **Prometheus Client**: Exportación de métricas
- **Tenacity**: Reintentos con backoff exponencial

## 4. Configuración y Despliegue

### 4.1 Variables de Entorno

| Variable | Descripción | Valor por defecto | Requerida |
|----------|-------------|-------------------|-----------|
| `DATABASE_URL` | URI de conexión a PostgreSQL | - | Sí |
| `REDIS_URI` | URI de conexión a Redis | - | Sí |
| `SERVICE_PORT` | Puerto del servicio | 8008 | No |
| `LOG_LEVEL` | Nivel de logging | INFO | No |
| `ENVIRONMENT` | Entorno de ejecución | development | No |
| `SECRET_KEY` | Clave para firmar tokens | - | Sí |
| `CONVERSATION_SERVICE_URL` | URL del Conversation Service | - | Sí |
| `AGENT_EXECUTION_SERVICE_URL` | URL del Agent Execution Service | - | Sí |
| `WORKFLOW_ENGINE_URL` | URL del Workflow Engine | - | Sí |
| `TOOL_REGISTRY_URL` | URL del Tool Registry Service | - | Sí |
| `AGENT_MANAGEMENT_URL` | URL del Agent Management Service | - | Sí |
| `QUERY_SERVICE_URL` | URL del Query Service | - | Sí |
| `EMBEDDING_SERVICE_URL` | URL del Embedding Service | - | Sí |
| `IDENTITY_SERVICE_URL` | URL del Identity Service | - | Sí |
| `SERVICE_TOKEN` | Token para autenticación entre servicios | - | Sí |
| `MAX_CONCURRENT_TASKS` | Límite de tareas concurrentes | 100 | No |
| `GLOBAL_RATE_LIMIT` | Límite global de peticiones por minuto | 1000 | No |
| `TENANT_RATE_LIMIT` | Límite por tenant (peticiones por minuto) | 100 | No |
| `SESSION_TTL` | Tiempo de vida de sesiones (segundos) | 3600 | No |
| `TASK_TIMEOUT` | Timeout para tareas (segundos) | 60 | No |
| `RETRY_ATTEMPTS` | Número de reintentos para tareas fallidas | 3 | No |
| `WEBSOCKET_MAX_CONNECTIONS` | Conexiones WebSocket máximas | 10000 | No |

### 4.2 Requisitos de Infraestructura

- **CPU**: Mínimo 4 cores, recomendado 8 cores
- **Memoria**: Mínimo 4GB, recomendado 8GB
- **Almacenamiento**: Mínimo 40GB SSD
- **Escalamiento**: Horizontal mediante múltiples instancias tras un balanceador
- **Red**: Acceso a PostgreSQL, Redis y todos los servicios internos
- **Latencia**: <50ms para comunicaciones entre servicios
- **Alta Disponibilidad**: Configuración multi-AZ recomendada
- **Balanceo de Carga**: Sticky sessions por conexiones WebSocket

## 5. Operaciones y Mantenimiento

### 5.1 Monitoreo y Disponibilidad con Domain/Action

- **Health Check**: Endpoint `/health` con verificación profunda de conexiones a todos los servicios dependientes, organizado por dominios funcionales

- **Métricas Domain/Action**:
  - `{domain}.{action}.request_count`: Contador de solicitudes por dominio y acción
  - `{domain}.{action}.duration_ms`: Histograma de tiempo de ejecución por dominio y acción
  - `{domain}.{action}.error_count`: Contador de errores por dominio y acción
  - `{domain}.queue.depth`: Profundidad de cola por dominio
  - `{domain}.active_tasks`: Tareas activas por dominio
  
- **Logs Estructurados**:
  Formato estructurado JSON con trazabilidad completa usando el estándar domain/action:
  ```json
  {
    "timestamp": "2025-06-04T04:15:00.000Z",
    "level": "info",
    "correlation_id": "uuid-v4",
    "domain": "workflow",
    "action": "execute",
    "tenant_id": "tenant-identifier",
    "message": "Workflow execution started",
    "execution_id": "exec-12345",
    "workflow_id": "doc-processor-v1"
  }
  ```

- **Dashboard por Dominio**: Paneles de control dedicados para cada dominio funcional (workflow, agent, tool, etc.)

- **Alertas Domain/Action**: Alertas configuradas por dominio y acción con umbrales específicos para cada tipo de operación

### 5.2 Respaldo y Recuperación

- **Estado de Sesión**: Persistido en Redis con replicación
- **Tolerancia a Fallos**: Capacidad de reintento automático para tareas fallidas
- **Degradación Elegante**: Modos de funcionamiento parcial si algún servicio downstream falla
- **Plan de Recuperación de Desastres**: RPO 30 minutos, RTO 5 minutos
- **Circuit Breaker Pattern**: Implementado para prevenir cascada de fallos

### 5.3 Multi-tenancia y Seguridad

- **Aislamiento Estricto**: Todas las operaciones validan tenant_id
- **Rate Limiting**: Por tenant y por usuario
- **Auditoría**: Logging detallado de todas las operaciones con metadatos de tenant
- **Protección DoS**: Limitación de conexiones WebSocket y peticiones por IP
- **Validación de Tokens**: Verificación de permisos y scopes para cada operación

## 6. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
