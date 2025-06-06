"""
Configuration module for Agent Service.
"""

from .settings import get_settings
from .constants import *

__all__ = [
    "get_settings",
    "AGENT_TYPE_CONVERSATIONAL",
    "AGENT_TYPE_FLOW",
    "AGENT_TYPE_RAG",
    "AGENT_TYPE_ASSISTANT",
    "AGENT_STATE_CREATED",
    "AGENT_STATE_ACTIVE",
    "AGENT_STATE_PAUSED",
    "AGENT_STATE_DELETED",
    "TOOL_TYPE_QUERY",
    "TOOL_TYPE_EMBEDDING",
    "TOOL_TYPE_EXTERNAL_API",
    "TOOL_TYPE_CUSTOM",
    "FLOW_STATE_CREATED",
    "FLOW_STATE_ACTIVE",
    "FLOW_STATE_PAUSED",
    "FLOW_STATE_COMPLETED",
    "FLOW_STATE_FAILED"
]
