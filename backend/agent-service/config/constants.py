"""
Constants for the Agent Service.
"""

# Agent Types
AGENT_TYPE_CONVERSATIONAL = "conversational"
AGENT_TYPE_FLOW = "flow"
AGENT_TYPE_RAG = "rag"
AGENT_TYPE_ASSISTANT = "assistant"

# Agent States
AGENT_STATE_CREATED = "created"
AGENT_STATE_ACTIVE = "active"
AGENT_STATE_PAUSED = "paused"
AGENT_STATE_DELETED = "deleted"

# Tool Types
TOOL_TYPE_QUERY = "query"
TOOL_TYPE_EMBEDDING = "embedding"
TOOL_TYPE_EXTERNAL_API = "external_api"
TOOL_TYPE_CUSTOM = "custom"

# Flow States
FLOW_STATE_CREATED = "created"
FLOW_STATE_ACTIVE = "active"
FLOW_STATE_PAUSED = "paused"
FLOW_STATE_COMPLETED = "completed"
FLOW_STATE_FAILED = "failed"

# Service Names
SERVICE_NAME_QUERY = "query"
SERVICE_NAME_EMBEDDING = "embedding"
SERVICE_NAME_INGESTION = "ingestion"
SERVICE_NAME_AGENT = "agent"

# Service URLs (these will be loaded from environment variables in settings.py)
DEFAULT_QUERY_SERVICE_URL = "http://localhost:8001"
DEFAULT_EMBEDDING_SERVICE_URL = "http://localhost:8002"
DEFAULT_INGESTION_SERVICE_URL = "http://localhost:8003"

# Cache TTL values (in seconds)
# Using standard TTLs as defined in the shared cache implementation
TTL_SHORT = 300  # 5 minutes - For volatile data like query results
TTL_STANDARD = 3600  # 1 hour - For agent configurations, etc.
TTL_EXTENDED = 86400  # 24 hours - For more stable data

# Default values
DEFAULT_MAX_AGENTS_PER_TENANT = 10
DEFAULT_MAX_TOOLS_PER_AGENT = 5
DEFAULT_MAX_NODES_PER_FLOW = 20
DEFAULT_CONVERSATION_HISTORY_SIZE = 10

# Table names
TABLE_AGENTS = "agents"
TABLE_TOOLS = "tools"
TABLE_FLOWS = "flows"
TABLE_FLOW_EXECUTIONS = "flow_executions"
TABLE_CONVERSATIONS = "conversations"
TABLE_CONVERSATION_MESSAGES = "conversation_messages"

# Token tracking constants
OPERATION_AGENT_CHAT = "agent_chat"
OPERATION_AGENT_FLOW = "agent_flow"
OPERATION_AGENT_RAG = "agent_rag"
