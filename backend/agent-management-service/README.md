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
├── utils/
│   ├── __init__.py
│   └── tier_validator.py        # Validación específica de tiers
├── main.py                      # FastAPI app
├── requirements.txt             # Dependencias específicas
├── Dockerfile
└── README.md