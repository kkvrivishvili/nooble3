"""
Modelos para las herramientas del Agent Service.

Este módulo define los modelos Pydantic para las herramientas 
que pueden ser utilizadas por los agentes, incluyendo esquemas 
de entrada y salida para cada tipo de herramienta.
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime


class ToolType(str, Enum):
    """Tipo de herramienta."""
    RAG_QUERY = "rag_query"
    EMBEDDING = "embedding"
    EXTERNAL_API = "external_api"
    WEB_SEARCH = "web_search"
    DATABASE = "database"
    FUNCTION = "function"
    CONSULT_AGENT = "consult_agent"
    CUSTOM = "custom"


class ToolExecutionMetadata(BaseModel):
    """Metadatos de ejecución de herramienta."""
    tool_name: str = Field(..., description="Nombre de la herramienta")
    tool_type: ToolType = Field(..., description="Tipo de herramienta")
    execution_time_ms: int = Field(..., description="Tiempo de ejecución en milisegundos")
    error: Optional[str] = Field(None, description="Error en caso de fallo")
    success: bool = Field(True, description="Si la ejecución fue exitosa")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de la ejecución")
    agent_id: Optional[str] = Field(None, description="ID del agente que ejecutó la herramienta")
    conversation_id: Optional[str] = Field(None, description="ID de la conversación")
    tenant_id: Optional[str] = Field(None, description="ID del tenant")
    input_preview: Optional[str] = Field(None, description="Vista previa de la entrada (truncada)")
    output_preview: Optional[str] = Field(None, description="Vista previa de la salida (truncada)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    

class RAGQueryInput(BaseModel):
    """Esquema de entrada para consulta RAG."""
    query: str = Field(..., description="Consulta a realizar")
    collection_id: Optional[str] = Field(None, description="ID de colección específica")
    top_k: int = Field(4, description="Número de resultados a recuperar")
    threshold: float = Field(0.7, description="Umbral de similitud mínima")
    filter_metadata: Optional[Dict[str, Any]] = Field(None, description="Filtros adicionales")
    rerank_results: bool = Field(False, description="Si se deben reordenar los resultados")
    include_metadata: bool = Field(True, description="Si se debe incluir metadatos en los resultados")
    
    @validator('top_k')
    def validate_top_k(cls, v):
        if v < 1 or v > 10:
            raise ValueError("top_k debe estar entre 1 y 10")
        return v
    
    @validator('threshold')
    def validate_threshold(cls, v):
        if v < 0 or v > 1:
            raise ValueError("threshold debe estar entre 0 y 1")
        return v


class RAGQuerySource(BaseModel):
    """Fuente de información para resultados RAG."""
    document_id: str = Field(..., description="ID del documento")
    chunk_id: Optional[str] = Field(None, description="ID del fragmento")
    title: Optional[str] = Field(None, description="Título del documento")
    url: Optional[str] = Field(None, description="URL del documento si aplica")
    relevance_score: float = Field(..., description="Puntuación de relevancia")
    content: str = Field(..., description="Contenido relevante")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")


class RAGQueryOutput(BaseModel):
    """Esquema de salida para consulta RAG."""
    query: str = Field(..., description="Consulta original")
    sources: List[RAGQuerySource] = Field(default_factory=list, description="Fuentes de información")
    collection_id: Optional[str] = Field(None, description="ID de la colección consultada")
    total_found: int = Field(..., description="Total de documentos encontrados")
    execution_time_ms: int = Field(..., description="Tiempo de ejecución en milisegundos")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos de la consulta")
    
    
class WebSearchInput(BaseModel):
    """Esquema de entrada para búsqueda web."""
    query: str = Field(..., description="Consulta a buscar")
    num_results: int = Field(3, description="Número de resultados a recuperar")
    search_type: str = Field("general", description="Tipo de búsqueda: general, news, images")
    

class WebSearchResult(BaseModel):
    """Resultado individual de búsqueda web."""
    title: str = Field(..., description="Título del resultado")
    url: str = Field(..., description="URL del resultado")
    snippet: str = Field(..., description="Fragmento de texto relevante")
    published_date: Optional[str] = Field(None, description="Fecha de publicación si está disponible")
    source: str = Field(..., description="Fuente del resultado")


class WebSearchOutput(BaseModel):
    """Esquema de salida para búsqueda web."""
    query: str = Field(..., description="Consulta original")
    results: List[WebSearchResult] = Field(..., description="Resultados de la búsqueda")
    total_found: int = Field(..., description="Total de resultados encontrados")
    search_type: str = Field(..., description="Tipo de búsqueda realizada")
    execution_time_ms: int = Field(..., description="Tiempo de ejecución en milisegundos")


class ExternalAPIInput(BaseModel):
    """Esquema de entrada para llamada a API externa."""
    api_name: str = Field(..., description="Nombre de la API a llamar")
    method: str = Field("GET", description="Método HTTP: GET, POST, PUT, DELETE")
    endpoint: str = Field(..., description="Endpoint específico a llamar")
    params: Optional[Dict[str, Any]] = Field(None, description="Parámetros para la llamada")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers adicionales")
    body: Optional[Dict[str, Any]] = Field(None, description="Cuerpo de la solicitud para POST/PUT")
    timeout: int = Field(30, description="Timeout en segundos")


class ExternalAPIOutput(BaseModel):
    """Esquema de salida para llamada a API externa."""
    success: bool = Field(..., description="Si la llamada fue exitosa")
    status_code: int = Field(..., description="Código de estado HTTP")
    data: Any = Field(None, description="Datos de respuesta")
    error: Optional[str] = Field(None, description="Error en caso de fallo")
    execution_time_ms: int = Field(..., description="Tiempo de ejecución en milisegundos")


class ConsultAgentInput(BaseModel):
    """Esquema de entrada para consulta a otro agente."""
    agent_id: str = Field(..., description="ID del agente a consultar")
    question: str = Field(..., description="Pregunta o instrucción para el agente")
    conversation_id: Optional[str] = Field(None, description="ID de conversación a continuar")
    pass_context: bool = Field(True, description="Si se debe pasar el contexto actual")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")


class ConsultAgentOutput(BaseModel):
    """Esquema de salida para consulta a otro agente."""
    agent_id: str = Field(..., description="ID del agente consultado")
    response: str = Field(..., description="Respuesta del agente")
    conversation_id: str = Field(..., description="ID de la conversación")
    execution_time_ms: int = Field(..., description="Tiempo de ejecución en milisegundos")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")


class ToolConfig(BaseModel):
    """Configuración para una herramienta."""
    tool_type: ToolType = Field(..., description="Tipo de herramienta")
    name: str = Field(..., description="Nombre de la herramienta")
    description: str = Field(..., description="Descripción de la herramienta")
    enabled: bool = Field(True, description="Si la herramienta está habilitada")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuración específica")
    required_permissions: Optional[List[str]] = Field(None, description="Permisos requeridos")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
