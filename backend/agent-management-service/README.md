# Agent Management Service

## Descripción
Servicio responsable de la gestión del ciclo de vida de los agentes: creación, actualización, eliminación y consulta de configuraciones de agentes.

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