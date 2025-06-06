"""
Settings configuration for the Agent Service.
"""

import os
from functools import lru_cache
from typing import Dict, List, Optional

from common.config import get_base_settings, get_service_settings
from common.config.tiers import get_tier_limits
from common.errors import handle_errors
from pydantic import BaseModel

from .constants import (
    DEFAULT_QUERY_SERVICE_URL,
    DEFAULT_EMBEDDING_SERVICE_URL,
    DEFAULT_INGESTION_SERVICE_URL,
    DEFAULT_MAX_AGENTS_PER_TENANT,
    DEFAULT_MAX_TOOLS_PER_AGENT,
    DEFAULT_MAX_NODES_PER_FLOW,
    DEFAULT_CONVERSATION_HISTORY_SIZE,
)


class AgentServiceSettings(BaseModel):
    """Settings specific to the Agent Service."""
    # Service URLs
    query_service_url: str = DEFAULT_QUERY_SERVICE_URL
    embedding_service_url: str = DEFAULT_EMBEDDING_SERVICE_URL
    ingestion_service_url: str = DEFAULT_INGESTION_SERVICE_URL

    # Service limits
    max_agents_per_tenant: int = DEFAULT_MAX_AGENTS_PER_TENANT
    max_tools_per_agent: int = DEFAULT_MAX_TOOLS_PER_AGENT
    max_nodes_per_flow: int = DEFAULT_MAX_NODES_PER_FLOW
    conversation_history_size: int = DEFAULT_CONVERSATION_HISTORY_SIZE

    # LLM Configuration
    default_llm_model: str = "gpt-3.5-turbo"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3

    # Feature flags
    enable_flow_engine: bool = True
    enable_tool_validation: bool = True
    enable_conversation_memory: bool = True


@lru_cache()
@handle_errors(error_type="config")
def get_settings() -> AgentServiceSettings:
    """
    Get Agent Service settings with environment variable overrides.
    Uses the centralized configuration pattern from common.config.
    
    Returns:
        AgentServiceSettings: The configured settings for the agent service
    """
    # Get base settings from common module
    base_settings = get_base_settings()
    
    # Get service-specific settings (this will load from environment variables)
    service_settings = get_service_settings("agent")
    
    # Create specific settings for this service
    return AgentServiceSettings(
        # Service URLs - Allow env var override
        query_service_url=os.getenv("QUERY_SERVICE_URL", DEFAULT_QUERY_SERVICE_URL),
        embedding_service_url=os.getenv("EMBEDDING_SERVICE_URL", DEFAULT_EMBEDDING_SERVICE_URL),
        ingestion_service_url=os.getenv("INGESTION_SERVICE_URL", DEFAULT_INGESTION_SERVICE_URL),
        
        # Service limits - Use centralized tier system with fallbacks
        max_agents_per_tenant=service_settings.get("max_agents_per_tenant", DEFAULT_MAX_AGENTS_PER_TENANT),
        max_tools_per_agent=service_settings.get("max_tools_per_agent", DEFAULT_MAX_TOOLS_PER_AGENT),
        max_nodes_per_flow=service_settings.get("max_nodes_per_flow", DEFAULT_MAX_NODES_PER_FLOW),
        conversation_history_size=service_settings.get("conversation_history_size", DEFAULT_CONVERSATION_HISTORY_SIZE),
        
        # LLM Configuration
        default_llm_model=service_settings.get("default_llm_model", "gpt-3.5-turbo"),
        llm_timeout_seconds=service_settings.get("llm_timeout_seconds", 60),
        llm_max_retries=service_settings.get("llm_max_retries", 3),
        
        # Feature flags
        enable_flow_engine=service_settings.get("enable_flow_engine", True),
        enable_tool_validation=service_settings.get("enable_tool_validation", True),
        enable_conversation_memory=service_settings.get("enable_conversation_memory", True),
    )


@handle_errors(error_type="config")
async def get_tenant_agent_limits(tenant_id: str, tier: Optional[str] = None) -> Dict:
    """
    Get agent-related limits for a specific tenant based on their tier.
    
    Args:
        tenant_id: The tenant ID
        tier: Optional tier override, if None will be determined from tenant_id
        
    Returns:
        Dict containing the agent limits for this tenant
    """
    # Get tier limits from the centralized tier system
    tier_limits = await get_tier_limits(tier, tenant_id)
    
    # Extract agent-specific limits
    agent_limits = {
        "max_agents": tier_limits.get("max_agents", DEFAULT_MAX_AGENTS_PER_TENANT),
        "max_tools_per_agent": tier_limits.get("max_tools_per_agent", DEFAULT_MAX_TOOLS_PER_AGENT),
        "max_nodes_per_flow": tier_limits.get("max_nodes_per_flow", DEFAULT_MAX_NODES_PER_FLOW),
        "conversation_history_size": tier_limits.get("conversation_history_size", DEFAULT_CONVERSATION_HISTORY_SIZE),
        "allowed_llm_models": tier_limits.get("allowed_llm_models", ["gpt-3.5-turbo"]),
    }
    
    return agent_limits
