"""
Sistema de manejo de errores para todos los servicios.
"""

from .exceptions import (
    ServiceError, AuthenticationError, PermissionError, ResourceNotFoundError,
    ValidationError, RateLimitError, QuotaExceededError, ServiceUnavailableError,
    ExternalApiError, DatabaseError, LlmGenerationError, ModelNotAvailableError,
    EmbeddingError, DocumentProcessingError, CollectionError, ConversationError
)

from .handlers import (
    setup_error_handling, handle_service_error, handle_service_error_simple,
    handle_errors
)

from .responses import (
    create_error_response, format_error_response, sanitize_content
)

__all__ = [
    # Excepciones
    'ServiceError', 'AuthenticationError', 'PermissionError', 'ResourceNotFoundError',
    'ValidationError', 'RateLimitError', 'QuotaExceededError', 'ServiceUnavailableError',
    'ExternalApiError', 'DatabaseError', 'LlmGenerationError', 'ModelNotAvailableError',
    'EmbeddingError', 'DocumentProcessingError', 'CollectionError', 'ConversationError',
    
    # Manejadores
    'setup_error_handling', 'handle_service_error', 'handle_service_error_simple',
    'handle_errors',
    
    # Utilidades
    'create_error_response', 'format_error_response', 'sanitize_content'
]