# Estructura del Servicio - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Estructura del Servicio - Agent Management Service](#estructura-del-servicio---agent-management-service)
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

El **Agent Management Service** es responsable de la gestión del ciclo de vida completo de los agentes inteligentes dentro del ecosistema Nooble. Este servicio debe ser accedido **directamente por el frontend** para todas las operaciones de gestión de agentes, sin intermediación del Orchestrator Service.

Sus principales responsabilidades son:

- Creación, configuración, actualización y eliminación de agentes directamente desde el frontend
- Versionado de configuraciones de agentes
- Gestión de plantillas de agentes para rápida implementación
- Control de estado de los agentes (activación, desactivación)
- Validación de configuraciones de agentes según tier del usuario
- Almacenamiento de configuraciones actualizadas para su uso por servicios de ejecución
- Control de acceso basado en tenants

Este servicio actúa como el repositorio central de configuración para todos los agentes del sistema y sirve como fuente de verdad para sus definiciones y estados, manteniendo estrictas garantías de atomicidad y aislamiento multi-tenant como principios fundamentales de diseño. El Agent Execution Service y otros servicios operacionales solo deberían consumir estas configuraciones, nunca gestionarlas.

## 2. Arquitectura del Servicio

### 2.1 Componentes Principales

![Diagrama de Arquitectura](./diagrams/agent_management_architecture.png)

Siguiendo el mismo patrón arquitectónico que otros servicios de nivel 2 como Query Service y Embedding Service, el Agent Management Service está compuesto por los siguientes componentes organizados por responsabilidad:

- **API REST (routes/)**: Interfaz que expone los endpoints HTTP para interacción con el frontend y otros servicios
  - `agents.py`: CRUD endpoints públicos
  - `templates.py`: Endpoints de templates
  - `internal.py`: APIs internas para otros servicios
  - `health.py`: Health check

- **Servicios de Negocio (services/)**:
  - `agent_manager.py`: Lógica de negocio principal
  - `validation_service.py`: Validación de configuraciones
  - `template_service.py`: Gestión de templates

- **Sistema de Colas (queue/)**:
  - `consumer.py`: Consumidor de Redis Queue
  - `producer.py`: Productor de tareas Redis Queue
  - `pubsub.py`: Cliente Redis PubSub para notificaciones
  - `tasks/agent_tasks.py`: Definiciones de tareas asíncronas
  
- **Comunicación en tiempo real (websocket/)**:
  - `connection_manager.py`: Gestión de conexiones WebSocket
  - `events.py`: Definición de eventos
  - `handlers.py`: Manejadores de eventos
  - `notifier.py`: Notificador para comunicación con el orquestador

- **Modelos (models/)**:
  - `agent.py`: Agent, AgentCreate, AgentUpdate, AgentConfig
  - `validation.py`: AgentValidation, TierValidation
  - `templates.py`: Modelos de templates de agentes

- **Utilidades (utils/)**:
  - `tier_validator.py`: Validación específica de tiers

### 2.2 Flujo de Datos

1. Las solicitudes llegan **directamente desde el frontend** a través de la API REST
2. Se valida la autenticación y pertenencia al tenant correcto
3. El controlador correspondiente procesa la solicitud y la envía al servicio adecuado
4. El servicio aplica la lógica de negocio, incluyendo validaciones específicas por tier
5. Las operaciones críticas se ejecutan dentro de transacciones Redis para garantizar atomicidad
6. El repositorio gestiona la persistencia de los datos con filtrado por tenant_id
7. Las tareas asíncronas se envían a Redis Queue para procesamiento en segundo plano
8. Las notificaciones de cambios se publican a través de Redis PubSub en canales específicos por tenant
9. Las actualizaciones en tiempo real se envían a servicios interesados (incluyendo el Agent Execution Service) vía WebSocket y Redis PubSub para mantenerlos informados sobre cambios en las configuraciones
10. Se envían respuestas al cliente a través de la API REST

> **IMPORTANTE**: El Agent Orchestrator Service no debe actuar como intermediario para operaciones CRUD de agentes. Solo debe leer las configuraciones cuando las necesita para ejecución de workflows.

## 3. Dependencias

### 3.1 Servicios Internos

| Servicio | Propósito | Tipo de Interacción | Naturaleza de la Interacción |
|----------|-----------|---------------------|-----------------------------|
| Frontend | Interfaz de usuario para gestión de agentes | REST API | Cliente principal para operaciones CRUD |
| Tool Registry Service | Validación de herramientas | REST API, Redis PubSub | Consulta para validación |
| Agent Execution Service | Ejecución de agentes | Redis PubSub | Consumidor de configuraciones |
| Agent Orchestrator Service | Coordinación de workflows | Redis PubSub | Consumidor de configuraciones (solo lectura) |
| Identity Service | Autenticación/Autorización | REST API | Validación de tokens y permisos |
| Monitoring Service | Métricas y salud del servicio | REST API | Recolección de telemetría |

> **NOTA IMPORTANTE**: A diferencia de la estructura anterior, el Agent Management Service debe ser accedido directamente por el frontend para operaciones CRUD. El Agent Orchestrator NO debe intermediar estas operaciones, sino sólo consumir las configuraciones cuando las necesita para workflows.

### 3.2 Servicios Externos

| Servicio | Propósito | Tipo de Interacción |
|----------|-----------|---------------------|
| PostgreSQL | Base de datos principal | TCP/IP |
| Redis | Procesamiento asíncrono (Redis Queue) + Mensajería (PubSub) + Caché | TCP/IP |
| S3/Blob Storage | Almacenamiento de archivos grandes | REST API |

### 3.3 Librerías y Frameworks

- **FastAPI**: Framework web principal
- **SQLAlchemy**: ORM para acceso a base de datos
- **Pydantic**: Validación de modelos y esquemas
- **Redis/aioredis**: Cliente asíncrono para Redis
- **RQ (Redis Queue)**: Procesamiento asíncrono de tareas
- **Websockets**: Gestión de conexiones websocket
- **Alembic**: Migraciones de base de datos
- **Prometheus Client**: Exportación de métricas

## 4. Configuración y Despliegue

### 4.1 Variables de Entorno

| Variable | Descripción | Valor por defecto | Requerida |
|----------|-------------|-------------------|-----------|
| `DATABASE_URL` | URI de conexión a PostgreSQL | - | Sí |
| `REDIS_URI` | URI de conexión a Redis (para Queue, PubSub y caché) | - | Sí |
| `SERVICE_PORT` | Puerto del servicio | 8080 | No |
| `LOG_LEVEL` | Nivel de logging | INFO | No |
| `ENVIRONMENT` | Entorno de ejecución | development | No |
| `SECRET_KEY` | Clave para firmar tokens | - | Sí |
| `TOOL_REGISTRY_URL` | URL del Tool Registry Service | - | Sí |
| `IDENTITY_SERVICE_URL` | URL del Identity Service | - | Sí |
| `ORCHESTRATOR_WS_URL` | URL del WebSocket del orquestador | - | Sí |
| `SERVICE_TOKEN` | Token para autenticación entre servicios | - | Sí |
| `MAX_AGENTS_PER_TENANT` | Límite de agentes por tenant | 50 | No |
| `ENABLE_WEBSOCKETS` | Habilitar websockets | true | No |
| `REDIS_QUEUE_TTL` | TTL para trabajos en cola (segundos) | 3600 | No |

### 4.2 Requisitos de Infraestructura

- **CPU**: Mínimo 2 cores, recomendado 4 cores
- **Memoria**: Mínimo 2GB, recomendado 4GB
- **Almacenamiento**: Mínimo 20GB SSD
- **Escalamiento**: Horizontal mediante múltiples instancias
- **Red**: Acceso a PostgreSQL, Redis y otros servicios internos
- **Latencia**: <100ms para comunicaciones entre servicios

## 5. Operaciones y Mantenimiento

### 5.1 Monitoreo y Disponibilidad

- **Health Check**: Endpoint `/health` para verificación de estado con validación de conexión a Redis y base de datos
- **Métricas**: Exposición de métricas en formato Prometheus en `/metrics` incluyendo métricas por tenant
- **Logs**: Formato estructurado JSON con campos estandarizados como `tenant_id`, `task_id` y `correlation_id`
- **Alertas**: Configuración de alertas para fallas de transacciones o violaciones de aislamiento

### 5.2 Respaldo y Recuperación

- **Backup de Base de Datos**: Diario con retención de 30 días
- **Snapshots de Redis**: Backup automático cada 6 horas
- **Plan de Recuperación de Desastres**: RPO 1 hora, RTO 10 minutos
- **Mantenimiento Programado**: Ventana semanal de 30 minutos en horas de baja actividad

### 5.3 Multi-tenancia y Seguridad

- **Auditoría de Operaciones**: Registro detallado por tenant para todas las modificaciones
- **Aislamiento de Recursos**: Monitoreo de límites de consumo por tenant
- **Scanning de Vulnerabilidades**: Revisiones semanales automatizadas
- **Acceso Directo**: El acceso a este servicio para operaciones CRUD debe realizarse directamente desde el frontend
- **Principio de Mínimo Privilegio**: Los servicios consumidores (como Agent Execution o Agent Orchestrator) solo tienen permisos de lectura sobre las configuraciones
- **Control de Acceso Granular**: Los permisos se validan no solo a nivel de tenant sino también por operación específica

## 6. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
| 1.0.1 | 2025-06-03 | Actualización para reflejar uso de Redis Queue + PubSub en lugar de RabbitMQ |
