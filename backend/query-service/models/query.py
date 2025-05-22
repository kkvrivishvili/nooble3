"""
Modelos de datos para Query Service.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class InternalQueryRequest(BaseModel):
    """Request para consultas RAG internas."""
    tenant_id: str
    query: str
    query_embedding: List[float] = Field(..., description="Embedding pre-calculado del query")
    collection_id: str
    agent_id: Optional[str] = None
    conversation_id: Optional[str] = None
    similarity_top_k: int = 4
    response_mode: str = "compact"
    llm_model: Optional[str] = None
    include_sources: bool = True
    max_sources: int = 3
    context_filter: Optional[Dict[str, Any]] = None
    
    # Campos para manejo de fallback
    agent_description: Optional[str] = None
    fallback_behavior: str = "agent_knowledge"  # Opciones: "agent_knowledge", "reject_query", "generic_response"
    relevance_threshold: float = 0.75  # Umbral para considerar documentos realmente relevantes

class InternalSearchRequest(BaseModel):
    """Request para búsqueda sin generación."""
    tenant_id: str
    query_embedding: List[float]
    collection_id: str
    limit: int = 5
    similarity_threshold: float = 0.7
    metadata_filter: Optional[Dict[str, Any]] = None

class DocumentMatch(BaseModel):
    """Documento encontrado por similitud."""
    id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float

class QueryResponse(BaseModel):
    """Response estándar para consultas."""
    success: bool
    message: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None
