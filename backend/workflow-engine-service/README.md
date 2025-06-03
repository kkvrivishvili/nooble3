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
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md