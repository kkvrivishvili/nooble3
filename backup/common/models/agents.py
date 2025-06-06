"""
Modelos de datos para agentes, configuraciones y herramientas.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import Field

from .base import BaseModel, BaseResponse

class AgentTool(BaseModel):
    """
    Herramienta disponible para un agente.
    
    Una herramienta define una capacidad que puede utilizar un agente,
    como buscar en una colección de documentos o realizar cálculos.
    """
    name: str
    description: str
    type: str  # rag_search, web_search, calculator, etc.
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    is_active: bool = True
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "name": "consultar_documentos",
                    "description": "Buscar información en documentos técnicos",
                    "type": "rag",
                    "metadata": {
                        "collection_id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "documentacion_tecnica",
                        "similarity_top_k": 3
                    },
                    "is_active": True
                }
            ]
        }


class AgentConfig(BaseModel):
    """Configuración de un agente."""
    agent_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    agent_type: str = "conversational"  # conversational, react, structured_chat, etc.
    llm_model: str = "gpt-3.5-turbo"
    tools: List[AgentTool] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    memory_enabled: bool = True
    memory_window: int = 10
    is_active: bool = True
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    """Solicitud para crear o actualizar un agente."""
    tenant_id: str
    name: str
    description: Optional[str] = None
    agent_type: str = "conversational"
    llm_model: Optional[str] = None
    tools: List[AgentTool] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    memory_enabled: bool = True
    memory_window: int = 10
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AgentResponse(BaseResponse):
    """Respuesta con detalles de un agente."""
    agent_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    agent_type: str
    llm_model: str
    tools: List[AgentTool]
    system_prompt: Optional[str]
    memory_enabled: bool
    memory_window: int
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentSummary(BaseModel):
    """Resumen de información básica de un agente."""
    agent_id: str
    name: str
    description: Optional[str] = None
    model: str
    is_public: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentsListResponse(BaseResponse):
    """Respuesta para listado de agentes."""
    agents: List[AgentSummary] = Field(default_factory=list)
    count: int = 0

    
class DeleteAgentResponse(BaseResponse):
    """Respuesta para eliminación de agente."""
    agent_id: str
    deleted: bool = True
    conversations_deleted: int = 0


# Alias para compatibilidad con código existente
class AgentListResponse(AgentsListResponse):
    """Alias de AgentsListResponse para compatibilidad con código existente."""
    pass