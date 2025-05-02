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

from common.api.context import Context, with_context
from common.api.errors import handle_errors
from common.helpers.health import (
    basic_health_check,
    detailed_status_check,
    HealthResponse,
    ServiceStatusResponse,
    get_service_health
)

logger = logging.getLogger(__name__)

# Creación del router para endpoints de health
health_router = APIRouter()

# Variable global para referenciar al scheduler
scheduler = None


def set_scheduler(scheduler_instance):
    """
    Establece la referencia global al scheduler.
    Necesario para realizar health checks específicos.
    """
    global scheduler
    scheduler = scheduler_instance


async def check_scheduler() -> str:
    """
    Verifica el estado del scheduler de tareas.
    
    Returns:
        str: Estado del scheduler ("available", "degraded" o "unavailable")
    """
    try:
        global scheduler
        if not scheduler:
            logger.warning("No hay referencia al scheduler")
            return "unavailable"
        
        if scheduler.running:
            # Verificar que hay al menos una tarea programada
            jobs = scheduler.get_jobs()
            if not jobs:
                logger.warning("Scheduler running pero sin tareas programadas")
                return "degraded"
            return "available"
        else:
            logger.warning("Scheduler no está en ejecución")
            return "degraded"
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
    
    # Si el scheduler no está disponible, el servicio no está disponible
    if scheduler_status == "unavailable":
        health_result["status"] = "unavailable"
    elif scheduler_status == "degraded" and health_result["status"] == "available":
        health_result["status"] = "degraded"
    
    return get_service_health(health_result)


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
    Incluye información sobre caché, base de datos, scheduler y tareas programadas.
    
    Returns:
        ServiceStatusResponse: Respuesta detallada con estado y métricas
    """
    # Verificar componentes y obtener estado detallado
    service_metrics = {
        "service_type": "worker",
        "reconciliation_enabled": True,
    }
    
    # Añadir métricas específicas del scheduler
    if scheduler:
        jobs = scheduler.get_jobs()
        service_metrics["jobs_count"] = len(jobs)
        service_metrics["scheduler_running"] = scheduler.running
        
        # Listar tareas programadas
        scheduled_jobs = []
        for job in jobs:
            scheduled_jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        service_metrics["scheduled_jobs"] = scheduled_jobs
    
    async def extra_checks():
        return {
            "scheduler": await check_scheduler()
        }
    
    return await detailed_status_check(
        service_name="worker-service",
        service_metrics=service_metrics,
        extra_checks=extra_checks
    )
