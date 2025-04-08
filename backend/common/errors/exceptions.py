"""
Definiciones de excepciones para la plataforma.
"""

import logging
from typing import Dict, Any, Optional

from ..context.vars import get_full_context

logger = logging.getLogger(__name__)

# Estructura centralizada de códigos de error para toda la plataforma
ERROR_CODES = {
    # Errores generales (1xxx)
    "GENERAL_ERROR": {"code": 1000, "message": "Error interno del servidor", "status": 500},
    "NOT_FOUND": {"code": 1001, "message": "Recurso no encontrado", "status": 404},
    "VALIDATION_ERROR": {"code": 1002, "message": "Error en datos de entrada", "status": 422},
    
    # Errores de autenticación y autorización (2xxx)
    "PERMISSION_DENIED": {"code": 2000, "message": "Sin permisos para la operación", "status": 403},
    "AUTHENTICATION_FAILED": {"code": 2001, "message": "Autenticación fallida", "status": 401},
    "TENANT_ACCESS_DENIED": {"code": 2002, "message": "Acceso denegado al tenant", "status": 403},
    "TENANT_ISOLATION_BREACH": {"code": 2003, "message": "Violación de aislamiento de tenant", "status": 403},
    
    # Errores de límites y cuotas (3xxx)
    "QUOTA_EXCEEDED": {"code": 3000, "message": "Límite de cuota alcanzado", "status": 429},
    "RATE_LIMITED": {"code": 3001, "message": "Límite de tasa alcanzado", "status": 429},
    "TOKEN_LIMIT_EXCEEDED": {"code": 3002, "message": "Límite de tokens alcanzado", "status": 429},
    
    # Errores de servicios externos (4xxx)
    "SERVICE_UNAVAILABLE": {"code": 4000, "message": "Servicio no disponible", "status": 503},
    "EXTERNAL_API_ERROR": {"code": 4001, "message": "Error en API externa", "status": 502},
    "DATABASE_ERROR": {"code": 4002, "message": "Error de base de datos", "status": 500},
    
    # Errores específicos de LLM (5xxx)
    "LLM_GENERATION_ERROR": {"code": 5000, "message": "Error en generación de texto", "status": 500},
    "MODEL_NOT_AVAILABLE": {"code": 5001, "message": "Modelo no disponible", "status": 404},
    "EMBEDDING_ERROR": {"code": 5002, "message": "Error generando embeddings", "status": 500},
    
    # Errores de gestión de datos (6xxx)
    "DOCUMENT_PROCESSING_ERROR": {"code": 6000, "message": "Error procesando documento", "status": 500},
    "COLLECTION_ERROR": {"code": 6001, "message": "Error con la colección", "status": 500},
    "CONVERSATION_ERROR": {"code": 6002, "message": "Error con la conversación", "status": 500},
}

class ServiceError(Exception):
    """
    Excepción centralizada para todos los errores de servicio.
    
    Esta clase proporciona un formato consistente para todos los errores
    y facilita su conversión a respuestas HTTP apropiadas.
    
    Attributes:
        message: Mensaje descriptivo del error
        error_code: Código estandarizado de error (ej: "NOT_FOUND")
        status_code: Código HTTP (ej: 404)
        details: Información adicional sobre el error
        context: Información de contexto (tenant_id, etc.)
    """
    def __init__(
        self, 
        message: str, 
        error_code: str = "GENERAL_ERROR",
        status_code: Optional[int] = None, 
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.context = context or get_full_context()
        
        # Buscar la definición del error para obtener código y estado
        error_info = ERROR_CODES.get(error_code, ERROR_CODES["GENERAL_ERROR"])
        
        # Usar el estado del código de error a menos que se proporcione uno específico
        self.status_code = status_code or error_info["status"]
        self.error_number = error_info["code"]
        
        # Inicialización de Exception
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte la excepción a un diccionario para la respuesta JSON.
        
        Returns:
            Dict: Representación del error como diccionario
        """
        error_dict = {
            "success": False,
            "error": self.error_code,
            "error_number": self.error_number,
            "message": self.message,
        }
        
        # Añadir detalles si existen
        if self.details:
            error_dict["details"] = self.details
            
        # Añadir contexto si existe y tiene valores no nulos
        if self.context:
            context_dict = {k: v for k, v in self.context.items() if v is not None}
            if context_dict:
                error_dict["context"] = context_dict
                
        return error_dict

# Clases de error específicas
class AuthenticationError(ServiceError):
    """Error de autenticación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            details=details
        )

class PermissionError(ServiceError):
    """Error de permisos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="PERMISSION_DENIED",
            details=details
        )

class ResourceNotFoundError(ServiceError):
    """Error de recurso no encontrado."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            details=details
        )

class ValidationError(ServiceError):
    """Error de validación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details
        )

class RateLimitError(ServiceError):
    """Error de límite de tasa."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMITED",
            details=details
        )

class QuotaExceededError(ServiceError):
    """Error de cuota excedida."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="QUOTA_EXCEEDED",
            details=details
        )

class ServiceUnavailableError(ServiceError):
    """Error de servicio no disponible."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            details=details
        )

class ExternalApiError(ServiceError):
    """Error en API externa."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EXTERNAL_API_ERROR",
            details=details
        )

class DatabaseError(ServiceError):
    """Error de base de datos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=details
        )

class LlmGenerationError(ServiceError):
    """Error en generación de texto con LLM."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="LLM_GENERATION_ERROR",
            details=details
        )

class ModelNotAvailableError(ServiceError):
    """Error de modelo no disponible."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="MODEL_NOT_AVAILABLE",
            details=details
        )

class EmbeddingError(ServiceError):
    """Error generando embeddings."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EMBEDDING_ERROR",
            details=details
        )

class DocumentProcessingError(ServiceError):
    """Error procesando documento."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DOCUMENT_PROCESSING_ERROR",
            details=details
        )

class CollectionError(ServiceError):
    """Error con la colección."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="COLLECTION_ERROR",
            details=details
        )

class ConversationError(ServiceError):
    """Error con la conversación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONVERSATION_ERROR",
            details=details
        )