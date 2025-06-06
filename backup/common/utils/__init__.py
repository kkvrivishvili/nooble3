"""
Utilidades compartidas para todos los servicios.
"""

from .http import call_service
from .logging import init_logging, get_logger
from .rate_limiting import apply_rate_limit, setup_rate_limiting
from .stream import stream_llm_response
from .text import sanitize_query, format_sources

__all__ = [
    # HTTP y comunicación entre servicios
    'call_service',
    
    # Logging
    'init_logging', 'get_logger',
    
    # Rate limiting
    'apply_rate_limit', 'setup_rate_limiting',
    
    # Streaming de respuestas
    'stream_llm_response',
    
    # Procesamiento de texto
    'sanitize_query', 'format_sources'
]