"""
Worker para procesamiento asíncrono de documentos
"""
import asyncio
import logging
import signal
import time
from typing import Set

from .queue import process_next_job, initialize_queue, shutdown_queue

logger = logging.getLogger(__name__)

# Control de estado
running = False
workers: Set[asyncio.Task] = set()

async def worker_process(worker_id: int):
    """Proceso worker individual que procesa trabajos de la cola."""
    logger.info(f"Worker {worker_id} iniciado")
    
    while running:
        try:
            # Intentar procesar el siguiente trabajo
            job_processed = await process_next_job()
            
            if not job_processed:
                # Si no hay trabajos, esperar un poco
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error en worker {worker_id}: {str(e)}", exc_info=True)
            await asyncio.sleep(5)  # Esperar más tiempo si hay error
    
    logger.info(f"Worker {worker_id} detenido")

async def start_worker_pool(num_workers: int = 3):
    """Inicia un pool de workers para procesar trabajos."""
    global running, workers
    
    if running:
        logger.warning("Worker pool ya está en ejecución")
        return
    
    # Inicializar cola
    if not await initialize_queue():
        logger.error("Error inicializando cola, workers no iniciados")
        return
    
    running = True
    
    # Crear workers
    for i in range(num_workers):
        task = asyncio.create_task(worker_process(i+1))
        workers.add(task)
        # Eliminar referencia cuando el task termina
        task.add_done_callback(workers.discard)
    
    logger.info(f"Pool de {num_workers} workers iniciado")

async def stop_worker_pool():
    """Detiene el pool de workers."""
    global running, workers
    
    if not running:
        return
    
    running = False
    
    # Esperar a que todos los workers terminen
    if workers:
        logger.info(f"Esperando a que {len(workers)} workers terminen...")
        await asyncio.gather(*workers, return_exceptions=True)
    
    # Cerrar cola
    await shutdown_queue()
    
    logger.info("Worker pool detenido")
