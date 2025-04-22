"""
Modelos de datos compartidos entre los servicios.
"""

from .base import BaseModel, BaseResponse, ErrorResponse, HealthResponse, TenantInfo
from .tenants import PublicTenantInfo
from .agents import (
    AgentTool, AgentConfig, AgentRequest, AgentResponse, AgentSummary, 
    AgentsListResponse, DeleteAgentResponse, AgentListResponse
)
from .collections import (
    CollectionInfo, CollectionsListResponse, CollectionToolResponse,
    CollectionCreationResponse, CollectionUpdateResponse, CollectionStatsResponse
)
from .responses import (
    ServiceStatusResponse, CacheStatsResponse, CacheClearResponse,
    ModelListResponse, EmbeddingRequest, EmbeddingResponse, QueryRequest, QueryResponse
)

# Re-exportar todos los modelos importantes
__all__ = [
    # Base
    'BaseModel', 'BaseResponse', 'ErrorResponse', 'HealthResponse', 'TenantInfo',
    
    # Tenants
    'PublicTenantInfo',
    
    # Agents
    'AgentTool', 'AgentConfig', 'AgentRequest', 'AgentResponse', 'AgentSummary',
    'AgentsListResponse', 'DeleteAgentResponse', 'AgentListResponse',
    
    # Collections
    'CollectionInfo', 'CollectionsListResponse', 'CollectionToolResponse',
    'CollectionCreationResponse', 'CollectionUpdateResponse', 'CollectionStatsResponse',
    
    # Responses
    'HealthResponse', 'ServiceStatusResponse', 'CacheStatsResponse', 'CacheClearResponse',
    'ModelListResponse', 'EmbeddingRequest', 'EmbeddingResponse', 'QueryRequest', 'QueryResponse'
]