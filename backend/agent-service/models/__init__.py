"""
Models for the Agent Service.

Este módulo proporciona una interfaz centralizada para acceder a todos los modelos
utilizados por el Agent Service, incluyendo modelos para agentes, herramientas,
servicios, colecciones y gestión de contexto.
"""

# Modelos básicos de agentes
from .agent import (
    Agent,
    AgentCreate,
    AgentUpdate,
    AgentConfig,
    AgentState,
    AgentType,
    AgentResponse
)

# Modelos de respuesta y conversación
from .response import (
    BaseResponse,
    MessageRole,
    ConversationMessage,
    ChatRequest,
    ChatResponse,
    FlowExecution,
    FlowExecutionState,
    FlowNode,
    FlowNodeConnection
)

# Modelos para herramientas
from .tools import (
    ToolType,
    ToolExecutionMetadata,
    RAGQueryInput,
    RAGQueryOutput,
    RAGQuerySource,
    WebSearchInput,
    WebSearchOutput,
    WebSearchResult,
    ExternalAPIInput,
    ExternalAPIOutput,
    ConsultAgentInput,
    ConsultAgentOutput,
    ToolConfig
)

# Modelos para gestión de contexto
from .context import (
    ContextConfig,
    ContextPayload,
    ContextManager
)

# Modelos para Service Registry
from .services import (
    ServiceType,
    ServiceConfig,
    RequestMethod,
    ServiceRequest,
    ServiceResponse,
    ServiceRegistry
)

# Modelos para colecciones
from .collections import (
    CollectionType,
    EmbeddingModelType,
    CollectionMetadata,
    SourceMetadata,
    CollectionSource,
    StrategyType,
    SelectionCriteria,
    CollectionStrategyConfig,
    CollectionSelectionResult
)

__all__ = [
    # Agentes
    "Agent",
    "AgentCreate",
    "AgentUpdate",
    "AgentConfig",
    "AgentState",
    "AgentType",
    "AgentResponse",
    
    # Respuestas y conversación
    "BaseResponse",
    "MessageRole",
    "ConversationMessage",
    "ChatRequest",
    "ChatResponse",
    "FlowExecution",
    "FlowExecutionState",
    "FlowNode",
    "FlowNodeConnection",
    
    # Herramientas
    "ToolType",
    "ToolExecutionMetadata",
    "RAGQueryInput",
    "RAGQueryOutput",
    "RAGQuerySource",
    "WebSearchInput",
    "WebSearchOutput",
    "WebSearchResult",
    "ExternalAPIInput",
    "ExternalAPIOutput",
    "ConsultAgentInput",
    "ConsultAgentOutput",
    "ToolConfig",
    
    # Contexto
    "ContextConfig",
    "ContextPayload",
    "ContextManager",
    
    # Service Registry
    "ServiceType",
    "ServiceConfig",
    "RequestMethod",
    "ServiceRequest",
    "ServiceResponse",
    "ServiceRegistry",
    
    # Colecciones
    "CollectionType",
    "EmbeddingModelType",
    "CollectionMetadata",
    "SourceMetadata",
    "CollectionSource",
    "StrategyType",
    "SelectionCriteria",
    "CollectionStrategyConfig",
    "CollectionSelectionResult"
]
