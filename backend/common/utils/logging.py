"""
Configuración de logging centralizada para todos los servicios.
"""

import logging
import sys
import os
from typing import Optional
from logging.handlers import RotatingFileHandler
import platform
from pathlib import Path

from ..config.settings import get_settings

def init_logging(log_level: Optional[str] = None, service_name: Optional[str] = None) -> None:
    """
    Inicializa la configuración de logging para la aplicación.
    
    Args:
        log_level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                  Si no se especifica, se usa el nivel configurado en config.py
        service_name: Nombre del servicio para el archivo de log
                  Si no se especifica, se usa 'app'
    """
    settings = get_settings()
    
    # Determinar nivel de log (priorizar el parámetro si se proporciona)
    level_str = log_level or settings.log_level
    level = getattr(logging, level_str.upper(), logging.INFO)
    
    # Usar el nombre del servicio proporcionado o un valor por defecto
    service = service_name or 'app'
    
    # Configurar formato según el entorno
    # Usar debug_mode o verificar si el entorno es development
    is_development = settings.debug_mode or settings.environment.lower() == "development"
    
    if is_development:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        # Formato más estructurado para producción
        format_str = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    
    # Configurar handler para salida a consola
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Determinar la ruta de logs apropiada para Docker/Kubernetes vs. local
    if os.environ.get('KUBERNETES_SERVICE_HOST') or os.environ.get('DOCKER_CONTAINER'):
        # En Docker o Kubernetes, usar /app/logs
        log_dir = "/app/logs"
    else:
        # Localmente, usar una carpeta 'logs' en el directorio actual o en la raíz del proyecto
        # Intentar encontrar la raíz del proyecto (donde está el backend)
        current_dir = Path.cwd()
        if 'backend' in str(current_dir):
            # Si estamos en algún subdirectorio de backend, subir hasta encontrar la carpeta backend
            while current_dir.name != 'backend' and current_dir.parent != current_dir:
                current_dir = current_dir.parent
                
            # Usar la carpeta backend/logs
            log_dir = str(current_dir / 'logs')
        else:
            # Si no encontramos backend, usar el directorio actual
            log_dir = str(current_dir / 'logs')
    
    # Crear el directorio de logs si no existe
    os.makedirs(log_dir, exist_ok=True)
    
    # Configurar archivo de log con rotación
    log_file = os.path.join(log_dir, f"{service}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,          # Mantener 5 archivos de respaldo
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(format_str))
    file_handler.setLevel(level)
    handlers.append(file_handler)
    
    # Configuración básica
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers,
        force=True  # Forzar reconfigiración incluso si ya ha sido llamada
    )
    
    # Establecer niveles específicos para algunos loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    
    # Log de inicio
    logging.info(f"Logging iniciado para el servicio '{service}' con nivel: {logging.getLevelName(level)}")
    logging.info(f"Los logs se guardan en: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado con el nombre especificado.
    
    Args:
        name: Nombre del logger
        
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)