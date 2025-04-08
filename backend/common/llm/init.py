"""
Integración con modelos de lenguaje (LLMs) y embeddings.
"""

from .base import BaseEmbeddingModel, BaseLLM
from .openai import get_openai_client, get_openai_embedding_model
from .ollama import OllamaEmbeddings, OllamaLLM, get_embedding_model, get_llm_model, is_using_ollama
from .token_counters import count_tokens, count_message_tokens, estimate_max_tokens_for_model, estimate_remaining_tokens
from .streaming import stream_openai_response, stream_ollama_response

__all__ = [
    # Interfaces base
    'BaseEmbeddingModel', 'BaseLLM',
    
    # OpenAI
    'get_openai_client', 'get_openai_embedding_model',
    
    # Ollama
    'OllamaEmbeddings', 'OllamaLLM', 'get_embedding_model', 'get_llm_model', 'is_using_ollama',
    
    # Conteo de tokens
    'count_tokens', 'count_message_tokens', 'estimate_max_tokens_for_model', 'estimate_remaining_tokens',
    
    # Streaming
    'stream_openai_response', 'stream_ollama_response'
]