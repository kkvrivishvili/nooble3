"""
Manejadores de errores y decoradores para FastAPI.
"""

import logging
import traceback
import sys
from typing import Dict, Any, Optional, Union, TypeVar, Callable, Awaitable, Type, List, Tuple
from functools import wraps

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .exceptions import ServiceError, ERROR_CODES
from ..context.vars import get_full_context

logger = logging.getLogger(__name__)

# Tipo para funciones asíncronas para el decorador
T = TypeVar('T')
Func = Callable[..., Awaitable[T]]

def setup_error_handling(app: FastAPI) -> None:
    """
    Configura manejadores de error globales para la aplicación FastAPI.
    
    Esta función debe llamarse durante la inicialización de la aplicación.
    
    Args:
        app: Aplicación FastAPI
    """
    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        # Obtener contexto para logging
        context_str = ", ".join([f"{k}='{v}'" for k, v in exc.context.items() if v])
        
        if context_str:
            logger.error(f"Service error [{context_str}]: {exc.message}")
        else:
            logger.error(f"Service error: {exc.message}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict()
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Obtener contexto para logging
        context = get_full_context()
        context_str = ", ".join([f"{k}='{v}'" for k, v in context.items() if v])
        
        if context_str:
            logger.warning(f"HTTP error {exc.status_code} [{context_str}]: {exc.detail}")
        else:
            logger.warning(f"HTTP error {exc.status_code}: {exc.detail}")
        
        # Convertir a formato consistente
        error_response = {
            "success": False,
            "error": "HTTP_ERROR",
            "error_number": 1000 + exc.status_code,  # Generar número de error basado en el código HTTP
            "message": str(exc.detail)
        }
        
        # Añadir contexto si existe
        if any(v for v in context.values()):
            error_response["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Obtener contexto para logging
        context = get_full_context()
        context_str = ", ".join([f"{k}='{v}'" for k, v in context.items() if v])
        
        if context_str:
            logger.warning(f"Validation error [{context_str}]: {str(exc)}")
        else:
            logger.warning(f"Validation error: {str(exc)}")
        
        # Construir respuesta con formato de error estándar
        error_response = {
            "success": False,
            "error": "VALIDATION_ERROR",
            "error_number": ERROR_CODES["VALIDATION_ERROR"]["code"],
            "message": "Datos de entrada inválidos",
            "details": {
                "errors": exc.errors()
            }
        }
        
        # Añadir contexto si existe
        if any(v for v in context.values()):
            error_response["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=422,
            content=error_response
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        # Generar ID único para este error
        error_id = f"error_{id(exc)}"
        
        # Obtener contexto para logging
        context = get_full_context()
        context_str = ", ".join([f"{k}='{v}'" for k, v in context.items() if v])
        
        if context_str:
            logger.error(f"Unhandled exception {error_id} [{context_str}]: {str(exc)}")
        else:
            logger.error(f"Unhandled exception {error_id}: {str(exc)}")
            
        logger.error(traceback.format_exc())
        
        # Construir respuesta estándar
        error_response = {
            "success": False,
            "error": "GENERAL_ERROR",
            "error_number": ERROR_CODES["GENERAL_ERROR"]["code"],
            "message": "Error interno del servidor",
            "error_id": error_id
        }
        
        # Añadir contexto si existe
        if any(v for v in context.values()):
            error_response["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=500,
            content=error_response
        )
    
    # Middleware para logging de peticiones y respuestas
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        try:
            # Log request with tenant_id if available in headers
            tenant_id = request.headers.get("X-Tenant-ID")
            log_prefix = f"[tenant_id={tenant_id}]" if tenant_id else ""
            logger.debug(f"{log_prefix} Request: {request.method} {request.url.path}")
            
            # Process request
            response = await call_next(request)
            
            # Log response
            logger.debug(f"{log_prefix} Response: {request.method} {request.url.path} - Status: {response.status_code}")
            return response
        except Exception as e:
            # Manejar excepciones no capturadas
            logger.error(f"Unhandled error in middleware: {str(e)}")
            logger.error(traceback.format_exc())
            raise

def handle_errors(
    on_error_response: Optional[Dict[str, Any]] = None,
    error_map: Optional[Dict[Type[Exception], Tuple[str, int]]] = None
):
    """
    Decorador avanzado para manejar errores en funciones asíncronas.
    
    Este decorador captura todas las excepciones y las convierte en ServiceError
    con información de contexto adecuada.
    
    Args:
        on_error_response: Respuesta personalizada opcional en caso de error
        error_map: Mapeo de tipos de excepción a tuplas (error_code, status_code)
        
    Returns:
        Decorador configurado
        
    Ejemplo:
        ```python
        @handle_errors(error_map={
            ValueError: ("VALIDATION_ERROR", 422),
            KeyError: ("NOT_FOUND", 404)
        })
        async def my_function():
            # Código que puede lanzar excepciones
        ```
    """
    error_map = error_map or {}
    
    def decorator(func: Func) -> Func:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ServiceError:
                # Propagar ServiceError directamente, ya contiene toda la información necesaria
                raise
            except ValidationError as e:
                # Manejar errores de validación de Pydantic
                raise ServiceError(
                    message="Error de validación de datos",
                    error_code="VALIDATION_ERROR",
                    details={"errors": e.errors()}
                )
            except Exception as e:
                # Buscar en el mapa de errores si esta excepción tiene un manejo específico
                for exc_type, (error_code, status_code) in error_map.items():
                    if isinstance(e, exc_type):
                        raise ServiceError(
                            message=str(e),
                            error_code=error_code,
                            status_code=status_code
                        )
                
                # Para excepciones no mapeadas, registrar y convertir en ServiceError
                context = get_full_context()
                context_str = ", ".join([f"{k}='{v}'" for k, v in context.items() if v])
                
                logger.error(f"Error in {func.__name__} [{context_str}]: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Si se proporciona una respuesta personalizada, usarla
                if on_error_response:
                    raise ServiceError(
                        message=str(e),
                        error_code="GENERAL_ERROR",
                        details=on_error_response
                    )
                
                # Por defecto, crear ServiceError general
                raise ServiceError(
                    message=f"Error interno del servidor: {str(e)}",
                    error_code="GENERAL_ERROR"
                )
        
        # Preservar metadatos para FastAPI
        if hasattr(func, "__annotations__"):
            wrapper.__annotations__ = func.__annotations__
        
        for attr in ["response_model", "responses", "status_code", "tags", "summary", "description"]:
            if hasattr(func, attr):
                setattr(wrapper, attr, getattr(func, attr))
        
        return wrapper
    
    # Permitir usar el decorador con o sin parámetros
    if callable(on_error_response):
        func = on_error_response
        on_error_response = None
        return decorator(func)
    
    return decorator

# Alias para compatibilidad con código existente
handle_service_error = handle_errors

# Versión simplificada por mantener compatibilidad
handle_service_error_simple = handle_errors