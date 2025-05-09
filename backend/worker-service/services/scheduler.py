"""
Configuración del scheduler para tareas programadas.

Este módulo configura el scheduler (APScheduler) para ejecutar
tareas programadas en la plataforma, como reconciliación de tokens.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

from common.config.settings import get_service_settings
# Importación directa del módulo de tareas para evitar dependencias innecesarias
from common.tracking.scheduled_tasks import register_reconciliation_tasks

logger = logging.getLogger(__name__)

def create_scheduler():
    """
    Crea y configura una instancia del scheduler.
    
    Returns:
        AsyncIOScheduler: Instancia del scheduler de APScheduler
    """
    settings = get_service_settings("worker")
    
    # Configurar los executors para el scheduler
    executors = {
        'default': ThreadPoolExecutor(20),
        'processpool': ProcessPoolExecutor(5)
    }
    
    # Configuración general del scheduler
    job_defaults = {
        'coalesce': True,
        'max_instances': 3,
        'misfire_grace_time': 3600  # 1 hora
    }
    
    # Crear scheduler
    scheduler = AsyncIOScheduler(
        executors=executors,
        job_defaults=job_defaults,
        timezone='UTC'
    )
    
    return scheduler

async def initialize_scheduler():
    """
    Inicializa el scheduler con todas las tareas necesarias.
    
    Returns:
        AsyncIOScheduler: Instancia del scheduler inicializado
    """
    logger.info("Inicializando scheduler para tareas programadas")
    scheduler = create_scheduler()
    
    # Registrar tareas de reconciliación de tokens
    register_reconciliation_tasks(scheduler)
    
    # Aquí se pueden añadir otras tareas programadas
    # ...
    
    # Iniciar el scheduler
    scheduler.start()
    logger.info("Scheduler iniciado correctamente")
    
    return scheduler
