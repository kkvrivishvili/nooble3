# Agent Orchestrator Service

*Versión: 3.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Descripción

Servicio central que coordina las interacciones entre el usuario y los diferentes servicios del sistema. Actúa como un punto de entrada unificado para gestionar el flujo de solicitudes, mantener el estado de sesiones, y orquestar la comunicación entre los múltiples microservicios de la plataforma Nooble AI.

> **IMPORTANTE**: Este servicio es el componente principal de comunicación interna y externa de la plataforma Nooble AI. Implementa el estándar de comunicación **Domain/Action** en todos sus mensajes, APIs y eventos WebSocket para garantizar consistencia, trazabilidad y mantenibilidad a través del sistema completo.

## 📚 Documentación

La documentación del Agent Orchestrator Service está organizada en las siguientes secciones:

### Estándares y Referencias

- [📒 Estándares Globales](standards/global_standards.md) - Punto central de referencia para todos los estándares
- [📘 Estándar Domain/Action](standards/domain_action_standard.md) - Especificación completa del estándar de comunicación
- [📃 Clasificación de Endpoints API](api/endpoints_classification.md) - Catálogo completo de endpoints Domain/Action
- [🧪 Matriz de Errores](errors/error_matrix.md) - Definición de códigos de error por dominio

### Arquitectura y Estructura

- [📍 Estructura del Servicio](structure/structure_service.md) - Organización interna del servicio
- [📈 Flujos End-to-End](structure/end_to_end_flows.md) - Diagramas de secuencia y flujos principales
- [📗 Estados de Sesión](models/session_states.md) - Estados del ciclo de vida de sesiones

### Comunicación

#### Comunicación Interna

- [🔄 Comunicación Interna General](communication/internal/internal_communication.md) - Principios y flujos de comunicación del servicio
- [💡 Esquemas de Mensajes](communication/internal/message_schemas.md) - Formatos estandarizados de mensajes
- [⚙️ Integración con Agent Execution](communication/internal/agent_execution_service.md) - Comunicación con el servicio de ejecución
- [🧠 Integración con Workflow Engine](communication/internal/workflow_engine_service.md) - Orquestación de flujos de trabajo
- [🗄️ Integración con Conversation Service](communication/internal/conversation_service.md) - Gestión de historial y contexto
- [🧰 Integración con Tool Registry](communication/internal/tool_registry_service.md) - Manejo de herramientas externas
- [👤 Integración con Agent Management](communication/internal/agent_management_service.md) - Configuración de agentes

#### Comunicación Externa

- [💬 Eventos WebSocket](communication/websocket/websocket_events.md) - Catálogo de eventos Domain/Action para comunicación en tiempo real
- [🔗 Integración Frontend](communication/frontend/frontend_integration.md) - Guía completa para integración de clientes con Domain/Action
- [🔄 Ejemplos y SDK](communication/frontend/client_sdk.md) - SDK y ejemplos de implementación Domain/Action

### Configuración y Seguridad

- [🔐 Estándares de Seguridad](security/security_standards.md) - Prácticas de seguridad
- [⚙️ Configuración del Servicio](configuration/service_configuration.md) - Variables y ajustes del servicio

> **Nota:** Esta documentación sigue los [Estándares Comunes de Nooble](../../common-standarts/basic_standards.md) incluyendo:
> - [Estándares de Comunicación entre Microservicios](../../common-standarts/microservice_communication_standards_part1.md)
> - [Estándares de Manejo de Errores](../../common-standarts/error_handling_standards.md)
> - [Estándares de Logging](../../common-standarts/logging_standards.md)
> - [Estándares de Métricas](../../common-standarts/metrics_standards.md)

## 🏗️ Ecosistema de Servicios

La arquitectura se organiza en 3 niveles jerárquicos:

### Nivel 1: Orquestación

- **Agent Orchestrator**: Punto de entrada único, gestión de sesiones y coordinación global

### Nivel 2: Servicios Funcionales

- **Conversation Service**: Historial y contexto de conversaciones
- **Workflow Engine**: Flujos de trabajo complejos multi-etapa
- **Agent Execution**: Lógica específica del agente
- **Tool Registry**: Registro y ejecución de herramientas
- **Agent Management**: Gestión del ciclo de vida de agentes

### Nivel 3: Servicios de Infraestructura

- **Query Service**: Procesamiento RAG y LLM
- **Embedding Service**: Generación de embeddings vectoriales
- **Ingestion Service**: Procesamiento de documentos

> 📌 **Este documento describe el Agent Orchestrator Service**, ubicado en el Nivel 1 como componente central de orquestación

## Estructura
```
agent-orchestrator-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # AgentOrchestratorSettings
│   └── constants.py             # Timeouts, rate limits
├── models/
│   ├── __init__.py
│   ├── chat.py                  # ChatRequest, ChatResponse
│   ├── session.py               # Session, SessionState
│   ├── orchestration.py         # OrchestrationPlan, ServiceCall
│   └── batch.py                 # BatchRequest, BatchResponse
├── routes/
│   ├── __init__.py
│   ├── chat.py                  # Endpoint principal de chat
│   ├── sessions.py              # Gestión de sesiones
│   ├── batch.py                 # Procesamiento en lote
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── orchestrator.py          # Orquestador principal
│   ├── session_manager.py       # Gestión de sesiones
│   ├── service_coordinator.py   # Coordinación entre servicios
│   └── rate_limiter.py          # Rate limiting
├── middleware/
│   ├── __init__.py
│   ├── auth.py                  # Autenticación
│   ├── rate_limit.py            # Rate limiting middleware
│   └── context.py               # Context propagation
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── chat_tasks.py         # Tareas de procesamiento de chat
│       └── orchestration_tasks.py # Tareas de orquestación
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## Funciones Clave
1. Punto de entrada unificado para solicitudes de usuarios (API Domain/Action)
2. Orquestación de flujos de trabajo entre servicios (mensajería Domain/Action)
3. Gestión de sesiones y mantenimiento de estado (consistente entre comunicaciones síncronas y asíncronas)
4. Coordinación de respuestas en tiempo real (WebSocket con eventos Domain/Action)
5. Trazabilidad end-to-end con metadatos de correlación en formato Domain/Action

## 🚦 Sistema de Colas Multi-tenant

### Mapa de Responsabilidades del Orquestador

```
+----------------------------------------------------------+
|                   AGENT ORCHESTRATOR                     |
+----------------------------------------------------------+
| RESPONSABILIDADES PRINCIPALES:                           |
|                                                          |
| 1. ◆ Punto único de entrada para ejecucion de workflows y conversaciones                |
| 2. ◆ Gestión global de sesiones y contexto               |
| 3. ◆ Orquestación de tareas entre servicios              |
| 4. ◆ Seguimiento del estado de tareas asíncronas         |
| 5. ◆ Servidor WebSocket para notificaciones              |
| 6. ◆ Aplicación de políticas de seguridad y tenancy      |
+----------------------------------------------------------+
```

### Estructura Jerárquica de Colas (Domain/Action)

```
                  +-----------------------------------+
                  |    COLAS DE ORQUESTADOR (D/A)     |
                  +-----------------------------------+
                               |
         +--------------------+-------------------+
         |                    |                   |
+----------------+  +------------------+  +-------------------+
| Nivel Sesión   |  | Nivel Tarea     |  | Nivel Sistema     |
+----------------+  +------------------+  +-------------------+
|                |  |                  |  |                   |
| orchestrator:  |  | orchestrator:    |  | orchestrator:     |
| session:       |  | task:            |  | system:           |
| {tenant_id}:   |  | {tenant_id}:     |  | {domain}:         |
| {session_id}   |  | {domain}         |  | {action}          |
+----------------+  +------------------+  +-------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Esquema Domain/Action**: Estructura de mensajes estandarizada para toda comunicación
- **Trazabilidad con message_id y correlation_id**: Correlación end-to-end de solicitudes
- **Metadatos enriquecidos**: Versión de esquema, timestamp, servicio fuente
- **Tracking de estado en tiempo real**: Actualización inmediata con mensajes domain/action

### Estructura y Tipos de Colas con Domain/Action

1. **Colas de Nivel Sesión**:
   - `orchestrator:session:{tenant_id}:{session_id}`
   - Propósito: Seguimiento de sesiones activas y su estado
   - Datos: Mensajes Domain/Action para chat, workflow y session
   - Formato: `{message_id, correlation_id, type: {domain, action}, data, ...}`

2. **Colas de Nivel Tarea por Dominio**:
   - `orchestrator:task:{tenant_id}:{domain}`
   - Propósito: Tracking de tareas específicas por dominio (chat, workflow, tool)
   - Estructura: Registro centralizado de tareas con metadata Domain/Action
   - Ejemplo: `orchestrator:task:tenant123:chat` para tareas de chat

3. **Colas de Sistema por Dominio y Acción**:
   - `orchestrator:system:{domain}:{action}`
   - Propósito: Eventos del sistema organizados por domain/action
   - Ejemplos: `orchestrator:system:monitoring:alert`, `orchestrator:system:metrics:report`

## 🔗 Integraciones Principales (Domain/Action)

El Agent Orchestrator Service coordina con todos los demás servicios utilizando el estándar Domain/Action para mensajería interna:

1. **Conversation Service**: Para gestionar el historial de conversaciones
2. **Agent Management Service**: Para obtener configuraciones de agentes
3. **Agent Execution Service**: Para ejecutar agentes
4. **Workflow Engine Service**: Para flujos de trabajo complejos
5. **Tool Registry Service**: Para acceder a herramientas disponibles
6. **Query Service**: Como Único punto de contacto para procesamiento LLM y RAG
7. **Embedding Service**: Como Único punto de contacto para generación de embeddings

Consulte [endpoints_classification.md](api/endpoints_classification.md) para información detallada sobre las APIs.

## ⚙️ Instalación y Configuración

Para instalar y configurar el Agent Orchestrator Service:

1. **Dependencias**: Requiere Python 3.9+, Redis, y conexión a otros servicios
2. **Variables de entorno**: Configure según el documento [service_configuration.md](configuration/service_configuration.md)
3. **Ejecución**: Use Docker Compose o el script `deploy.sh` para desplegar

```bash
# Instalar dependencias
pip install -r requirements.txt

# Iniciar el servicio en modo desarrollo
python main.py
```

## 📜 Referencias Adicionales

El Agent Orchestrator Service se integra con la plataforma Nooble AI siguiendo estos estándares comunes:

- [Microservice Communication Standards](../../common-standarts/microservice_communication_standards_part1.md)
- [Basic Standards](../../common-standarts/basic_standards.md)

## Papel Central en la Arquitectura

El Agent Orchestrator Service actúa como el único punto de contacto para:

1. **Query Service**: Todas las solicitudes de procesamiento LLM y RAG
2. **Embedding Service**: Todas las solicitudes de embeddings (exceptuando Ingestion Service)

Esta centralización garantiza:
- Seguimiento consistente del uso de tokens
- Aplicación de políticas de rate limiting
- Consistencia en el manejo de caché
- Orquestación correcta de operaciones complejas
- Trazabilidad completa de las solicitudes

Para diagramas detallados de los flujos de trabajo, ver [end_to_end_flows.md](structure/end_to_end_flows.md).

---

> **Nota**: Para cualquier consulta o contribución a la documentación, contacte al equipo de backend de Nooble.