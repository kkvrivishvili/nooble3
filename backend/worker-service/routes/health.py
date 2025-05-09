"""
Endpoints de health y status para worker-service.

Implementa:
- /health: Verificación rápida de disponibilidad del servicio (liveness check)
- /status: Información detallada del servicio (monitoring, observability)

Utiliza los helpers centralizados de common/helpers/health.py
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends

from common.context import Context, with_context
from common.errors import handle_errors
from common.models import HealthResponse, ServiceStatusResponse 
from common.helpers.health import (
    basic_health_check,
    detailed_status_check,
    get_service_health,
    check_groq_availability,
    check_ollama_availability
)

logger = logging.getLogger(__name__)

# Creación del router para endpoints de health
health_router = APIRouter()

# Variables globales para referenciar componentes y métricas
scheduler = None
service_start_time = None

# Métricas para monitoreo de tareas
job_execution_times = {}
job_error_counts = {}
job_success_counts = {}
last_execution_times = {}

# Constantes para alertas y umbrales
MAX_CONSECUTIVE_FAILURES = 3
MAX_EXECUTION_TIME_FACTOR = 2.0  # Factor máximo sobre el tiempo promedio


def set_scheduler(scheduler_instance):
    """
    Establece la referencia global al scheduler.
    Necesario para realizar health checks específicos.
    
    Args:
        scheduler_instance: Instancia del scheduler APScheduler
    """
    global scheduler, service_start_time
    scheduler = scheduler_instance
    
    # Registrar tiempo de inicio del servicio
    from datetime import datetime
    service_start_time = datetime.now()
    
    # Configurar listeners para métricas si el scheduler existe
    if scheduler:
        scheduler.add_listener(record_job_executed, 'executed')
        scheduler.add_listener(record_job_error, 'error')


def record_job_executed(event):
    """
    Registra métricas para trabajos ejecutados exitosamente.
    
    Args:
        event: Evento de ejecución de tarea del scheduler
    """
    try:
        # Extraer información del evento
        job_id = event.job_id
        runtime = event.retval  # Asumiendo que retval contiene el tiempo de ejecución
        
        # Registrar tiempo de ejecución si es un número válido
        if isinstance(runtime, (int, float)):
            if job_id not in job_execution_times:
                job_execution_times[job_id] = []
            job_execution_times[job_id].append(runtime)
            
            # Mantener solo los últimos 10 valores
            if len(job_execution_times[job_id]) > 10:
                job_execution_times[job_id] = job_execution_times[job_id][-10:]
        
        # Registrar éxito
        job_success_counts[job_id] = job_success_counts.get(job_id, 0) + 1
        
        # Registrar tiempo de última ejecución
        from datetime import datetime
        last_execution_times[job_id] = datetime.now()
    except Exception as e:
        logger.warning(f"Error registrando métricas de ejecución: {e}")

def record_job_error(event):
    """
    Registra métricas para trabajos fallidos.
    
    Args:
        event: Evento de error de tarea del scheduler
    """
    try:
        # Extraer información del evento
        job_id = event.job_id
        exception = event.exception
        traceback = event.traceback
        
        # Registrar error
        job_error_counts[job_id] = job_error_counts.get(job_id, 0) + 1
        
        # Registrar tiempo de última ejecución (aunque haya fallado)
        from datetime import datetime
        last_execution_times[job_id] = datetime.now()
        
        # Registrar error en logs para observabilidad
        logger.error(
            f"Error en tarea {job_id}: {str(exception)}\n"
            f"Errores consecutivos: {job_error_counts[job_id]}"
        )
    except Exception as e:
        logger.warning(f"Error registrando métricas de error: {e}")

async def check_scheduler() -> str:
    """
    Verifica el estado del scheduler de tareas y su configuración.
    Realiza verificaciones detalladas para cada componente del sistema.
    
    Returns:
        str: Estado del scheduler ("available", "degraded" o "unavailable")
    """
    try:
        global scheduler
        if not scheduler:
            logger.warning("No hay referencia al scheduler")
            return "unavailable"
        
        # Verificar si el scheduler está ejecutándose
        if not scheduler.running:
            logger.warning("Scheduler no está en ejecución")
            return "unavailable"
        
        # Obtener trabajos programados
        jobs = scheduler.get_jobs()
        if not jobs:
            logger.warning("Scheduler running pero sin tareas programadas")
            return "degraded"
        
        # Verificar que los trabajos críticos estén programados
        critical_jobs = []
        for job in jobs:
            # Considerar ciertos trabajos como críticos (personalizables)
            if hasattr(job, "id") and any(keyword in job.id for keyword in ["sync", "reconcile", "cleanup"]):
                critical_jobs.append(job)
                
        if not critical_jobs:
            logger.warning("No se encontraron trabajos críticos programados")
            return "degraded"
        
        # Verificar errores continuos en tareas
        for job_id, error_count in job_error_counts.items():
            if error_count >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(f"Tarea {job_id} con {error_count} errores consecutivos")
                return "degraded"
        
        # Verificar que las tareas se estén ejecutando recientemente
        from datetime import datetime, timedelta
        now = datetime.now()
        for job in jobs:
            if job.id in last_execution_times:
                last_run = last_execution_times[job.id]
                expected_interval = getattr(job.trigger, "interval", timedelta(hours=24))
                
                # Si una tarea no se ha ejecutado en 2x su intervalo esperado
                if now - last_run > expected_interval * 2:
                    logger.warning(f"Tarea {job.id} sin ejecutar desde {last_run}")
                    return "degraded"
        
        return "available"
    except Exception as e:
        logger.error(f"Error verificando el scheduler: {e}")
        return "unavailable"


@health_router.get(
    "/health", 
    response_model=None,
    summary="Estado básico del servicio",
    description="Verificación rápida de disponibilidad del servicio (liveness check)"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Endpoint para verificación básica de salud del servicio.
    Comprueba componentes esenciales: caché, base de datos y scheduler.
    
    Returns:
        HealthResponse: Respuesta con estado básico
    """
    # Verificaciones básicas de componentes críticos
    health_result = await basic_health_check()
    
    # Añadir verificación específica del scheduler
    scheduler_status = await check_scheduler()
    health_result["components"]["scheduler"] = scheduler_status
    
    # Verificación de disponibilidad de Groq y Ollama
    try:
        groq_status = await check_groq_availability()
        health_result["components"]["groq"] = groq_status
    except Exception as e:
        logger.warning(f"Error verificando Groq: {e}")
        health_result["components"]["groq"] = "unavailable"
    
    try:
        ollama_status = await check_ollama_availability()
        health_result["components"]["ollama"] = ollama_status
    except Exception as e:
        logger.warning(f"Error verificando Ollama: {e}")
        health_result["components"]["ollama"] = "unavailable"
    
    # Si el scheduler no está disponible, el servicio no está disponible
    if scheduler_status == "unavailable":
        health_result["status"] = "unavailable"
    # Si Groq y Ollama están indisponibles, marcar como degradado
    elif (health_result["components"].get("groq") == "unavailable" and 
          health_result["components"].get("ollama") == "unavailable") and \
         health_result["status"] == "available":
        health_result["status"] = "degraded"
    elif scheduler_status == "degraded" and health_result["status"] == "available":
        health_result["status"] = "degraded"
    
    return get_service_health(health_result)


async def get_system_resources():
    """
    Obtiene información sobre recursos del sistema como CPU, memoria y disco.
    
    Returns:
        dict: Diccionario con métricas del sistema
    """
    try:
        import psutil
        import os
        
        # Obtener uso de CPU
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        
        # Obtener uso de memoria
        memory = psutil.virtual_memory()
        memory_usage = {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent": memory.percent
        }
        
        # Obtener uso de disco
        disk_path = os.path.abspath(os.sep)  # Ruta raíz
        disk = psutil.disk_usage(disk_path)
        disk_usage = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": disk.percent
        }
        
        # Obtener información de red
        net_io = psutil.net_io_counters()
        network = {
            "bytes_sent_mb": round(net_io.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(net_io.bytes_recv / (1024**2), 2),
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv
        }
        
        # Obtener procesos
        process = psutil.Process(os.getpid())
        process_info = {
            "memory_mb": round(process.memory_info().rss / (1024**2), 2),
            "cpu_percent": process.cpu_percent(interval=0.5),
            "threads": process.num_threads(),
            "open_files": len(process.open_files())
        }
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count
            },
            "memory": memory_usage,
            "disk": disk_usage,
            "network": network,
            "process": process_info
        }
    except ImportError:
        logger.warning("La biblioteca psutil no está instalada. Limitando métricas del sistema.")
        return {"error": "psutil no disponible"}
    except Exception as e:
        logger.warning(f"Error obteniendo métricas del sistema: {e}")
        return {"error": str(e)}

async def analyze_scheduler_jobs():
    """
    Analiza detalladamente el estado de las tareas programadas.
    
    Returns:
        dict: Diccionario con análisis de tareas
    """
    result = {
        "total_jobs": 0,
        "active_jobs": 0,
        "paused_jobs": 0,
        "critical_jobs": 0,
        "jobs_with_errors": 0,
        "avg_execution_times": {},
        "error_rates": {},
        "job_health": {}
    }
    
    if not scheduler:
        return {"error": "Scheduler no inicializado"}
    
    try:
        jobs = scheduler.get_jobs()
        result["total_jobs"] = len(jobs)
        
        # Clasificar trabajos
        for job in jobs:
            job_id = job.id
            
            # Determinar si es activo o pausado
            is_active = job.next_run_time is not None
            if is_active:
                result["active_jobs"] += 1
            else:
                result["paused_jobs"] += 1
            
            # Determinar si es crítico
            is_critical = any(keyword in job_id for keyword in ["sync", "reconcile", "cleanup"])
            if is_critical:
                result["critical_jobs"] += 1
            
            # Calcular errores y tiempos de ejecución
            error_count = job_error_counts.get(job_id, 0)
            success_count = job_success_counts.get(job_id, 0)
            execution_times = job_execution_times.get(job_id, [])
            
            if error_count > 0:
                result["jobs_with_errors"] += 1
            
            if execution_times:
                avg_time = sum(execution_times) / len(execution_times)
                result["avg_execution_times"][job_id] = round(avg_time, 2)
            
            if error_count + success_count > 0:
                error_rate = error_count / (error_count + success_count)
                result["error_rates"][job_id] = round(error_rate * 100, 2)
            
            # Evaluar salud de cada trabajo
            job_health = "healthy"
            if error_count >= MAX_CONSECUTIVE_FAILURES:
                job_health = "critical"
            elif error_count > 0:
                job_health = "warning"
            elif not is_active:
                job_health = "inactive"
            
            # Calcular última ejecución y próxima ejecución
            last_execution = None
            if job_id in last_execution_times:
                from datetime import datetime
                now = datetime.now()
                last_exec = last_execution_times[job_id]
                last_execution = {
                    "timestamp": last_exec.isoformat(),
                    "time_ago_seconds": (now - last_exec).total_seconds()
                }
            
            result["job_health"][job_id] = {
                "status": job_health,
                "is_active": is_active,
                "is_critical": is_critical,
                "error_count": error_count,
                "success_count": success_count,
                "last_execution": last_execution,
                "next_execution": job.next_run_time.isoformat() if job.next_run_time else None
            }
            
        return result
    except Exception as e:
        logger.error(f"Error analizando tareas programadas: {e}")
        return {"error": str(e)}

@health_router.get(
    "/status",
    response_model=None,
    summary="Estado detallado del servicio",
    description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Endpoint para obtener estado detallado y métricas del servicio.
    Incluye información sobre caché, base de datos, scheduler, tareas programadas
    y recursos del sistema.
    
    Returns:
        ServiceStatusResponse: Respuesta detallada con estado y métricas
    """
    # Métricas de servicio básicas
    from datetime import datetime
    uptime_seconds = 0
    if service_start_time:
        uptime_seconds = (datetime.now() - service_start_time).total_seconds()
    
    service_metrics = {
        "service_type": "worker",
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": f"{uptime_seconds // 86400:.0f}d {(uptime_seconds % 86400) // 3600:.0f}h {(uptime_seconds % 3600) // 60:.0f}m"
    }
    
    # Añadir métricas detalladas del scheduler
    if scheduler:
        # Métricas básicas del scheduler
        service_metrics["scheduler_status"] = {
            "running": scheduler.running,
            "timezone": str(scheduler.timezone)
        }
        
        # Análisis detallado de tareas programadas
        service_metrics["jobs_analysis"] = await analyze_scheduler_jobs()
        
        # Listar tareas programadas con detalles
        jobs = scheduler.get_jobs()
        scheduled_jobs = []
        for job in jobs:
            job_data = {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
                "misfire_grace_time": job.misfire_grace_time,
                "max_instances": job.max_instances,
                "executor": job.executor
            }
            
            # Añadir métricas de rendimiento si están disponibles
            if job.id in job_execution_times and job_execution_times[job.id]:
                job_data["avg_execution_time"] = sum(job_execution_times[job.id]) / len(job_execution_times[job.id])
                job_data["min_execution_time"] = min(job_execution_times[job.id])
                job_data["max_execution_time"] = max(job_execution_times[job.id])
            
            # Añadir contadores de errores y éxitos
            job_data["error_count"] = job_error_counts.get(job.id, 0)
            job_data["success_count"] = job_success_counts.get(job.id, 0)
            
            scheduled_jobs.append(job_data)
        service_metrics["scheduled_jobs"] = scheduled_jobs
    
    # Añadir métricas del sistema
    service_metrics["system_resources"] = await get_system_resources()
    
    async def extra_checks():
        return {
            "scheduler": await check_scheduler()
        }
    
    return await detailed_status_check(
        service_name="worker-service",
        service_metrics=service_metrics,
        extra_checks=extra_checks
    )
