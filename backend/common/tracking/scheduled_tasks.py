"""
Tareas programadas para reconciliación de contadores de tokens.

Este módulo implementa tareas periódicas para asegurar la
consistencia entre los contadores en Redis y la base de datos.
"""

import logging
import asyncio
import json
from typing import Optional, Dict, Any

from ..config import get_settings
from . import reconciliation  # Importación estructurada para evitar ciclos
from .alerts import register_alert, AlertLevel

logger = logging.getLogger(__name__)

async def run_daily_reconciliation() -> Dict[str, Any]:
    """
    Tarea diaria para reconciliar tokens pendientes.
    
    Esta tarea procesa todos los registros pendientes en el conjunto
    'pending_token_reconciliation' asegurando que se persistan en la BD.
    
    Returns:
        Dict con estadísticas de la reconciliación
    """
    logger.info("Iniciando reconciliación diaria de tokens")
    settings = get_settings()
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Ejecutar reconciliación
        tokens_processed = await reconciliation.reconcile_pending_tokens()
        
        # Verificar umbral para alertas
        if tokens_processed > settings.reconciliation_alert_threshold:
            await register_alert(
                title="Alto volumen de reconciliación",
                message=f"Se procesaron {tokens_processed} registros pendientes, lo que supera el umbral de alerta ({settings.reconciliation_alert_threshold})",
                level=AlertLevel.WARNING,
                component="tracking",
                metadata={"processed_count": tokens_processed}
            )
            
        if tokens_processed > settings.reconciliation_critical_threshold:
            await register_alert(
                title="Volumen crítico de reconciliación",
                message=f"Se procesaron {tokens_processed} registros pendientes, lo que supera el umbral crítico ({settings.reconciliation_critical_threshold})",
                level=AlertLevel.CRITICAL,
                component="tracking",
                metadata={"processed_count": tokens_processed}
            )
        
        # Calcular tiempo total
        total_time = asyncio.get_event_loop().time() - start_time
        
        result = {
            "status": "success",
            "processed_count": tokens_processed,
            "duration_seconds": total_time
        }
        
        logger.info(f"Reconciliación diaria completada: {tokens_processed} registros procesados en {total_time:.2f}s")
        return result
        
    except Exception as e:
        logger.error(f"Error en reconciliación diaria: {str(e)}", exc_info=True)
        await register_alert(
            title="Error en reconciliación diaria",
            message=f"Ocurrió un error durante la reconciliación diaria: {str(e)}",
            level=AlertLevel.ERROR,
            component="tracking",
            metadata={"error": str(e), "traceback": str(asyncio.format_exc()) if hasattr(asyncio, 'format_exc') else None}
        )
        return {
            "status": "error",
            "error": str(e)
        }

async def run_weekly_consolidation() -> Dict[str, Any]:
    """
    Tarea semanal para consolidar contadores entre Redis y BD.
    
    Esta tarea sincroniza todos los contadores de tokens entre
    Redis y la base de datos, garantizando consistencia.
    
    Returns:
        Dict con estadísticas de la consolidación
    """
    logger.info("Iniciando consolidación semanal de contadores")
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Consolidar contadores LLM
        llm_count = await reconciliation.consolidate_counters(
            pattern="*:counter:token_usage:type:llm:*",
            token_type="llm"
        )
        
        # Consolidar contadores de embeddings
        embedding_count = await reconciliation.consolidate_counters(
            pattern="*:counter:token_usage:type:embedding:*",
            token_type="embedding"
        )
        
        # Calcular tiempo total
        total_time = asyncio.get_event_loop().time() - start_time
        
        result = {
            "status": "success",
            "llm_counters": llm_count,
            "embedding_counters": embedding_count,
            "total_counters": llm_count + embedding_count,
            "duration_seconds": total_time
        }
        
        logger.info(f"Consolidación semanal completada: {llm_count + embedding_count} contadores procesados en {total_time:.2f}s")
        return result
        
    except Exception as e:
        logger.error(f"Error en consolidación semanal: {str(e)}", exc_info=True)
        await register_alert(
            title="Error en consolidación semanal",
            message=f"Ocurrió un error durante la consolidación semanal: {str(e)}",
            level=AlertLevel.ERROR,
            component="tracking",
            metadata={"error": str(e), "traceback": str(asyncio.format_exc()) if hasattr(asyncio, 'format_exc') else None}
        )
        return {
            "status": "error",
            "error": str(e)
        }

async def run_monthly_audit() -> Dict[str, Any]:
    """
    Tarea mensual para auditar y corregir discrepancias en contadores.
    
    Esta tarea realiza una auditoría completa para detectar y corregir
    cualquier discrepancia entre los contadores en Redis y la base de datos.
    
    Returns:
        Dict con resultados de la auditoría
    """
    logger.info("Iniciando auditoría mensual de contadores")
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Ejecutar auditoría para todos los tenants
        audit_results = await reconciliation.audit_token_counters(days_back=30)
        
        # Calcular tiempo total
        total_time = asyncio.get_event_loop().time() - start_time
        
        # Generar alertas si hay muchas discrepancias
        if audit_results.get("mismatches", 0) > 0:
            await register_alert(
                title="Discrepancias en contadores de tokens",
                message=f"Se encontraron {audit_results.get('mismatches')} discrepancias entre Redis y la base de datos",
                level=AlertLevel.WARNING if audit_results.get("mismatches") < 100 else AlertLevel.ERROR,
                component="tracking",
                metadata={"audit_results": audit_results}
            )
        
        audit_results["duration_seconds"] = total_time
        logger.info(f"Auditoría mensual completada: {audit_results.get('reconciled', 0)} discrepancias corregidas en {total_time:.2f}s")
        
        return audit_results
        
    except Exception as e:
        logger.error(f"Error en auditoría mensual: {str(e)}", exc_info=True)
        await register_alert(
            title="Error en auditoría mensual",
            message=f"Ocurrió un error durante la auditoría mensual: {str(e)}",
            level=AlertLevel.ERROR,
            component="tracking",
            metadata={"error": str(e), "traceback": str(asyncio.format_exc()) if hasattr(asyncio, 'format_exc') else None}
        )
        return {
            "status": "error",
            "error": str(e)
        }

# Funciones para configurar tareas programadas con el scheduler elegido
def register_reconciliation_tasks(scheduler) -> None:
    """
    Registra todas las tareas de reconciliación en el scheduler.
    
    Args:
        scheduler: Instancia del scheduler (APScheduler, Celery, etc.)
    """
    settings = get_settings()
    
    # Configurar según el tipo de scheduler detectado
    if hasattr(scheduler, 'add_job'):  # APScheduler
        scheduler.add_job(
            run_daily_reconciliation,
            'cron',
            **_parse_cron(settings.reconciliation_schedule_daily),
            id='daily_reconciliation',
            replace_existing=True
        )
        
        scheduler.add_job(
            run_weekly_consolidation,
            'cron',
            **_parse_cron(settings.reconciliation_schedule_weekly),
            id='weekly_consolidation',
            replace_existing=True
        )
        
        scheduler.add_job(
            run_monthly_audit,
            'cron',
            **_parse_cron(settings.reconciliation_schedule_monthly),
            id='monthly_audit',
            replace_existing=True
        )
    
    elif hasattr(scheduler, 'schedule'):  # Celery
        from celery.schedules import crontab
        
        scheduler.add_periodic_task(
            _to_celery_crontab(settings.reconciliation_schedule_daily),
            run_daily_reconciliation.s(),
            name='daily_reconciliation'
        )
        
        scheduler.add_periodic_task(
            _to_celery_crontab(settings.reconciliation_schedule_weekly),
            run_weekly_consolidation.s(),
            name='weekly_consolidation'
        )
        
        scheduler.add_periodic_task(
            _to_celery_crontab(settings.reconciliation_schedule_monthly),
            run_monthly_audit.s(),
            name='monthly_audit'
        )
    
    else:
        logger.warning(f"Tipo de scheduler no soportado: {type(scheduler)}")

def _parse_cron(cron_expr: str) -> Dict[str, Any]:
    """
    Convierte expresión cron a formato para APScheduler.
    
    Args:
        cron_expr: Expresión cron (e.g. "0 2 * * *")
        
    Returns:
        Dict con parámetros para APScheduler
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Expresión cron inválida: {cron_expr}")
        
    return {
        'minute': parts[0],
        'hour': parts[1],
        'day': parts[2],
        'month': parts[3],
        'day_of_week': parts[4]
    }

def _to_celery_crontab(cron_expr: str) -> Any:
    """
    Convierte expresión cron a formato para Celery.
    
    Args:
        cron_expr: Expresión cron (e.g. "0 2 * * *")
        
    Returns:
        crontab para Celery
    """
    from celery.schedules import crontab
    parts = cron_expr.split()
    
    if len(parts) != 5:
        raise ValueError(f"Expresión cron inválida: {cron_expr}")
        
    return crontab(
        minute=parts[0],
        hour=parts[1],
        day_of_month=parts[2],
        month_of_year=parts[3],
        day_of_week=parts[4]
    )
