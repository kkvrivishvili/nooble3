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
│   ├── general_tools.py         # Calculator, DateTime, etc.
│   └── external_api_tool.py     # ExternalAPITool
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md