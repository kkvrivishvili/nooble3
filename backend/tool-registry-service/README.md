# Tool Registry Service

## Descripción
Servicio encargado del registro, validación y ejecución de herramientas (tools) que pueden ser utilizadas por los agentes. Proporciona un mecanismo central para descubrir y utilizar herramientas de forma segura y controlada.

## Estructura
```
tool-registry-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # ToolRegistrySettings
│   └── constants.py             # Tipos de herramientas
├── models/
│   ├── __init__.py
│   ├── tool.py                  # Tool, ToolConfig, ToolMetadata
│   ├── registration.py          # ToolRegistration, ToolUpdate
│   └── execution.py             # ToolExecutionRequest/Response
├── routes/
│   ├── __init__.py
│   ├── tools.py                 # CRUD de herramientas
│   ├── registry.py              # Registro y discovery
│   ├── internal.py              # Ejecución de herramientas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── tool_registry.py         # Registro central
│   ├── tool_validator.py        # Validación de herramientas
│   └── tool_factory.py          # Factory de herramientas
├── tools/
│   ├── __init__.py
│   ├── base.py                  # BaseTool interface
│   ├── rag_tools.py             # RAGQueryTool, RAGSearchTool
│   ├── general_tools.py          # Calculator, DateTime, etc.
│   └── external_api_tool.py      # ExternalAPITool
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── tool_execution_tasks.py # Tareas de ejecución de herramientas
│       └── registration_tasks.py  # Tareas de registro y validación
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
1. Registro y discovery de herramientas disponibles
2. Validación de permisos y configuraciones
3. Ejecución segura de herramientas
4. Abstracción de APIs externas

## Sistema de Cola de Trabajo
- **Tareas**: Ejecución asíncrona de herramientas de larga duración, validación de herramientas externas
- **Implementación**: Redis Queue con sistema de resultados y estado
- **Procesamiento**: Herramientas que requieren tiempo de ejecución prolongado

## Comunicación
- **HTTP**: API REST para registro y ejecución de herramientas
- **WebSocket**: Actualizaciones en tiempo real del estado de ejecución
- **Callbacks**: Notificaciones de finalización de tareas en cola

## Integración con otros Servicios
El Tool Registry Service se comunica exclusivamente a través del Agent Orchestrator Service, que actúa como intermediario para todas las interacciones con otros servicios:

1. Agent Execution Service: Para proporcionar herramientas a los agentes
2. Agent Management Service: Para validar permisos de herramientas
3. Workflow Engine Service: Para herramientas utilizadas en flujos de trabajo

Además, no se comunica directamente con el Query Service ni el Embedding Service, sino que todas las operaciones RAG o de embeddings son solicitadas a través del Agent Orchestrator Service, manteniendo así la arquitectura centralizada.