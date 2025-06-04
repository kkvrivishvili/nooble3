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
  - `chat.py`: ChatRequest, ChatResponse
  - `session.py`: Session, SessionState
  - `orchestration.py`: OrchestrationPlan, ServiceCall
  - `batch.py`: BatchRequest, BatchResponse

### 2.2 Flujo de Datos

1. Las solicitudes llegan desde el frontend a través de la API REST o WebSocket
2. Se valida la autenticación y pertenencia al tenant correcto mediante middleware
3. El controlador correspondiente procesa la solicitud y la envía al orquestador
4. El orquestador determina el plan de ejecución y los servicios a involucrar
5. El coordinador de servicios distribuye las tareas entre los servicios apropiados
6. Las tareas se envían a Redis Queue para procesamiento asíncrono
7. El sistema mantiene seguimiento del estado general de la tarea y sus subtareas
8. Los servicios individuales notifican su progreso y resultados
9. El orquestador combina los resultados intermedios según el plan
10. Se envían respuestas y actualizaciones al cliente vía HTTP o WebSocket

Este flujo permite la ejecución coordinada de operaciones complejas que involucran múltiples servicios, manteniendo el control centralizado del proceso y el feedback en tiempo real al usuario.

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

### 5.1 Monitoreo y Disponibilidad

- **Health Check**: Endpoint `/health` con verificación profunda de conexiones a todos los servicios dependientes
- **Métricas Críticas**:
  - Tasa de completitud de workflows
  - Latencia entre recepción y respuesta
  - Tasa de errores por servicio downstream
  - Utilización de memoria y conexiones
  - Tiempo de respuesta por tipo de flujo
- **Logs**: Formato estructurado JSON con trazabilidad completa de solicitudes usando IDs de correlación
- **Alertas**: Múltiples niveles de alertas (advertencia/crítica) configuradas para umbrales de latencia y errores

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
