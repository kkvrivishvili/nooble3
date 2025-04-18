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

from .exceptions import ServiceError, ConfigurationError, ErrorCode, ERROR_CODES

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
        from ..context.vars import get_full_context
        # Obtener contexto para logging
        context = get_full_context()
        context_str = ", ".join([f"{k}='{v}'" for k, v in context.items() if v])
        
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
        from ..context.vars import get_full_context
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
            "error": {
                "code": "HTTP_ERROR",
                "error_number": 1000 + exc.status_code,
                "message": str(exc.detail)
            }
        }
        # Añadir contexto anidado si existe
        if any(v for v in context.values()):
            error_response["error"]["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        from ..context.vars import get_full_context
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
            "error": {
                "code": "VALIDATION_ERROR",
                "error_number": ERROR_CODES["VALIDATION_ERROR"]["code"],
                "message": "Datos de entrada inválidos",
                "details": {
                    "errors": exc.errors()
                }
            }
        }
        # Añadir contexto anidado si existe
        if any(v for v in context.values()):
            error_response["error"]["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=422,
            content=error_response
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        from ..context.vars import get_full_context
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
            "error": {
                "code": "GENERAL_ERROR",
                "error_number": ERROR_CODES["GENERAL_ERROR"]["code"],
                "message": "Error interno del servidor",
                "error_id": error_id
            }
        }
        # Añadir contexto anidado si existe
        if any(v for v in context.values()):
            error_response["error"]["context"] = {k: v for k, v in context.items() if v}
        
        return JSONResponse(
            status_code=500,
            content=error_response
        )
    
    # Middleware para logging de peticiones y respuestas
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        from ..context.vars import get_full_context
        try:
            # Log request with tenant_id if available in headers
            context = get_full_context()
            tenant_id = context.get("tenant_id")
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
    error_map: Optional[Dict[Type[Exception], Tuple[str, int]]] = None,
    error_type: str = "service",  # Nuevo parámetro: 'service', 'config' o 'simple'
    convert_exceptions: bool = True,  # Determina si convertir excepciones a ServiceError
    log_traceback: bool = True,  # Determina si se loggea el traceback
    ignore_exceptions: Optional[List[Type[Exception]]] = None  # Excepciones a ignorar
) -> Callable[[Func], Func]:
    """
    Decorador unificado y parametrizable para manejar errores en funciones asíncronas.
    
    Este decorador captura todas las excepciones y las convierte en ServiceError
    o ConfigurationError dependiendo del valor de error_type con información de contexto adecuada.
    
    Args:
        on_error_response: Respuesta personalizada opcional en caso de error
        error_map: Mapeo de tipos de excepción a tuplas (error_code, status_code)
        error_type: Tipo de error a manejar ('service', 'config', o 'simple')
        convert_exceptions: Si es True, convierte excepciones a ServiceError
        log_traceback: Si es True, loggea el traceback completo
        ignore_exceptions: Lista de excepciones que no se deben capturar
        
    Returns:
        Decorador configurado
        
    Ejemplo:
        ```python
        # Uso normal para errores de servicio
        @handle_errors(error_map={
            ValueError: ("VALIDATION_ERROR", 422),
            KeyError: ("NOT_FOUND", 404)
        })
        async def my_function():
            # Código que puede lanzar excepciones
            
        # Para errores de configuración
        @handle_errors(error_type="config")
        async def load_config():
            # Código que carga configuración
            
        # Versión simple
        @handle_errors(error_type="simple")
        async def simple_function():
            # Código con manejo de errores básico
        ```
    """
    # Normalizar los parámetros
    ignore_exceptions = ignore_exceptions or []
    
    def decorator(func: Func) -> Func:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except tuple(ignore_exceptions):
                # Permitir que ciertas excepciones pasen sin modificar
                raise
            except (ServiceError, ConfigurationError):
                # Ya es un error manejado, dejar pasar
                raise
            except Exception as e:
                # Obtener contexto actual para enriquecer el error
                from ..context.vars import get_full_context
                context = get_full_context()
                function_name = func.__name__
                
                # Añadir información de la función y su ubicación
                context.update({
                    "function": function_name,
                    "module": func.__module__
                })
                
                # Añadir argumentos no sensibles para depuración
                try:
                    safe_args = [f"{i}:{type(arg).__name__}" for i, arg in enumerate(args)]
                    safe_kwargs = {k: type(v).__name__ for k, v in kwargs.items()}
                    context.update({
                        "args": str(safe_args),
                        "kwargs": str(safe_kwargs)
                    })
                except Exception:
                    pass
                
                # Para logging
                log_extras = {"extra": context} if context else {}
                
                # Manejamos los diferentes tipos de errores según el parámetro error_type
                if error_type == "config":
                    # Manejo específico para errores de configuración
                    if isinstance(e, KeyError):
                        # Error típico al intentar acceder a una configuración inexistente
                        context.update({"missing_key": str(e)})
                        logger.error(f"Configuración faltante: {str(e)}", **log_extras)
                        raise ConfigurationError(
                            message=f"Configuración faltante: {str(e)}",
                            error_code=ErrorCode.MISSING_CONFIGURATION.value,
                            context=context
                        )
                    elif isinstance(e, (ValueError, TypeError)):
                        # Error típico de configuración inválida
                        logger.error(f"Configuración inválida: {str(e)}", **log_extras)
                        raise ConfigurationError(
                            message=f"Configuración inválida: {str(e)}",
                            error_code=ErrorCode.INVALID_CONFIGURATION.value,
                            status_code=400,
                            context=context
                        )
                    else:
                        # Otras excepciones se convierten en error genérico de configuración
                        if log_traceback:
                            logger.error(f"Error de configuración: {str(e)}", exc_info=True, **log_extras)
                        else:
                            logger.error(f"Error de configuración: {str(e)}", **log_extras)
                        
                        raise ConfigurationError(
                            message=f"Error de configuración: {str(e)}",
                            context=context
                        )
                else:
                    # Manejo estándar para errores de servicio
                    # Verificar si el tipo de excepción está en el mapa de errores
                    exception_type = type(e)
                    error_code = ErrorCode.INTERNAL_ERROR
                    status_code = 500
                    
                    if error_map and exception_type in error_map:
                        error_code_str, status_code = error_map[exception_type]
                        error_code = ErrorCode(error_code_str) if isinstance(error_code_str, str) else error_code_str
                    
                    # Log del error
                    error_message = f"Error en {function_name}: {str(e)}"
                    if log_traceback:
                        logger.error(error_message, exc_info=True, **log_extras)
                    else:
                        logger.error(error_message, **log_extras)
                    
                    if convert_exceptions:
                        # Convertir a ServiceError con contexto
                        raise ServiceError(
                            message=str(e),
                            error_code=error_code,
                            status_code=status_code,
                            context=context
                        )
                    else:
                        # Dejar pasar la excepción original
                        raise
                    
        return wrapper
    
    # Handle case where decorator is used without parentheses
    if callable(on_error_response) and not error_map:
        func = on_error_response
        on_error_response = None
        return decorator(func)
    
    return decorator

# Aliases para decoración estandarizada de endpoints
handle_service_error_simple = handle_errors(error_type="simple")  # Para endpoints públicos
handle_service_error_internal = handle_errors(error_type="service")  # Para endpoints internos
# Mantener alias antiguo para compatibilidad
handle_service_error = handle_service_error_simple