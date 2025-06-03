# Agent Management Service

## Descripción
Servicio responsable de la gestión del ciclo de vida de los agentes: creación, actualización, eliminación y consulta de configuraciones de agentes.

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

> 📌 **Este documento describe el Agent Management Service**, ubicado en el Nivel 2 como servicio funcional encargado de la gestión completa del ciclo de vida de agentes.

## 🔄 Flujos de Trabajo Principales

### 1. Creación y Configuración de Agentes
```
Cliente → Orchestrator → Agent Management → Validación → Persistencia → Notificación
```

### 2. Actualización de Configuración de Agente
```
Cliente → Orchestrator → Agent Management → Validación → Persistencia → Notificación → Actualización en cachés de servicios
```

> 🔍 **Rol del Agent Management**: Gestionar y validar las configuraciones de agentes, asegurando consistencia y disponibilidad para toda la plataforma.

## Estructura
```
agent-management-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # AgentManagementSettings
│   └── constants.py             # Constantes específicas del dominio
├── models/
│   ├── __init__.py
│   ├── agent.py                 # Agent, AgentCreate, AgentUpdate, AgentConfig
│   ├── validation.py            # AgentValidation, TierValidation
│   └── templates.py             # AgentTemplate models
├── routes/
│   ├── __init__.py
│   ├── agents.py                # CRUD endpoints públicos
│   ├── templates.py             # Endpoints de templates
│   ├── internal.py              # APIs internas para otros servicios
│   └── health.py                # Health check
├── services/
│   ├── __init__.py
│   ├── agent_manager.py         # Lógica de negocio principal
│   ├── validation_service.py    # Validación de configuraciones
│   └── template_service.py      # Gestión de templates
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       └── agent_tasks.py       # Tareas asíncronas de gestión
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── utils/
│   ├── __init__.py
│   └── tier_validator.py        # Validación específica de tiers
├── main.py                      # FastAPI app
├── requirements.txt             # Dependencias específicas
├── Dockerfile
└── README.md
```

## 🚦 Sistema de Colas Multi-tenant

### Estructura Jerárquica de Colas del Agent Management Service

```
+--------------------------------------------------+
|           COLAS DE AGENT MANAGEMENT               |
+--------------------------------------------------+
|                                                  |
| agent_management:{tenant_id}                     | → Cola principal de tareas
| agent_validation:{tenant_id}                     | → Validación de configuraciones
| agent_template:{tenant_id}                       | → Operaciones con plantillas
| agent_notifications:{tenant_id}                  | → Notificaciones de cambios
|                                                  |
+--------------------------------------------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **Validación asíncrona**: Verificación completa de configuraciones de agentes
- **Distribución de actualizaciones**: Propagación de cambios a otros servicios
- **Historización de cambios**: Registro de todas las modificaciones por auditoría

### Formato de Mensaje Estandarizado

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "agent_create|agent_update|agent_validate|agent_notify",
  "priority": 0-9,
  "metadata": {
    "user_id": "user-identifier",
    "source": "api|orchestrator|system"
  },
  "payload": {
    "agent_id": "agent-identifier",
    "agent_name": "nombre-agente",
    "agent_type": "tipo-agente",
    "version": "1.0",
    "config": {},
    "tools": []
  }
}
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- **Integración con orquestador**: Conexión bidireccional con Agent Orchestrator
- **Publicación de cambios**: Notificación de actualizaciones en configuraciones
- **Reconexión automática**: Mecanismo de backoff exponencial para mayor resiliencia
- **Autenticación por token**: Comunicación segura entre servicios

### Eventos Específicos del Agent Management Service

- `agent_created`: Nuevo agente creado en el sistema
- `agent_updated`: Configuración de agente actualizada
- `agent_deleted`: Agente eliminado del sistema
- `agent_validated`: Validación de configuración completada
- `agent_template_created`: Nueva plantilla de agente disponible

### Implementación WebSocket para Notificaciones:

```python
# websocket/notifier.py
import asyncio
import websockets
import json
import logging
from datetime import datetime

ORCHESTRATOR_WS_URL = "ws://agent-orchestrator:8000/ws/task_updates"

logger = logging.getLogger(__name__)

async def notify_agent_change(task_id, tenant_id, agent_data, event_type, global_task_id=None):
    """Notifica sobre cambios en la configuración de agentes"""
    try:
        async with websockets.connect(ORCHESTRATOR_WS_URL) as websocket:
            notification = {
                "event": event_type,  # agent_created, agent_updated, agent_deleted
                "service": "agent-management",
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "agent_id": agent_data["agent_id"],
                    "agent_name": agent_data["agent_name"],
                    "version": agent_data.get("version", "1.0")
                }
            }
            await websocket.send(json.dumps(notification))
            
            # También notificar al canal específico del tenant para actualización de UI
            tenant_notification = {
                "channel": f"tenant:{tenant_id}",
                "event": event_type,
                "data": {
                    "agent_id": agent_data["agent_id"],
                    "agent_name": agent_data["agent_name"]
                }
            }
            await websocket.send(json.dumps(tenant_notification))
    except Exception as e:
        logger.error(f"Error al notificar cambio de agente via WebSocket: {e}")
```

## 🌐 Integración en el Ecosistema

### Beneficios de la Arquitectura

- **Configuración centralizada**: Punto único de verdad para configuraciones de agentes
- **Validación avanzada**: Garantía de que las configuraciones cumplen con requisitos técnicos
- **Versionado de configuraciones**: Historial completo de cambios con capacidad de rollback
- **Templates reutilizables**: Biblioteca de plantillas para rápida creación de nuevos agentes

## Funciones Clave
1. CRUD de agentes
2. Gestión de plantillas de agentes
3. Validación de configuraciones según tier del usuario
4. Notificaciones de actualizaciones de agentes

## Sistema de Cola de Trabajo
- **Tareas**: Actualización masiva de agentes, reconstrucción de índices, sincronización con otros servicios
- **Implementación**: Redis Queue + Redis PubSub para notificaciones
- **Procesamiento**: Operaciones en segundo plano para no bloquear las API principales

## Comunicación
- **HTTP**: API REST para operaciones CRUD
- **WebSocket**: Notificaciones de cambios en agentes
- **Callbacks**: Webhooks para notificaciones a sistemas externos

## Integración con otros Servicios
El Agent Management Service se comunica exclusivamente a través del Agent Orchestrator Service, que actúa como intermediario para todas las interacciones con:

1. Agent Execution Service: Para proporcionar configuraciones de agentes
2. Conversation Service: Para validar agentes en conversaciones
3. Tool Registry Service: Para actualizar herramientas disponibles por agente

No se realizan comunicaciones directas entre servicios sin pasar por el orquestador central, siguiendo el patrón arquitectónico establecido para todo el sistema.