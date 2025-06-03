"""
Models related to agents and their configurations.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field, validator

from common.models.base import BaseResponse


class AgentType(str, Enum):
    """Type of agent."""
    CONVERSATIONAL = "conversational"
    FLOW = "flow"
    RAG = "rag"
    ASSISTANT = "assistant"


class AgentState(str, Enum):
    """State of an agent."""
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class AgentConfig(BaseModel):
    """Configuration for an agent."""
    system_prompt: str = Field(..., description="System prompt for the agent")
    temperature: float = Field(0.7, description="Temperature for LLM responses")
    model: str = Field("gpt-3.5-turbo", description="LLM model to use")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens in responses")
    context_window: int = Field(10, description="Number of messages to keep in context")
    functions_enabled: bool = Field(True, description="Whether functions/tools are enabled")
    collection_ids: Optional[List[str]] = Field(None, description="Collection IDs for RAG")
    memory_enabled: bool = Field(True, description="Whether conversation memory is enabled")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        extra = "allow"


class AgentCreate(BaseModel):
    """Model for creating a new agent."""
    name: str = Field(..., description="Name of the agent")
    description: Optional[str] = Field(None, description="Description of the agent")
    type: AgentType = Field(..., description="Type of agent")
    config: AgentConfig = Field(..., description="Agent configuration")
    tenant_id: str = Field(..., description="Tenant ID")
    collection_ids: Optional[List[str]] = Field(None, description="Collection IDs for RAG")
    is_public: bool = Field(False, description="Whether the agent is publicly accessible")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class Agent(BaseModel):
    """Model representing an agent."""
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Agent ID")
    name: str = Field(..., description="Name of the agent")
    description: Optional[str] = Field(None, description="Description of the agent")
    type: AgentType = Field(..., description="Type of agent")
    config: AgentConfig = Field(..., description="Agent configuration")
    tenant_id: str = Field(..., description="Tenant ID")
    collection_ids: Optional[List[str]] = Field(None, description="Collection IDs for RAG")
    is_public: bool = Field(False, description="Whether the agent is publicly accessible")
    state: AgentState = Field(AgentState.CREATED, description="State of the agent")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        orm_mode = True


class AgentUpdate(BaseModel):
    """Model for updating an agent."""
    name: Optional[str] = Field(None, description="Name of the agent")
    description: Optional[str] = Field(None, description="Description of the agent")
    type: Optional[AgentType] = Field(None, description="Type of agent")
    config: Optional[AgentConfig] = Field(None, description="Agent configuration")
    collection_ids: Optional[List[str]] = Field(None, description="Collection IDs for RAG")
    is_public: Optional[bool] = Field(None, description="Whether the agent is publicly accessible")
    state: Optional[AgentState] = Field(None, description="State of the agent")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    @validator("updated_at", pre=True, always=True)
    def set_updated_at(cls, v):
        return datetime.utcnow()


class AgentResponse(BaseResponse):
    """Standard response model for agent operations."""
    data: Optional[Union[Agent, List[Agent], Dict[str, Any]]] = Field(None, description="Response data")
