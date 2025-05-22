"""
Configuración del servicio de embeddings.
Solo configuraciones esenciales para OpenAI.
"""

from typing import Dict
from pydantic import Field
from common.config import Settings as BaseSettings
from common.config import get_service_settings as get_base_settings
from common.models import HealthResponse

# Constantes de OpenAI - Modelos disponibles y sus propiedades
OPENAI_MODELS = {
    "text-embedding-3-small": {
        "dimensions": 1536,
        "max_tokens": 8191
    },
    "text-embedding-3-large": {
        "dimensions": 3072,
        "max_tokens": 8191
    },
    "text-embedding-ada-002": {
        "dimensions": 1536,
        "max_tokens": 8191
    }
}

class EmbeddingServiceSettings(BaseSettings):
    """Configuración mínima para el servicio de embeddings."""
    
    # OpenAI
    openai_api_key: str = Field(..., description="API Key para OpenAI")
    default_embedding_model: str = Field(
        "text-embedding-3-small",
        description="Modelo de embedding predeterminado"
    )
    
    # Límites operacionales
    max_batch_size: int = Field(
        100,
        description="Número máximo de textos por batch"
    )
    max_text_length: int = Field(
        8000,
        description="Longitud máxima de texto en caracteres"
    )
    
    # Timeouts
    openai_timeout_seconds: int = Field(
        30,
        description="Timeout para llamadas a OpenAI"
    )
    
    # Dimensión predeterminada
    default_embedding_dimension: int = Field(
        1536,
        description="Dimensión predeterminada cuando no se conoce el modelo"
    )
    
    # TTL para caché de embeddings (simplificado)
    embedding_cache_ttl: int = Field(
        604800,  # 7 días por defecto
        description="Tiempo de vida de los embeddings en caché (segundos)"
    )
    
    class Config:
        """Configuración de la clase de configuración"""
        validate_assignment = True
        extra = "ignore"
        env_prefix = "EMBEDDING_"

def get_settings() -> EmbeddingServiceSettings:
    """
    Obtiene la configuración específica para el servicio de embeddings.
    
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
