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
├── utils/
│   ├── __init__.py
│   └── memory_utils.py          # Utilidades para memoria
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md