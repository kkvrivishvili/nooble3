"""
Configuración simplificada del Query Service.
"""

from typing import Dict, Optional
from pydantic import Field
from common.config import Settings as BaseSettings
from common.config import get_service_settings as get_base_settings

# Modelos Groq disponibles en producción
GROQ_MODELS = {
    "llama-4-scout-17bx16e": {
        "description": "Llama 4 Scout - Balanceado para uso general",
        "context_window": 32768,
        "max_tokens": 8192,
        "speed": 460
    },
    "llama-4-maverick-17bx128e": {
        "description": "Llama 4 Maverick - Alto rendimiento",
        "context_window": 32768,
        "max_tokens": 8192,
        "speed": 240
    },
    "llama-3.1-8b-instant-128k": {
        "description": "Llama 3.1 8B - Respuesta rápida, contexto extendido",
        "context_window": 131072,
        "max_tokens": 8192,
        "speed": 750
    }
}

class QueryServiceSettings(BaseSettings):
    """Configuración específica para Query Service."""

    # Groq
    groq_api_key: str = Field(..., description="API Key para Groq")
    default_groq_model: str = Field(
        "llama-3.1-8b-instant-128k",
        description="Modelo Groq predeterminado"
    )

    # RAG Configuration
    default_similarity_top_k: int = Field(4, description="Documentos a recuperar")
    max_similarity_top_k: int = Field(10, description="Máximo de documentos")
    similarity_threshold: float = Field(0.7, description="Umbral de similitud")

    # LLM Configuration
    llm_temperature: float = Field(0.7, description="Temperatura LLM")
    llm_max_tokens: int = Field(4096, description="Tokens máximos de respuesta")

    # Timeouts
    groq_timeout_seconds: int = Field(30, description="Timeout para Groq API")
    vector_search_timeout: int = Field(10, description="Timeout búsqueda vectorial")

def get_settings() -> QueryServiceSettings:
    """Obtiene configuración del servicio."""
    base_settings = get_base_settings("query-service")
    return QueryServiceSettings(**base_settings.dict())


