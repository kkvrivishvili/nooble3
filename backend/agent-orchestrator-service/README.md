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
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md