"""Manejo de errores y excepciones personalizadas."""

from .exceptions import (
    ServiceError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    ExternalServiceError,
    DatabaseError,
    ConfigurationError,
    handle_service_error,
    handle_service_error_simple,
    setup_error_handling
)

__all__ = [
    "ServiceError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ExternalServiceError",
    "DatabaseError",
    "ConfigurationError",
    "handle_service_error",
    "handle_service_error_simple",
    "setup_error_handling"
]
