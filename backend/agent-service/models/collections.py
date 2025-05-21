"""
Modelos para la gestión de colecciones en el Agent Service.

Este módulo define los modelos Pydantic para metadatos de colecciones,
estrategias de selección y fuentes de información para el sistema RAG.
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union, Set
from pydantic import BaseModel, Field, validator, root_validator
from datetime import datetime


class CollectionType(str, Enum):
    """Tipo de colección."""
    DOCUMENT = "document"
    KNOWLEDGE_BASE = "knowledge_base"
    CONVERSATION = "conversation"
    CUSTOM = "custom"


class EmbeddingModelType(str, Enum):
    """Tipo de modelo de embedding."""
    OPENAI = "openai"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    CUSTOM = "custom"


class CollectionMetadata(BaseModel):
    """Metadatos de colección."""
    collection_id: str = Field(..., description="ID de la colección")
    tenant_id: str = Field(..., description="ID del tenant")
    name: str = Field(..., description="Nombre de la colección")
    description: Optional[str] = Field(None, description="Descripción de la colección")
    collection_type: CollectionType = Field(CollectionType.DOCUMENT, description="Tipo de colección")
    document_count: int = Field(0, description="Número de documentos")
    chunk_count: int = Field(0, description="Número de fragmentos")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de última actualización")
    embedding_model: str = Field(..., description="Modelo de embedding usado")
    embedding_model_type: EmbeddingModelType = Field(EmbeddingModelType.OPENAI, description="Tipo de modelo de embedding")
    embedding_dimensions: int = Field(..., description="Dimensiones del embedding")
    is_public: bool = Field(False, description="Si la colección es pública")
    tags: Optional[List[str]] = Field(None, description="Etiquetas asociadas")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    
    class Config:
        orm_mode = True


class SourceMetadata(BaseModel):
    """Metadatos de fuente de documento."""
    source_type: str = Field(..., description="Tipo de fuente (web, pdf, doc, etc.)")
    source_url: Optional[str] = Field(None, description="URL de la fuente si aplica")
    author: Optional[str] = Field(None, description="Autor de la fuente")
    published_date: Optional[str] = Field(None, description="Fecha de publicación")
    last_modified: Optional[str] = Field(None, description="Fecha de última modificación")
    file_name: Optional[str] = Field(None, description="Nombre del archivo original")
    file_type: Optional[str] = Field(None, description="Tipo de archivo original")
    file_size: Optional[int] = Field(None, description="Tamaño del archivo en bytes")
    page_number: Optional[int] = Field(None, description="Número de página para PDFs")
    total_pages: Optional[int] = Field(None, description="Total de páginas para PDFs")
    section: Optional[str] = Field(None, description="Sección específica del documento")
    custom_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos personalizados")


class CollectionSource(BaseModel):
    """Fuente de información en colección."""
    document_id: str = Field(..., description="ID del documento")
    collection_id: str = Field(..., description="ID de la colección")
    tenant_id: str = Field(..., description="ID del tenant")
    chunk_id: Optional[str] = Field(None, description="ID del fragmento específico")
    title: str = Field(..., description="Título del documento")
    url: Optional[str] = Field(None, description="URL del documento si aplica")
    relevance_score: float = Field(..., description="Puntuación de relevancia")
    content_preview: str = Field(..., description="Vista previa del contenido")
    source_metadata: Optional[SourceMetadata] = Field(None, description="Metadatos de la fuente")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    
    @validator('relevance_score')
    def validate_relevance_score(cls, v):
        """Validar que la puntuación de relevancia esté en el rango adecuado."""
        if v < 0 or v > 1:
            raise ValueError("relevance_score debe estar entre 0 y 1")
        return v


class StrategyType(str, Enum):
    """Tipo de estrategia para selección de colecciones."""
    SINGLE = "single"
    MULTI = "multi"
    FEDERATED = "federated"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SelectionCriteria(str, Enum):
    """Criterio de selección de colecciones."""
    DEFAULT = "default"
    SIMILARITY = "similarity"
    RECENCY = "recency"
    CUSTOM = "custom"


class CollectionStrategyConfig(BaseModel):
    """Configuración para estrategia de selección."""
    strategy_type: StrategyType = Field(StrategyType.SINGLE, description="Tipo de estrategia")
    primary_collection_id: Optional[str] = Field(None, description="ID de colección primaria")
    collection_ids: Optional[List[str]] = Field(None, description="IDs de colecciones a usar")
    federate_results: bool = Field(False, description="Si se deben federar resultados")
    per_collection_limit: int = Field(3, description="Límite de resultados por colección")
    selection_criteria: SelectionCriteria = Field(SelectionCriteria.DEFAULT, description="Criterio de selección")
    similarity_threshold: float = Field(0.7, description="Umbral de similitud mínima")
    max_collections: int = Field(3, description="Máximo de colecciones a consultar")
    custom_strategy_config: Optional[Dict[str, Any]] = Field(None, description="Config. personalizada")
    
    @root_validator
    def validate_strategy_config(cls, values):
        """Validar que la configuración sea coherente con el tipo de estrategia."""
        strategy_type = values.get('strategy_type')
        primary_collection_id = values.get('primary_collection_id')
        collection_ids = values.get('collection_ids', [])
        federate_results = values.get('federate_results', False)
        
        # Para estrategia single, se requiere primary_collection_id
        if strategy_type == StrategyType.SINGLE and not primary_collection_id:
            raise ValueError("Se requiere primary_collection_id para estrategia SINGLE")
        
        # Para estrategias multi y federated, se requieren collection_ids
        if strategy_type in [StrategyType.MULTI, StrategyType.FEDERATED] and not collection_ids:
            raise ValueError(f"Se requieren collection_ids para estrategia {strategy_type}")
        
        # Federated implica federate_results=True
        if strategy_type == StrategyType.FEDERATED and not federate_results:
            values['federate_results'] = True
        
        # Semantic y hybrid requieren custom_strategy_config
        if strategy_type in [StrategyType.SEMANTIC, StrategyType.HYBRID]:
            if not values.get('custom_strategy_config'):
                raise ValueError(f"Se requiere custom_strategy_config para estrategia {strategy_type}")
        
        return values


class CollectionSelectionResult(BaseModel):
    """Resultado de la selección de colecciones."""
    strategy_type: StrategyType = Field(..., description="Tipo de estrategia utilizada")
    selected_collections: List[str] = Field(..., description="IDs de colecciones seleccionadas")
    federated: bool = Field(False, description="Si los resultados están federados")
    selection_criteria: SelectionCriteria = Field(..., description="Criterio de selección usado")
    selection_time_ms: int = Field(..., description="Tiempo de selección en milisegundos")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
