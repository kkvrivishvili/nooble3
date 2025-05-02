"""
Configuración principal del servicio de embeddings.

Este módulo extiende la configuración base del sistema con configuraciones
específicas del servicio de embeddings y centraliza la obtención de
la configuración en un solo lugar.
"""

from typing import Dict, Any, Optional, List
from pydantic import Field, validator

from common.config import get_service_settings as get_base_settings
from common.config import Settings as BaseSettings
from common.models import HealthResponse

from .constants import (
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    QUALITY_THRESHOLDS,
    CACHE_EFFICIENCY_THRESHOLDS,
    OLLAMA_API_ENDPOINTS,
    TIMEOUTS
)

class EmbeddingServiceSettings(BaseSettings):
    """
    Configuración específica para el servicio de embeddings.
    Extiende la configuración base con parámetros específicos del servicio.
    """
    # Parámetros específicos del servicio
    embedding_quality_thresholds: Dict[str, Any] = Field(
        default_factory=lambda: QUALITY_THRESHOLDS,
        description="Umbrales para verificar la calidad de los embeddings"
    )
    
    cache_efficiency_thresholds: Dict[str, Any] = Field(
        default_factory=lambda: CACHE_EFFICIENCY_THRESHOLDS,
        description="Umbrales para determinar la eficiencia de caché"
    )
    
    ollama_api_endpoints: Dict[str, str] = Field(
        default_factory=lambda: OLLAMA_API_ENDPOINTS,
        description="Endpoints de la API de Ollama"
    )
    
    timeouts: Dict[str, float] = Field(
        default_factory=lambda: TIMEOUTS,
        description="Timeouts para diferentes operaciones"
    )
    
    embedding_dimensions: Dict[str, int] = Field(
        default_factory=lambda: EMBEDDING_DIMENSIONS,
        description="Dimensiones de embedding por modelo"
    )
    
    default_embedding_dimension: int = Field(
        DEFAULT_EMBEDDING_DIMENSION,
        description="Dimensión predeterminada cuando no se conoce el modelo"
    )
    
    # Parámetros de rendimiento y batch processing
    max_batch_size: int = Field(
        10,
        description="Tamaño máximo de lote para procesar embeddings"
    )
    
    max_tokens_per_batch: int = Field(
        50000,
        description="Número máximo de tokens por lote"
    )
    
    max_token_length_per_text: int = Field(
        8000,
        description="Longitud máxima en tokens para un texto individual"
    )
    
    allow_batch_processing: bool = Field(
        True,
        description="Si se permite el procesamiento por lotes"
    )
    
    max_input_length: int = Field(
        32000,
        description="Longitud máxima de entrada en caracteres"
    )
    
    # Parámetro para RAG - consultas de similitud
    max_similarity_top_k: int = Field(
        4,
        description="Número máximo de documentos similares a recuperar en consultas RAG"
    )
    
    # TTL para caché de embeddings
    embedding_cache_ttl: int = Field(
        604800,  # 7 días por defecto
        description="Tiempo de vida de los embeddings en caché (segundos)"
    )
    
    # Habilitar/deshabilitar caché
    embedding_cache_enabled: bool = Field(
        True,
        description="Habilitar o deshabilitar la caché de embeddings"
    )
    
    # Modelos de embeddings predeterminados
    default_embedding_model: str = Field(
        "text-embedding-3-small",
        description="Modelo de embedding predeterminado para OpenAI"
    )

    default_ollama_embedding_model: str = Field(
        "nomic-embed-text:latest",
        description="Modelo de embedding predeterminado para Ollama (con version)"
    )

    ollama_base_url: str = Field(
        "http://ollama:11434",
        description="URL base para el servicio Ollama"
    )

    # Tamaño de lote para procesamiento por API
    embedding_batch_size: int = Field(
        128,
        description="Tamaño predeterminado de lote para procesamiento de embeddings"
    )
    
    # Validadores para asegurar integridad de la configuración
    @validator("embedding_dimensions")
    def validate_embedding_dimensions(cls, v):
        """Verifica que las dimensiones de embedding sean valores positivos"""
        for model, dim in v.items():
            if dim <= 0:
                raise ValueError(f"La dimensión para el modelo {model} debe ser positiva")
        return v

    class Config:
        """Configuración de la clase de configuración"""
        validate_assignment = True
        extra = "ignore"
        env_prefix = "EMBEDDING_"

def get_settings() -> EmbeddingServiceSettings:
    """
    Obtiene la configuración específica para el servicio de embeddings.
    
    Esta función extiende la configuración base con parámetros específicos
    del servicio de embeddings.
    
    Returns:
        EmbeddingServiceSettings: Configuración para el servicio de embeddings
    """
    # Obtener configuración base del sistema
    base_settings = get_base_settings("embedding-service")
    
    # Crear la configuración específica del servicio
    service_settings = EmbeddingServiceSettings(**base_settings.dict())
    
    return service_settings

def get_health_status() -> HealthResponse:
    """
    Obtiene el estado de salud del servicio de embeddings.
    
    Returns:
        HealthResponse: Estado de salud del servicio
    """
    settings = get_settings()
    
    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        status="healthy",
        timestamp=None  # Se generará automáticamente
    )
