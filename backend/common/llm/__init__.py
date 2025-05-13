"""
Integración con modelos de lenguaje (LLMs) y embeddings.
Este módulo se centra exclusivamente en Groq y Ollama como proveedores de LLM.
"""

from .base import BaseEmbeddingModel, BaseLLM
from .ollama import OllamaEmbeddings, OllamaLLM, get_embedding_model, get_llm_model, is_using_ollama
from .token_counters import count_tokens, count_message_tokens, estimate_max_tokens_for_model, estimate_remaining_tokens
from .streaming import stream_ollama_response, stream_groq_response

# Importar integración con Groq si está disponible
try:
    from .groq import (
        GroqLLM, get_groq_client, get_async_groq_client, 
        get_groq_llm_model, stream_groq_response, is_groq_model,
        GROQ_MODELS
    )
    GROQ_AVAILABLE = True
except ImportError:
    # Si no está disponible, definir variables dummy
    GROQ_AVAILABLE = False
    GroqLLM = None
    get_groq_client = None
    get_async_groq_client = None
    get_groq_llm_model = None
    stream_groq_response = None
    is_groq_model = lambda model_name: False
    GROQ_MODELS = {}

__all__ = [
    # Interfaces base
    'BaseEmbeddingModel', 'BaseLLM',
    
    # Ollama
    'OllamaEmbeddings', 'OllamaLLM', 'get_embedding_model', 'get_llm_model', 'is_using_ollama',
    
    # Conteo de tokens
    'count_tokens', 'count_message_tokens', 'estimate_max_tokens_for_model', 'estimate_remaining_tokens',
    
    # Streaming
    'stream_ollama_response', 'stream_groq_response',
    
    # Groq
    'GroqLLM', 'get_groq_client', 'get_async_groq_client', 'get_groq_llm_model',
    'stream_groq_response', 'is_groq_model', 'GROQ_MODELS', 'GROQ_AVAILABLE'
]