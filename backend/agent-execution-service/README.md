# Agent Execution Service

## Descripción
Servicio encargado de la ejecución de agentes, procesamiento de solicitudes de los usuarios y coordinación con servicios de consulta y embedding.

## Estructura
```
agent-execution-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # AgentExecutionSettings
│   └── constants.py             # Modelos LLM, timeouts
├── models/
│   ├── __init__.py
│   ├── execution.py             # ExecutionRequest, ExecutionResponse
│   ├── prompt.py                # PromptTemplate, PromptConfig
│   ├── completion.py            # CompletionRequest, CompletionResponse
│   └── tool_call.py             # ToolCall, ToolResult
├── routes/
│   ├── __init__.py
│   ├── execute.py               # Endpoints de ejecución
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── langchain_executor.py    # LangChainExecutor principal
│   ├── prompt_processor.py      # Procesamiento de prompts
│   ├── tool_orchestrator.py     # Orquestación de herramientas
│   └── llm_factory.py           # Factory para modelos LLM
├── providers/
│   ├── __init__.py
│   ├── openai_provider.py       # Proveedor OpenAI
│   ├── groq_provider.py         # Proveedor Groq
│   └── base_provider.py         # Interface base
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── execution_tasks.py    # Tareas de ejecución
│       └── batch_tasks.py        # Procesamiento por lotes
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
1. Ejecución de agentes con LLMs (Groq, OpenAI)
2. Procesamiento de prompts y completion
3. Orquestación de herramientas y llamadas a herramientas
4. Streaming de respuestas generativas

## Sistema de Cola de Trabajo
- **Tareas**: Procesamiento asíncrono de ejecuciones complejas, lotes de inferencias
- **Implementación**: Redis Queue con prioridad para tareas críticas
- **Procesamiento**: Tareas en segundo plano para ejecuciones que requieren más tiempo

## Comunicación
- **HTTP**: API REST para solicitudes de ejecución
- **WebSocket**: Streaming de respuestas y actualizaciones de ejecución
- **Callbacks**: Notificaciones de finalización de tareas en cola

## Integración con otros Servicios
El Agent Execution Service se comunica principalmente con:
1. Tool Registry Service: Para ejecutar herramientas durante el proceso de razonamiento
2. Agent Management Service: Para obtener configuraciones de agentes
3. Agent Orchestrator Service: Para solicitar operaciones de consulta o embedding (NO directamente con Query/Embedding Services)