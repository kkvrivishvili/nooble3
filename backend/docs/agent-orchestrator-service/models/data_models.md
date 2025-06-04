# Modelos de Datos - Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Modelos de Datos - Agent Orchestrator Service](#modelos-de-datos---agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Modelos Principales](#2-modelos-principales)
    - [2.1 Modelos de Sesión](#21-modelos-de-sesión)
    - [2.2 Modelos de Mensajes](#22-modelos-de-mensajes)
    - [2.3 Modelos de Orquestación](#23-modelos-de-orquestación)
    - [2.4 Modelos de Tareas](#24-modelos-de-tareas)
  - [3. Implementación en Pydantic](#3-implementación-en-pydantic)
  - [4. Ejemplos de Uso](#4-ejemplos-de-uso)
  - [5. Validación y Serialización](#5-validación-y-serialización)

## 1. Introducción

Este documento define los modelos de datos utilizados por el Agent Orchestrator Service para gestionar sesiones, mensajes, planes de orquestación y tareas. Estos modelos garantizan la consistencia de los datos intercambiados entre los diferentes componentes del sistema.

## 2. Modelos Principales

### 2.1 Modelos de Sesión

#### SessionBase
```python
class SessionBase(BaseModel):
    session_id: str  # UUID v4
    tenant_id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    status: str = "active"  # active, inactive, paused, error
    metadata: Dict[str, Any] = {}
```

#### SessionCreate
```python
class SessionCreate(BaseModel):
    tenant_id: str
    user_id: str
    agent_id: str
    initial_context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

#### Session
```python
class Session(SessionBase):
    agent_id: str
    agent_version: str
    agent_config: Dict[str, Any]
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    context: Dict[str, Any] = {}
    session_ttl: int = 1800  # Segundos (30 minutos por defecto)
```

#### SessionUpdate
```python
class SessionUpdate(BaseModel):
    status: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    session_ttl: Optional[int] = None
```

### 2.2 Modelos de Mensajes

#### MessageBase
```python
class MessageBase(BaseModel):
    tenant_id: str
    session_id: str
    message_id: str  # UUID v4
    created_at: datetime
    role: str  # user, assistant, system
    content: str
    metadata: Dict[str, Any] = {}
```

#### UserMessage
```python
class UserMessage(MessageBase):
    role: str = "user"
    stream: bool = False
```

#### AssistantMessage
```python
class AssistantMessage(MessageBase):
    role: str = "assistant"
    completion_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    thinking: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = []
```

#### SystemMessage
```python
class SystemMessage(MessageBase):
    role: str = "system"
    level: str = "info"  # info, warning, error
```

### 2.3 Modelos de Orquestación

#### OrchestrationPlan
```python
class ServiceCall(BaseModel):
    service: str
    operation: str
    parameters: Dict[str, Any] = {}
    dependency_indices: List[int] = []
    retry_policy: Dict[str, Any] = {"max_attempts": 3, "initial_delay_ms": 500}

class OrchestrationPlan(BaseModel):
    plan_id: str  # UUID v4
    tenant_id: str
    session_id: str
    created_at: datetime
    calls: List[ServiceCall]
    execution_strategy: str = "sequential"  # sequential, parallel, conditional
    timeout_ms: int = 30000  # 30 segundos
    completed_calls: List[int] = []
    failed_calls: List[int] = []
    status: str = "pending"  # pending, running, completed, failed
```

#### OrchestrationResult
```python
class ServiceResult(BaseModel):
    service: str
    operation: str
    status: str  # success, error
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    execution_time_ms: int

class OrchestrationResult(BaseModel):
    plan_id: str
    tenant_id: str
    session_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str  # completed, failed, partial
    results: List[ServiceResult] = []
    error: Optional[Dict[str, Any]] = None
    total_execution_time_ms: int
```

### 2.4 Modelos de Tareas

#### Task
```python
class Task(BaseModel):
    task_id: str  # UUID v4
    tenant_id: str
    session_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    status: str = "pending"  # pending, processing, completed, failed
    type: str  # query, embedding, workflow, agent_execution, etc.
    priority: int = 5  # 0-9, 9 es la mayor prioridad
    delegated_services: List[Dict[str, str]] = []
    metadata: Dict[str, Any] = {}
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
```

#### TaskCreate
```python
class TaskCreate(BaseModel):
    tenant_id: str
    session_id: Optional[str] = None
    type: str
    priority: Optional[int] = 5
    metadata: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any]
```

#### TaskUpdate
```python
class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

## 3. Implementación en Pydantic

Ejemplo de implementación completa para el modelo `Session`:

```python
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: str
    agent_id: str
    agent_version: str
    agent_config: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    status: str = "active"
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    session_ttl: int = 1800

    @validator("session_id")
    def validate_session_id(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError("session_id must be a valid UUID")

    @validator("status")
    def validate_status(cls, v):
        valid_statuses = ["active", "inactive", "paused", "error"]
        if v not in valid_statuses:
            raise ValueError(f"status must be one of: {', '.join(valid_statuses)}")
        return v

    class Config:
        schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "acme-corp",
                "user_id": "user-123",
                "agent_id": "customer-support-agent",
                "agent_version": "2.5.0",
                "agent_config": {
                    "name": "Asistente de Soporte",
                    "parameters": {"temperature": 0.7}
                },
                "created_at": "2025-06-03T20:15:00Z",
                "status": "active",
                "message_count": 5,
                "last_message_at": "2025-06-03T20:20:00Z",
                "context": {"previous_topics": ["facturación", "soporte"]},
                "metadata": {"source": "web", "browser": "chrome"},
                "session_ttl": 1800
            }
        }
```

## 4. Ejemplos de Uso

### Crear una nueva sesión

```python
from models.session import Session, SessionCreate

async def create_session(session_data: SessionCreate):
    # Obtener configuración de agente desde Agent Management Service
    agent_config = await agent_management_client.get_agent_configuration(
        tenant_id=session_data.tenant_id,
        agent_id=session_data.agent_id
    )
    
    # Crear objeto de sesión
    session = Session(
        tenant_id=session_data.tenant_id,
        user_id=session_data.user_id,
        agent_id=session_data.agent_id,
        agent_version=agent_config["version"],
        agent_config=agent_config,
        context=session_data.initial_context or {},
        metadata=session_data.metadata or {}
    )
    
    # Guardar en base de datos/caché
    await session_repository.save(session)
    
    return session
```

### Crear un plan de orquestación

```python
from models.orchestration import OrchestrationPlan, ServiceCall

async def create_rag_plan(session_id: str, tenant_id: str, query: str):
    plan = OrchestrationPlan(
        tenant_id=tenant_id,
        session_id=session_id,
        calls=[
            ServiceCall(
                service="conversation_service",
                operation="get_context",
                parameters={"session_id": session_id}
            ),
            ServiceCall(
                service="agent_execution",
                operation="process_query",
                parameters={"query": query},
                dependency_indices=[0]  # Depende del resultado del get_context
            )
        ],
        execution_strategy="sequential"
    )
    
    await orchestration_repository.save_plan(plan)
    return plan
```

## 5. Validación y Serialización

### Deserialización desde JSON

```python
def parse_message(json_data: Dict[str, Any]):
    role = json_data.get("role", "")
    
    if role == "user":
        return UserMessage(**json_data)
    elif role == "assistant":
        return AssistantMessage(**json_data)
    elif role == "system":
        return SystemMessage(**json_data)
    else:
        raise ValueError(f"Unsupported message role: {role}")
```

### Serialización a JSON para Redis

```python
async def save_session_to_redis(session: Session, redis_client):
    session_key = f"orchestrator:session:{session.tenant_id}:{session.session_id}"
    session_data = session.json()
    
    await redis_client.set(
        session_key, 
        session_data,
        ex=session.session_ttl
    )
```
