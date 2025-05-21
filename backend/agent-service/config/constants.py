"""
Constants for the Agent Service.
"""

from common.core.constants import (
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT,
    DEFAULT_TTL_MAPPING
)

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

# Default values
DEFAULT_MAX_AGENTS_PER_TENANT = 10
DEFAULT_MAX_TOOLS_PER_AGENT = 5
DEFAULT_MAX_NODES_PER_FLOW = 20
DEFAULT_CONVERSATION_HISTORY_SIZE = 10

# Token Types
TOKEN_TYPE_LLM = "llm"
TOKEN_TYPE_EMBEDDING = "embedding"
TOKEN_TYPE_TOKENIZATION = "tokenization"

# Operation Types
OPERATION_AGENT_CHAT = "agent_chat"
OPERATION_AGENT_RAG = "agent_rag"
OPERATION_AGENT_FLOW = "agent_flow"
OPERATION_AGENT_TOOL = "agent_tool"
OPERATION_AGENT_MULTI = "agent_multi"

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

# Cache Data Types (para estandarización de claves de caché)
CACHE_TYPE_AGENT = "agent"
CACHE_TYPE_AGENT_CONFIG = "agent_config"
CACHE_TYPE_AGENT_TOOLS = "agent_tools"
CACHE_TYPE_CONVERSATION = "conversation"
CACHE_TYPE_CONVERSATION_MEMORY = "conversation_memory"
CACHE_TYPE_CONVERSATION_MESSAGE = "conversation_message"
CACHE_TYPE_CONVERSATION_MESSAGES_LIST = "conversation_messages_list"
CACHE_TYPE_AGENT_EXECUTION_STATE = "agent_execution_state"
CACHE_TYPE_COLLECTION_METADATA = "collection_metadata"

# Mapeo de TTLs para tipos de datos específicos del Agent Service
# Esto extiende el DEFAULT_TTL_MAPPING definido en common/core/constants.py
AGENT_SERVICE_TTL_MAPPING = {
    CACHE_TYPE_AGENT: TTL_STANDARD,                    # 1 hora
    CACHE_TYPE_AGENT_CONFIG: TTL_STANDARD,             # 1 hora
    CACHE_TYPE_AGENT_TOOLS: TTL_STANDARD,              # 1 hora
    CACHE_TYPE_CONVERSATION: TTL_EXTENDED,             # 24 horas
    CACHE_TYPE_CONVERSATION_MEMORY: TTL_EXTENDED,      # 24 horas
    CACHE_TYPE_CONVERSATION_MESSAGE: TTL_EXTENDED,     # 24 horas
    CACHE_TYPE_CONVERSATION_MESSAGES_LIST: TTL_EXTENDED, # 24 horas
    CACHE_TYPE_AGENT_EXECUTION_STATE: TTL_SHORT,       # 5 minutos
    CACHE_TYPE_COLLECTION_METADATA: TTL_STANDARD,      # 1 hora
}

def get_ttl_for_data_type(data_type: str) -> int:
    """
    Obtiene el TTL adecuado para un tipo de datos específico del Agent Service.
    Primero verifica el mapeo específico del servicio, luego el mapeo global.
    
    Args:
        data_type: Tipo de datos
        
    Returns:
        TTL en segundos
    """
    # Verificar primero en el mapeo específico del servicio
    if data_type in AGENT_SERVICE_TTL_MAPPING:
        return AGENT_SERVICE_TTL_MAPPING[data_type]
    
    # Verificar en el mapeo global
    if data_type in DEFAULT_TTL_MAPPING:
        return DEFAULT_TTL_MAPPING[data_type]
    
    # Valor por defecto
    return TTL_STANDARD
