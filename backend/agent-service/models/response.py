"""
Models for handling agent responses, conversations, and flows.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field, root_validator

from common.models.base import BaseResponse


class MessageRole(str, Enum):
    """Role in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class FlowExecutionState(str, Enum):
    """State of a flow execution."""
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ConversationMessage(BaseModel):
    """Model for a conversation message."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Message ID")
    conversation_id: str = Field(..., description="Conversation ID")
    agent_id: str = Field(..., description="Agent ID")
    tenant_id: str = Field(..., description="Tenant ID")
    role: MessageRole = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional message metadata")
    
    class Config:
        orm_mode = True


class ChatRequest(BaseModel):
    """Model for a chat request."""
    message: str = Field(..., description="User message content")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for continuing a conversation")
    agent_id: str = Field(..., description="Agent ID")
    user_id: Optional[str] = Field(None, description="User ID, if applicable")
    collection_ids: Optional[List[str]] = Field(None, description="Optional collection IDs for RAG")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional request metadata")


class ChatResponse(BaseResponse):
    """Model for a chat response."""
    message: str = Field(..., description="Assistant response content")
    conversation_id: str = Field(..., description="Conversation ID")
    agent_id: str = Field(..., description="Agent ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Response metadata")
    sources: Optional[List[Dict[str, Any]]] = Field(None, description="Source references from RAG")
    tools_used: Optional[List[Dict[str, Any]]] = Field(None, description="Tools used in generating the response")
    thinking: Optional[str] = Field(None, description="Reasoning process (if enabled)")


class FlowNodeConnection(BaseModel):
    """Connection between flow nodes."""
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    condition: Optional[str] = Field(None, description="Optional condition for the connection")


class FlowNode(BaseModel):
    """Node in a flow."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Node ID")
    flow_id: str = Field(..., description="Flow ID")
    type: str = Field(..., description="Node type (agent, tool, condition, etc.)")
    name: str = Field(..., description="Node name")
    config: Dict[str, Any] = Field(..., description="Node configuration")
    position: Dict[str, float] = Field(..., description="Node position in UI")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional node metadata")


class FlowExecution(BaseModel):
    """Model for a flow execution."""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Execution ID")
    flow_id: str = Field(..., description="Flow ID")
    tenant_id: str = Field(..., description="Tenant ID")
    state: FlowExecutionState = Field(FlowExecutionState.CREATED, description="Execution state")
    current_node_id: Optional[str] = Field(None, description="Currently executing node ID")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Start timestamp")
    end_time: Optional[datetime] = Field(None, description="End timestamp")
    input_data: Optional[Dict[str, Any]] = Field(None, description="Input data for the flow")
    output_data: Optional[Dict[str, Any]] = Field(None, description="Output data from the flow")
    execution_history: List[Dict[str, Any]] = Field(default_factory=list, description="History of node executions")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional execution metadata")
    
    @root_validator
    def check_end_time(cls, values):
        """Set end_time if state is COMPLETED or FAILED."""
        state = values.get("state")
        end_time = values.get("end_time")
        
        if state in [FlowExecutionState.COMPLETED, FlowExecutionState.FAILED] and not end_time:
            values["end_time"] = datetime.utcnow()
        
        return values
