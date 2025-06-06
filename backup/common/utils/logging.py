"""
Configuración de logging centralizada para todos los servicios.
"""

import logging
import sys
import os
import time
import threading
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
import platform
from pathlib import Path

from ..config.settings import get_settings

class TimedRotatingFileHandler(RotatingFileHandler):
    """
    Handler que extiende RotatingFileHandler para forzar el guardado (flush)
    de logs al archivo cada cierto intervalo de tiempo.
    """
    def __init__(self, filename, maxBytes=0, backupCount=0, encoding=None, 
                 delay=False, flush_interval=20, **kwargs):
        """
        Inicializa el handler con un intervalo de flush.
        
        Args:
            filename: Ruta al archivo de log
            maxBytes: Tamaño máximo del archivo antes de rotar (0 = sin límite)
            backupCount: Número de archivos de respaldo
            encoding: Codificación del archivo
            delay: Si True, el archivo no se abre hasta el primer log
            flush_interval: Intervalo en segundos para forzar el flush (por defecto 20)
        """
        super().__init__(
            filename, maxBytes=maxBytes, backupCount=backupCount,
            encoding=encoding, delay=delay, **kwargs
        )
        self.flush_interval = flush_interval
        self.last_flush = time.time()
        self.flush_lock = threading.Lock()
        
        # Iniciar el thread de flush periódico
        self._start_flush_thread()
    
    def _start_flush_thread(self):
        """Inicia un thread que hace flush periódicamente."""
        self.should_stop = False
        
        def flush_thread():
            while not self.should_stop:
                time.sleep(1)  # Comprobar cada segundo
                now = time.time()
                if now - self.last_flush >= self.flush_interval:
                    with self.flush_lock:
                        self.flush()
                        self.last_flush = now
        
        self.flush_thread = threading.Thread(
            target=flush_thread, 
            daemon=True,  # Thread se cierra cuando el programa termina
            name=f"LogFlushThread-{self.baseFilename}"
        )
        self.flush_thread.start()
    
    def emit(self, record):
        """
        Emite un registro de log y fuerza flush si ha pasado el intervalo.
        """
        super().emit(record)
        now = time.time()
        # Si ha pasado el intervalo, hacer flush
        if now - self.last_flush >= self.flush_interval:
            with self.flush_lock:
                self.flush()
                self.last_flush = now
    
    def close(self):
        """Cierra el handler y detiene el thread de flush."""
        self.should_stop = True
        if hasattr(self, 'flush_thread') and self.flush_thread.is_alive():
            self.flush_thread.join(timeout=1)  # Esperar a que termine el thread
        super().close()


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
    
    # Determinar la ruta de logs
    # Encontrar la carpeta backend para guardar los logs
    # Buscar desde el directorio actual hacia arriba
    current_dir = Path.cwd()
    backend_dir = None
    
    # Si el directorio actual es 'backend' o contiene 'backend'
    if current_dir.name == 'backend' or 'backend' in str(current_dir):
        search_dir = current_dir
        
        # Buscar hacia arriba hasta encontrar la carpeta backend
        while search_dir.parent != search_dir:  # Evitar bucle infinito en la raíz
            if search_dir.name == 'backend':
                backend_dir = search_dir
                break
            elif (search_dir / 'backend').exists() and (search_dir / 'backend').is_dir():
                backend_dir = search_dir / 'backend'
                break
            
            search_dir = search_dir.parent
    
    # Si no encontramos 'backend', usar el directorio actual
    if not backend_dir:
        backend_dir = current_dir
        
    # Crear el directorio de logs en backend/logs
    log_dir = str(backend_dir / 'logs')
    
    # Crear el directorio de logs si no existe
    os.makedirs(log_dir, exist_ok=True)
    
    # Configurar archivo de log con rotación y flush periódico
    log_file = os.path.join(log_dir, f"{service}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,          # Mantener 5 archivos de respaldo
        encoding='utf-8',
        flush_interval=20       # Forzar flush cada 20 segundos
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
    
    # Filtro para ocultar o truncar mensajes de licencia
    class LicenseFilter(logging.Filter):
        """Filtro para evitar que se muestren mensajes de licencia largos en los logs."""
        def __init__(self, max_length=100):
            super().__init__()
            self.max_length = max_length
            # Palabras clave que indican mensajes de licencia
            self.license_keywords = ["license", "eula", "terms of service", "copyright", "all rights reserved", "llama-2", "llama-3"]
        
        def filter(self, record):
            # Si el mensaje contiene palabras de licencia y es muy largo, truncarlo
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                msg_lower = record.msg.lower()
                if any(keyword in msg_lower for keyword in self.license_keywords) and len(record.msg) > self.max_length:
                    # Truncar el mensaje
                    record.msg = record.msg[:self.max_length] + "... [licencia truncada]"
            return True
    
    # Crear y aplicar el filtro
    license_filter = LicenseFilter(max_length=100)
    root_logger = logging.getLogger()
    root_logger.addFilter(license_filter)
    
    # Establecer niveles específicos para algunos loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    
    # Reducir los logs de bibliotecas que suelen mostrar licencias
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langchain_core").setLevel(logging.WARNING)
    logging.getLogger("langchain_openai").setLevel(logging.WARNING)
    logging.getLogger("llama_index").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    
    # Log de inicio
    logging.info(f"Logging iniciado para el servicio '{service}' con nivel: {logging.getLevelName(level)}")
    logging.info(f"Los logs se guardan en: {log_file} (flush cada {file_handler.flush_interval} segundos)")


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado con el nombre especificado.
    
    Args:
        name: Nombre del logger
        
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)