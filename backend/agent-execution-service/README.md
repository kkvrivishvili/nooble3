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
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md