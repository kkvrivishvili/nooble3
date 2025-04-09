"""
Definiciones de excepciones para la plataforma.
"""

import logging
from typing import Dict, Any, Optional
from enum import Enum
from fastapi import HTTPException, status

from ..context.vars import get_full_context

logger = logging.getLogger(__name__)

class ErrorCode(Enum):
    """
    Enumeración centralizada de códigos de error para toda la plataforma.
    
    Los códigos están organizados por categorías:
    - 1xxx: Errores generales
    - 2xxx: Errores de autenticación y autorización
    - 3xxx: Errores de límites y cuotas
    - 4xxx: Errores de servicios externos
    - 5xxx: Errores específicos de LLM
    - 6xxx: Errores de gestión de datos
    - 7xxx: Errores específicos de agentes
    - 8xxx: Errores específicos de consultas (RAG)
    - 9xxx: Errores específicos de embeddings
    """
    # Errores generales (1xxx)
    GENERAL_ERROR = "GENERAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    
    # Errores de autenticación y autorización (2xxx)
    PERMISSION_DENIED = "PERMISSION_DENIED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    TENANT_ISOLATION_BREACH = "TENANT_ISOLATION_BREACH"
    
    # Errores de límites y cuotas (3xxx)
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    TOKEN_LIMIT_EXCEEDED = "TOKEN_LIMIT_EXCEEDED"
    
    # Errores de servicios externos (4xxx)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    CACHE_ERROR = "CACHE_ERROR"  # Añadido para unificar excepciones
    
    # Errores específicos de LLM (5xxx)
    LLM_GENERATION_ERROR = "LLM_GENERATION_ERROR"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    EMBEDDING_ERROR = "EMBEDDING_ERROR"
    
    # Errores de gestión de datos (6xxx)
    DOCUMENT_PROCESSING_ERROR = "DOCUMENT_PROCESSING_ERROR"
    COLLECTION_ERROR = "COLLECTION_ERROR"
    CONVERSATION_ERROR = "CONVERSATION_ERROR"
    
    # Errores específicos de agentes (7xxx)
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_INACTIVE = "AGENT_INACTIVE"
    AGENT_EXECUTION_ERROR = "AGENT_EXECUTION_ERROR"
    AGENT_SETUP_ERROR = "AGENT_SETUP_ERROR"
    AGENT_TOOL_ERROR = "AGENT_TOOL_ERROR"
    AGENT_LIMIT_EXCEEDED = "AGENT_LIMIT_EXCEEDED"
    INVALID_AGENT_ID = "INVALID_AGENT_ID"
    AGENT_ALREADY_EXISTS = "AGENT_ALREADY_EXISTS"
    AGENT_QUOTA_EXCEEDED = "AGENT_QUOTA_EXCEEDED"
    
    # Errores específicos de consultas RAG (8xxx)
    QUERY_PROCESSING_ERROR = "QUERY_PROCESSING_ERROR"
    COLLECTION_NOT_FOUND = "COLLECTION_NOT_FOUND"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    GENERATION_ERROR = "GENERATION_ERROR"
    INVALID_QUERY_PARAMS = "INVALID_QUERY_PARAMS"
    
    # Errores específicos de embeddings (9xxx)
    EMBEDDING_GENERATION_ERROR = "EMBEDDING_GENERATION_ERROR"
    EMBEDDING_MODEL_ERROR = "EMBEDDING_MODEL_ERROR"
    TEXT_TOO_LARGE = "TEXT_TOO_LARGE"
    BATCH_TOO_LARGE = "BATCH_TOO_LARGE"
    INVALID_EMBEDDING_PARAMS = "INVALID_EMBEDDING_PARAMS"
    
    # Errores de configuración
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"

# Estructura centralizada de códigos de error para toda la plataforma
ERROR_CODES = {
    # Errores generales (1xxx)
    ErrorCode.GENERAL_ERROR.value: {"code": 1000, "message": "Error interno del servidor", "status": 500},
    ErrorCode.NOT_FOUND.value: {"code": 1001, "message": "Recurso no encontrado", "status": 404},
    ErrorCode.VALIDATION_ERROR.value: {"code": 1002, "message": "Error en datos de entrada", "status": 422},
    
    # Errores de autenticación y autorización (2xxx)
    ErrorCode.PERMISSION_DENIED.value: {"code": 2000, "message": "Sin permisos para la operación", "status": 403},
    ErrorCode.AUTHENTICATION_FAILED.value: {"code": 2001, "message": "Autenticación fallida", "status": 401},
    ErrorCode.TENANT_ACCESS_DENIED.value: {"code": 2002, "message": "Acceso denegado al tenant", "status": 403},
    ErrorCode.TENANT_ISOLATION_BREACH.value: {"code": 2003, "message": "Violación de aislamiento de tenant", "status": 403},
    
    # Errores de límites y cuotas (3xxx)
    ErrorCode.QUOTA_EXCEEDED.value: {"code": 3000, "message": "Cuota excedida", "status": 429},
    ErrorCode.RATE_LIMITED.value: {"code": 3001, "message": "Demasiadas solicitudes", "status": 429},
    ErrorCode.RATE_LIMIT_EXCEEDED.value: {"code": 3002, "message": "Límite de tasa excedido", "status": 429},
    ErrorCode.RATE_LIMIT_ERROR.value: {"code": 3003, "message": "Error de rate limit", "status": 500},
    ErrorCode.TOKEN_LIMIT_EXCEEDED.value: {"code": 3004, "message": "Límite de tokens excedido", "status": 413},
    
    # Errores de servicios externos (4xxx)
    ErrorCode.SERVICE_UNAVAILABLE.value: {"code": 4000, "message": "Servicio no disponible", "status": 503},
    ErrorCode.EXTERNAL_API_ERROR.value: {"code": 4001, "message": "Error en API externa", "status": 502},
    ErrorCode.DATABASE_ERROR.value: {"code": 4002, "message": "Error de base de datos", "status": 503},
    ErrorCode.CACHE_ERROR.value: {"code": 4003, "message": "Error de caché", "status": 503},
    
    # Errores específicos de LLM (5xxx)
    ErrorCode.LLM_GENERATION_ERROR.value: {"code": 5000, "message": "Error generando texto con LLM", "status": 500},
    ErrorCode.MODEL_NOT_AVAILABLE.value: {"code": 5001, "message": "Modelo no disponible", "status": 503},
    ErrorCode.EMBEDDING_ERROR.value: {"code": 5002, "message": "Error generando embeddings", "status": 500},
    
    # Errores de gestión de datos (6xxx)
    ErrorCode.DOCUMENT_PROCESSING_ERROR.value: {"code": 6000, "message": "Error procesando documento", "status": 500},
    ErrorCode.COLLECTION_ERROR.value: {"code": 6001, "message": "Error con la colección", "status": 500},
    ErrorCode.CONVERSATION_ERROR.value: {"code": 6002, "message": "Error con la conversación", "status": 500},
    
    # Errores específicos de agentes (7xxx)
    ErrorCode.AGENT_NOT_FOUND.value: {"code": 7000, "message": "Agente no encontrado", "status": 404},
    ErrorCode.AGENT_INACTIVE.value: {"code": 7001, "message": "Agente inactivo", "status": 400},
    ErrorCode.AGENT_EXECUTION_ERROR.value: {"code": 7002, "message": "Error en ejecución de agente", "status": 500},
    ErrorCode.AGENT_SETUP_ERROR.value: {"code": 7003, "message": "Error en configuración de agente", "status": 500},
    ErrorCode.AGENT_TOOL_ERROR.value: {"code": 7004, "message": "Error en herramienta de agente", "status": 500},
    ErrorCode.AGENT_LIMIT_EXCEEDED.value: {"code": 7005, "message": "Límite de agentes alcanzado", "status": 429},
    ErrorCode.INVALID_AGENT_ID.value: {"code": 7006, "message": "ID de agente inválido", "status": 400},
    ErrorCode.AGENT_ALREADY_EXISTS.value: {"code": 7007, "message": "Agente ya existente", "status": 409},
    ErrorCode.AGENT_QUOTA_EXCEEDED.value: {"code": 7008, "message": "Cuota de agentes alcanzada", "status": 429},
    
    # Errores específicos de consultas RAG (8xxx)
    ErrorCode.QUERY_PROCESSING_ERROR.value: {"code": 8000, "message": "Error procesando consulta", "status": 500},
    ErrorCode.COLLECTION_NOT_FOUND.value: {"code": 8001, "message": "Colección no encontrada", "status": 404},
    ErrorCode.RETRIEVAL_ERROR.value: {"code": 8002, "message": "Error en recuperación de datos", "status": 500},
    ErrorCode.GENERATION_ERROR.value: {"code": 8003, "message": "Error en generación de respuesta", "status": 500},
    ErrorCode.INVALID_QUERY_PARAMS.value: {"code": 8004, "message": "Parámetros de consulta inválidos", "status": 400},
    
    # Errores específicos de embeddings (9xxx)
    ErrorCode.EMBEDDING_GENERATION_ERROR.value: {"code": 9000, "message": "Error generando embeddings", "status": 500},
    ErrorCode.EMBEDDING_MODEL_ERROR.value: {"code": 9001, "message": "Error en modelo de embeddings", "status": 500},
    ErrorCode.TEXT_TOO_LARGE.value: {"code": 9002, "message": "Texto demasiado grande", "status": 413},
    ErrorCode.BATCH_TOO_LARGE.value: {"code": 9003, "message": "Lote demasiado grande", "status": 413},
    ErrorCode.INVALID_EMBEDDING_PARAMS.value: {"code": 9004, "message": "Parámetros de embeddings inválidos", "status": 400},
    
    # Errores de configuración
    ErrorCode.CONFIGURATION_ERROR.value: {"code": 1010, "message": "Error de configuración", "status": 500},
    ErrorCode.MISSING_CONFIGURATION.value: {"code": 1011, "message": "Configuración faltante", "status": 500},
    ErrorCode.INVALID_CONFIGURATION.value: {"code": 1012, "message": "Configuración inválida", "status": 400},
}

class ServiceError(Exception):
    """
    Excepción centralizada para todos los errores de servicio.
    
    Esta clase proporciona un formato consistente para todos los errores
    y facilita su conversión a respuestas HTTP apropiadas.
    
    Attributes:
        message: Mensaje descriptivo del error
        error_code: Código estandarizado de error (ej: ErrorCode.NOT_FOUND)
        status_code: Código HTTP (ej: 404)
        details: Información adicional sobre el error
        context: Información de contexto (tenant_id, etc.)
    """
    def __init__(
            self, 
            message: str, 
            error_code: ErrorCode = ErrorCode.GENERAL_ERROR,
            status_code: Optional[int] = None, 
            details: Optional[Dict[str, Any]] = None,
            context: Optional[Dict[str, Any]] = None
        ):
        self.message = message
        # Si error_code es un Enum, extraer el valor
        self.error_code = error_code.value if isinstance(error_code, ErrorCode) else error_code
        self.details = details or {}
        self.context = context or get_full_context()
        
        # Buscar la definición del error para obtener código y estado
        error_info = ERROR_CODES.get(self.error_code, ERROR_CODES[ErrorCode.GENERAL_ERROR.value])
        
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
        error_response = {
            "message": self.message,
            "code": self.error_code,
            "error_number": self.error_number,
            "details": self.details
        }
        
        # Incluir cierta información de contexto que sea útil para debugging
        # pero excluir información sensible
        if self.context and isinstance(self.context, dict):
            safe_context = {
                k: v for k, v in self.context.items()
                if k in ["tenant_id", "agent_id", "collection_id", "conversation_id", "request_id"]
            }
            if safe_context:
                error_response["context"] = safe_context
        
        return error_response
    
    def to_http_exception(self) -> HTTPException:
        """
        Convierte esta excepción en una HTTPException de FastAPI.
        
        Returns:
            HTTPException: Excepción HTTP para FastAPI
        """
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_dict()
        )

# Clases de error específicas
class AuthenticationError(ServiceError):
    """Error de autenticación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHENTICATION_FAILED,
            details=details
        )

class PermissionError(ServiceError):
    """Error de permisos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.PERMISSION_DENIED,
            details=details
        )

class ResourceNotFoundError(ServiceError):
    """Error de recurso no encontrado."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.NOT_FOUND,
            details=details
        )

class ValidationError(ServiceError):
    """Error de validación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            details=details
        )

class RateLimitError(ServiceError):
    """Error de límite de tasa."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMITED,
            details=details
        )

class RateLimitExceeded(ServiceError):
    """Error cuando se excede el límite de tasa."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            details=details,
            context=context
        )

class QuotaExceededError(ServiceError):
    """Error de cuota excedida."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.QUOTA_EXCEEDED,
            details=details
        )

class ServiceUnavailableError(ServiceError):
    """Error de servicio no disponible."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            details=details
        )

class ExternalApiError(ServiceError):
    """Error en API externa."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_API_ERROR,
            details=details
        )

class DatabaseError(ServiceError):
    """Error de base de datos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_ERROR,
            details=details
        )

class CacheError(ServiceError):
    """Error de caché."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CACHE_ERROR,
            details=details
        )

class LlmGenerationError(ServiceError):
    """Error en generación de texto con LLM."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.LLM_GENERATION_ERROR,
            details=details
        )

class ModelNotAvailableError(ServiceError):
    """Error de modelo no disponible."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.MODEL_NOT_AVAILABLE,
            details=details
        )

class EmbeddingError(ServiceError):
    """Error generando embeddings."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EMBEDDING_ERROR,
            details=details
        )

class DocumentProcessingError(ServiceError):
    """Error procesando documento."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.DOCUMENT_PROCESSING_ERROR,
            details=details
        )

class CollectionError(ServiceError):
    """Error con la colección."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.COLLECTION_ERROR,
            details=details
        )

class ConversationError(ServiceError):
    """Error con la conversación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CONVERSATION_ERROR,
            details=details
        )

class AgentNotFoundError(ServiceError):
    """Error de agente no encontrado."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_NOT_FOUND,
            details=details
        )

class AgentInactiveError(ServiceError):
    """Error de agente inactivo."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_INACTIVE,
            details=details
        )

class AgentExecutionError(ServiceError):
    """Error en ejecución de agente."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_EXECUTION_ERROR,
            details=details
        )

class AgentSetupError(ServiceError):
    """Error en configuración de agente."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_SETUP_ERROR,
            details=details
        )

class AgentToolError(ServiceError):
    """Error en herramienta de agente."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_TOOL_ERROR,
            details=details
        )

class AgentLimitExceededError(ServiceError):
    """Error de límite de agentes alcanzado."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_LIMIT_EXCEEDED,
            details=details
        )

class InvalidAgentIdError(ServiceError):
    """Error de ID de agente inválido."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_AGENT_ID,
            details=details
        )

class AgentAlreadyExistsError(ServiceError):
    """Error de agente ya existente."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_ALREADY_EXISTS,
            details=details
        )

class AgentQuotaExceededError(ServiceError):
    """Error de cuota de agentes alcanzada."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.AGENT_QUOTA_EXCEEDED,
            details=details
        )

class QueryProcessingError(ServiceError):
    """Error procesando consulta."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.QUERY_PROCESSING_ERROR,
            details=details
        )

class CollectionNotFoundError(ServiceError):
    """Error de colección no encontrada."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.COLLECTION_NOT_FOUND,
            details=details
        )

class RetrievalError(ServiceError):
    """Error en recuperación de datos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.RETRIEVAL_ERROR,
            details=details
        )

class GenerationError(ServiceError):
    """Error en generación de respuesta."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.GENERATION_ERROR,
            details=details
        )

class InvalidQueryParamsError(ServiceError):
    """Error de parámetros de consulta inválidos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_QUERY_PARAMS,
            details=details
        )

class EmbeddingGenerationError(ServiceError):
    """Error generando embeddings."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EMBEDDING_GENERATION_ERROR,
            details=details
        )

class EmbeddingModelError(ServiceError):
    """Error en modelo de embeddings."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EMBEDDING_MODEL_ERROR,
            details=details
        )

class TextTooLargeError(ServiceError):
    """Error de texto demasiado grande."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.TEXT_TOO_LARGE,
            details=details
        )

class BatchTooLargeError(ServiceError):
    """Error de lote demasiado grande."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.BATCH_TOO_LARGE,
            details=details
        )

class InvalidEmbeddingParamsError(ServiceError):
    """Error de parámetros de embeddings inválidos."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_EMBEDDING_PARAMS,
            details=details
        )

class ConfigurationError(ServiceError):
    """
    Error de configuración.
    
    Este error se utiliza cuando hay problemas relacionados con la configuración del sistema,
    como valores faltantes, inválidos o conflictivos en la configuración.
    """
    def __init__(self, message: str, error_code: str = ErrorCode.CONFIGURATION_ERROR.value, 
                     status_code: int = 500, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            context=context
        )
