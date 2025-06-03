# Conversation Service

## Descripción
Servicio encargado de gestionar las conversaciones entre usuarios y agentes, incluyendo historial, contexto y seguimiento de sesiones.

## Estructura
```
conversation-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # ConversationSettings
│   └── constants.py             # TTLs, límites de memoria
├── models/
│   ├── __init__.py
│   ├── conversation.py          # Conversation, ConversationCreate
│   ├── message.py               # Message, MessageRole, MessageCreate
│   ├── memory.py                # ConversationMemory, MemoryWindow
│   └── session.py               # Session, SessionContext
├── routes/
│   ├── __init__.py
│   ├── conversations.py         # CRUD conversaciones
│   ├── messages.py              # Gestión de mensajes
│   ├── internal.py              # APIs para Agent Execution
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── conversation_manager.py  # Gestión de conversaciones
│   ├── message_store.py         # Almacenamiento de mensajes
│   ├── memory_manager.py        # ConversationMemoryManager (mejorado)
│   └── context_tracker.py       # Tracking de contexto
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       └── message_tasks.py     # Tareas asíncronas de procesamiento
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── utils/
│   ├── __init__.py
│   └── memory_utils.py          # Utilidades para memoria
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## Funciones Clave
1. Gestión de conversaciones y mensajes
2. Mantenimiento de contexto de conversación
3. Streaming de respuestas en tiempo real
4. Persistencia de historial con metadatos enriquecidos

## Sistema de Cola de Trabajo
- **Tareas**: Procesamiento asíncrono de mensajes, generación de resúmenes, análisis de sentimiento
- **Implementación**: Redis Queue con priorización de mensajes
- **Procesamiento**: Tareas en segundo plano para optimizar la experiencia del usuario

## Comunicación
- **HTTP**: API REST para creación y consulta de conversaciones/mensajes
- **WebSocket**: Streaming de respuestas y actualizaciones en tiempo real
- **Callbacks**: Notificaciones asíncronas al finalizar tareas en cola

## Integración con otros Servicios
El Conversation Service se comunica exclusivamente a través del Agent Orchestrator Service, que actúa como intermediario para todas las interacciones con:

1. Agent Execution Service: Para procesamiento de mensajes a través de agentes
2. Agent Management Service: Para validación de configuraciones
3. Workflow Engine Service: Para conversaciones basadas en flujos de trabajo

No se realizan comunicaciones directas con otros servicios sin pasar por el orquestador central, manteniendo así la arquitectura de microservicios correctamente aislada y gestionada.