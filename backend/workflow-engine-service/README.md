# Workflow Engine Service

## Descripción
Servicio responsable de definir, gestionar y ejecutar flujos de trabajo (workflows) para orquestación de tareas complejas. Permite la creación de flujos basados en nodos interconectados con condiciones y transiciones.

## Estructura
```
workflow-engine-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # WorkflowEngineSettings
│   └── constants.py             # Estados, tipos de nodos
├── models/
│   ├── __init__.py
│   ├── workflow.py              # Workflow, WorkflowDefinition
│   ├── node.py                  # WorkflowNode, NodeConnection
│   ├── execution.py             # WorkflowExecution, ExecutionState
│   └── step.py                  # WorkflowStep, StepResult
├── routes/
│   ├── __init__.py
│   ├── workflows.py             # CRUD workflows
│   ├── execution.py             # Ejecución de workflows
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── workflow_manager.py      # Gestión de definiciones
│   ├── workflow_executor.py     # Motor de ejecución
│   ├── state_manager.py         # Gestión de estado
│   └── step_processor.py        # Procesador de pasos
├── engine/
│   ├── __init__.py
│   ├── conditions.py            # Evaluador de condiciones
│   ├── transitions.py           # Gestor de transiciones
│   └── variables.py             # Gestor de variables
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── workflow_tasks.py      # Tareas de ejecución de workflows
│       └── step_tasks.py          # Procesamiento de pasos individuales
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
1. Definición y gestión de workflows basados en nodos
2. Ejecución de workflows con maquina de estados
3. Procesamiento condicional y ramificaciones
4. Gestión de variables y contexto entre pasos

## Sistema de Cola de Trabajo
- **Tareas**: Ejecución de workflows completos y pasos individuales
- **Implementación**: Redis Queue con sistema de estado distribuido
- **Procesamiento**: Workflows de larga duración con puntos de control

## Comunicación
- **HTTP**: API REST para definición y gestión de workflows
- **WebSocket**: Actualizaciones en tiempo real del estado de ejecución
- **Callbacks**: Notificaciones en puntos clave del workflow

## Integración con otros Servicios
El Workflow Engine Service se comunica principalmente con el Agent Orchestrator Service, que actúa como intermediario central para todas las interacciones con otros servicios del sistema:

1. Agent Orchestrator Service: Punto principal de comunicación para orquestar flujos complejos
2. Tool Registry Service: No hay comunicación directa, sino a través del orquestador para ejecutar herramientas
3. Conversation Service: No hay comunicación directa, sino a través del orquestador para workflows basados en conversaciones
4. Agent Execution Service: No hay comunicación directa, sino a través del orquestador para ejecución de agentes

Este patrón de comunicación centralizada asegura la consistencia en el control de acceso, el seguimiento de tokens y la trazabilidad de las operaciones en todo el sistema.