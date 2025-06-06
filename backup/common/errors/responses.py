"""
Funciones de utilidad para crear respuestas de error estandarizadas.
"""

import re
import logging
from typing import Dict, Any, Optional

from .exceptions import ServiceError, ERROR_CODES

logger = logging.getLogger(__name__)

def sanitize_content(content: str) -> str:
    """
    Sanitiza contenido para eliminar datos sensibles y caracteres problemáticos.
    
    Args:
        content: Contenido a sanitizar
        
    Returns:
        str: Contenido sanitizado
    """
    if not content:
        return ""
    
    # Remover posibles tokens de API o credenciales
    content = re.sub(r'(api[_-]?key|token|password|secret)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{10,})["\']?', 
                    r'\1: [REDACTED]', 
                    content, 
                    flags=re.IGNORECASE)
    
    # Eliminar caracteres de control excepto saltos de línea y tabs
    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
    
    # Truncar si es demasiado largo (más de 100,000 caracteres)
    if len(content) > 100000:
        content = content[:100000] + "... [contenido truncado]"
    
    return content

def create_error_response(
    message: str, 
    error_code: str = "GENERAL_ERROR",
    status_code: Optional[int] = None, 
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Crea una respuesta de error estandarizada.
    
    Esta función es útil para retornar errores desde endpoints
    sin tener que lanzar excepciones.
    
    Args:
        message: Mensaje de error
        error_code: Código de error estandarizado
        status_code: Código HTTP opcional (se usa el predeterminado del error_code si no se proporciona)
        details: Detalles adicionales del error
        
    Returns:
        Dict: Respuesta de error estandarizada
    """
    # Crear ServiceError pero sin lanzarlo
    error = ServiceError(
        message=message,
        error_code=error_code,
        status_code=status_code,
        details=details
    )
    
    # Convertir a diccionario para la respuesta
    return error.to_dict()

def format_error_response(message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Formatea una respuesta de error estándar.
    
    Args:
        message: Mensaje de error
        status_code: Código de estado HTTP
        details: Detalles adicionales del error
        
    Returns:
        Dict: Respuesta de error formateada
    """
    response = {
        "success": False,
        "error": message,
        "status_code": status_code,
        "message": message
    }
    
    if details:
        response["details"] = details
    
    return response