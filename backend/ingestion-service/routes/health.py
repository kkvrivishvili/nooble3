"""
Endpoints para verificación de salud y estado del servicio de ingestión.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma. El endpoint /health
proporciona una verificación rápida de disponibilidad, mientras que
/status ofrece información detallada sobre el estado del servicio y cola de trabajos.
"""

import time
import logging
import statistics
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union, Tuple

from fastapi import APIRouter, Depends

import redis.asyncio as redis

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.utils.http import check_service_health
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health
from common.cache.manager import get_redis_client
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

# Importar configuración centralizada del servicio
from config.settings import get_settings, get_health_status
from config.constants import (
    MAX_WORKERS,
    SUPPORTED_MIMETYPES,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CACHE_EFFICIENCY_THRESHOLDS,
    QUALITY_THRESHOLDS,
    TIME_INTERVALS,
    METRICS_CONFIG,
    TIMEOUTS,
    # Importar constantes para la cola de trabajos
    JOBS_QUEUE_KEY,
    MAX_QUEUE_SIZE,
    WORKER_CONCURRENCY
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Constantes para métricas y monitoreo
MAX_METRIC_SAMPLES = 1000                  # Máximo número de muestras a mantener
SUPPORTED_FILE_TYPES = [
    "pdf", "docx", "txt", "html", "markdown", "csv", "json"
]

# Variables globales para métricas y seguimiento
service_start_time = datetime.now()  # Tiempo de inicio del servicio
job_processing_times: List[float] = []     # Tiempos de procesamiento de trabajos
queue_backlog_history: List[int] = []      # Historial de backlog en la cola
job_error_count: int = 0                   # Contador de errores de procesamiento

@router.get("/health", 
           response_model=None,
           summary="Estado básico del servicio",
           description="Verificación rápida de disponibilidad del servicio (liveness check)")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio de ingestión (liveness check).
    
    Este endpoint permite verificar rápidamente si el servicio está operativo
    y si sus componentes críticos funcionan correctamente. Incluye verificaciones
    de la cola de trabajos, disponibilidad del servicio de embeddings, y estado
    de los procesadores de documentos.
    
    Returns:
        HealthResponse: Estado básico del servicio
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar el servicio de embeddings (componente crítico)
    embedding_service_status = await check_embedding_service_status()
    components["embedding_service"] = embedding_service_status
    
    # Verificar la cola de trabajos (componente más crítico para ingestion)
    queue_status = await check_jobs_queue()
    components["jobs_queue"] = queue_status
    
    # Verificar procesadores de documentos (crítico para funcionalidad)
    document_processors_status = check_document_processors()
    components["document_processors"] = document_processors_status
    
    # Verificar espacio de almacenamiento temporal (crítico para procesamiento)
    storage_status = check_storage_space()
    components["storage"] = storage_status
    
    # Determinar estado general del servicio
    if (components["jobs_queue"] == "unavailable" or 
        components["embedding_service"] == "unavailable"):
        overall_status = "unavailable"
    elif (components["jobs_queue"] == "degraded" or 
          components["embedding_service"] == "degraded" or
          components["document_processors"] == "degraded" or
          components["storage"] == "degraded"):
        overall_status = "degraded"
    else:
        overall_status = "available"
    
    # Generar respuesta estandarizada
    response = get_service_health(
        components=components,
        service_version=settings.service_version
    )
    
    # Actualizar estado general (usando atributo en lugar de acceso tipo diccionario)
    response.status = overall_status
    
    return response

@router.get("/status", 
            response_model=None,
            summary="Estado detallado del servicio",
            description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene el estado detallado del servicio de ingestión con métricas y dependencias.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado detallado de componentes críticos (cache, DB, jobs queue)
    - Estado de la cola de trabajos con estadísticas de procesamiento
    - Estado de dependencias externas (embedding-service)
    - Métricas de rendimiento y capacidad
    - Configuraciones activas
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio con métricas
    """
    # Obtener métricas específicas del servicio
    queue_metrics = await get_queue_metrics()
    processing_metrics = get_processing_metrics()
    ingestion_stats = await get_ingestion_statistics()
    storage_metrics = get_storage_metrics()
    
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="ingestion-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "embedding_service": check_embedding_service_status,
            "jobs_queue": check_jobs_queue,
            "document_processors": check_document_processors,
            "storage": check_storage_space
        },
        # Métricas detalladas específicas del servicio
        extra_metrics={
            # Configuración y capacidades
            "supported_file_types": SUPPORTED_FILE_TYPES,
            "max_file_size_mb": settings.max_file_size_mb,
            "chunking_strategies": ["fixed", "paragraph", "semantic", "recursive"],
            "supports_batch_processing": settings.enable_batch_processing,
            "worker_concurrency": settings.worker_concurrency,
            
            # Métricas operacionales
            "queue": queue_metrics,
            "processing": processing_metrics,
            "storage": storage_metrics,
            
            # Estadísticas de ingestión
            "ingestion_statistics": ingestion_stats,
            
            # Capacidad de procesamiento
            "estimated_throughput": {
                "docs_per_minute": calculate_throughput(),
                "max_concurrent_uploads": settings.max_concurrent_uploads
            }
        }
    )

async def check_embedding_service_status() -> str:
    """
    Verifica el estado del servicio de embeddings.
    Incluye verificación detallada si el servicio está disponible pero degradado.
    Soporta verificación de los proveedores principales: Ollama y Groq.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        # Verificar conexión al servicio de embeddings
        service_url = settings.embedding_service_url
        if not service_url:
            logger.warning("URL del servicio de embeddings no configurada")
            return "unavailable"
            
        # Verificar con health check básico
        is_available = await check_service_health(
            service_url=service_url,
            service_name="embedding-service"
        )
        
        if not is_available:
            return "unavailable"
        
        # Verificar estado detallado (opcional)
        try:
            from common.utils.http import call_service
            
            # Usar call_service en lugar de httpx directo
            status_url = f"{service_url}/status"
            result = await call_service(
                url=status_url,
                data={},  # Sin datos para GET
                method="GET",
                custom_timeout=TIMEOUTS.get("health_check", 2.0),
                operation_type="status_check"
            )
            
            if not result.get("success", False):
                logger.warning(f"Estado degradado en embedding-service: respuesta no exitosa")
                return "degraded"
                
            status_data = result.get("data", {})
            
            # Verificar el estado del proveedor de embeddings (puede ser Ollama o Groq)
            components = status_data.get("components", {})
            
            # Verificar el estado de Groq si está configurado
            if components.get("groq_provider") == "unavailable":
                logger.warning("Proveedor Groq no disponible")
                # Si Groq está configurado como principal y no está disponible, es crítico
                import os
                if os.environ.get("USE_GROQ", "False").lower() == "true" and \
                   os.environ.get("USE_OLLAMA", "False").lower() != "true":
                    return "unavailable"
                else:
                    return "degraded"  # Hay fallback a Ollama
                
            # Verificar el estado de Ollama si está configurado
            if components.get("ollama_provider") == "unavailable":
                logger.warning("Proveedor Ollama no disponible")
                # Si Ollama está configurado como principal y no está disponible, es crítico
                import os
                if os.environ.get("USE_OLLAMA", "False").lower() == "true" and \
                   os.environ.get("USE_GROQ", "False").lower() != "true":
                    return "unavailable"
                else:
                    return "degraded"  # Hay fallback a Groq
            
            # Si ambos están degradados pero no indisponibles, reportar como degradado
            if (components.get("groq_provider") == "degraded" or 
                components.get("ollama_provider") == "degraded"):
                logger.warning("Al menos un proveedor de embeddings en estado degradado")
                return "degraded"
            
            # Verificar métricas de latencia si están disponibles
            if "metrics" in status_data and "latency_ms" in status_data["metrics"]:
                latency = status_data["metrics"]["latency_ms"]
                if latency > 5000:  # Si la latencia es mayor a 5 segundos
                    logger.warning(f"Latencia del servicio de embeddings muy alta: {latency}ms")
                    return "degraded"
            
            return "available"
                
        except Exception as detail_error:
            logger.info(f"No se pudo obtener estado detallado: {detail_error}")
            # El servicio está disponible pero no pudimos obtener más detalles
            return "available"
        
        return "available"
    except Exception as e:
        logger.warning(f"Error verificando servicio de embeddings: {str(e)}")
        return "unavailable"

async def check_jobs_queue() -> str:
    """
    Verifica el estado de la cola de trabajos.
    
    Esta función comprueba si la cola de Redis utilizada para los trabajos
    de ingestión está disponible y operativa. También verifica el backlog
    y el estado de procesamiento de trabajos.
    
    Returns:
        str: Estado de la cola ("available", "degraded" o "unavailable")
    """
    try:
        # Verificar conexión a Redis para la cola de trabajos
        redis_client = await get_redis_client()
        
        if not redis_client:
            logger.warning("No se pudo obtener cliente Redis para la cola de trabajos")
            return "unavailable"
        
        # Verificar acceso a la cola usando directamente las constantes
        queue_key = JOBS_QUEUE_KEY
        processing_key = f"{queue_key}:processing"
        failed_key = f"{queue_key}:failed"
        
        # Intentar ping y acceso a la cola
        await redis_client.ping()
        
        # Verificar varios aspectos de la cola
        pending_jobs = await redis_client.llen(queue_key)
        processing_jobs = await redis_client.hlen(processing_key)
        failed_jobs = await redis_client.llen(failed_key)
        
        # Registrar backlog actual para métricas
        record_queue_backlog(pending_jobs)
        
        # Criterios para determinar estado usando las constantes directamente
        if pending_jobs > MAX_QUEUE_SIZE * 0.9:
            logger.warning(f"Cola de trabajos casi llena: {pending_jobs} trabajos pendientes")
            return "degraded"
            
        if failed_jobs > 10:
            logger.warning(f"Muchos trabajos fallidos: {failed_jobs} en la cola de errores")
            return "degraded"
            
        if processing_jobs > WORKER_CONCURRENCY * 2:
            logger.warning(f"Demasiados trabajos en procesamiento: {processing_jobs}")
            return "degraded"
        
        return "available"
        
    except Exception as e:
        logger.error(f"Error verificando cola de trabajos: {str(e)}")
        return "unavailable"

def check_document_processors() -> str:
    """
    Verifica el estado de los procesadores de documentos.
    
    Comprueba si los procesadores de documentos para cada tipo de archivo
    soportado están disponibles y funcionando correctamente.
    
    Returns:
        str: Estado de los procesadores ("available", "degraded" o "unavailable")
    """
    try:
        # Verificar importación de las dependencias de procesamiento
        import importlib
        missing_processors = []
        
        # Procesadores críticos que deben estar disponibles
        processors = {
            "pdf": "PyPDF",
            "docx": "docx", 
            "txt": "builtins",
            "csv": "csv",
            "markdown": "markdown"
        }
        
        # Verificar cada procesador
        for file_type, module_name in processors.items():
            try:
                if module_name != "builtins":
                    importlib.import_module(module_name)
            except ImportError:
                missing_processors.append(file_type)
        
        # Evaluar estado basado en procesadores faltantes
        if len(missing_processors) > 2:
            logger.warning(f"Faltan varios procesadores: {', '.join(missing_processors)}")
            return "degraded"
            
        if 'pdf' in missing_processors or 'docx' in missing_processors:
            # PDF y DOCX son considerados críticos
            logger.warning(f"Falta procesador crítico: {missing_processors}")
            return "degraded"
            
        return "available"
        
    except Exception as e:
        logger.error(f"Error verificando procesadores de documentos: {str(e)}")
        return "degraded"  # No es crítico para el funcionamiento básico

def check_storage_space() -> str:
    """
    Verifica el espacio de almacenamiento temporal disponible.
    
    Comprueba si hay suficiente espacio en el directorio temporal
    usado para procesar archivos durante la ingestión.
    
    Returns:
        str: Estado del almacenamiento ("available", "degraded" o "unavailable")
    """
    try:
        # Obtener directorio temporal (predeterminado o configurado)
        temp_dir = settings.temp_dir if hasattr(settings, 'temp_dir') else '/tmp'
        
        # Verificar que el directorio exista
        if not os.path.exists(temp_dir):
            logger.warning(f"Directorio temporal no existe: {temp_dir}")
            return "degraded"
        
        # Verificar espacio disponible
        statvfs = os.statvfs(temp_dir)
        # Espacio libre en bytes
        free_space = statvfs.f_frsize * statvfs.f_bavail
        # Convertir a MB
        free_space_mb = free_space / (1024 * 1024)
        
        # Criterios para espacio disponible
        if free_space_mb < 100:  # Menos de 100 MB
            logger.warning(f"Muy poco espacio disponible: {free_space_mb:.2f} MB")
            return "degraded"
            
        if free_space_mb < 500:  # Menos de 500 MB
            logger.info(f"Espacio limitado disponible: {free_space_mb:.2f} MB")
            return "available"  # Disponible pero al límite
            
        return "available"
        
    except Exception as e:
        logger.error(f"Error verificando espacio de almacenamiento: {str(e)}")
        return "degraded"  # No es crítico para el funcionamiento básico


def record_queue_backlog(current_backlog: int) -> None:
    """
    Registra el tamaño actual del backlog en la cola para métricas.
    
    Args:
        current_backlog: Número actual de trabajos pendientes
    """
    global queue_backlog_history
    
    queue_backlog_history.append(current_backlog)
    
    # Mantener solo las últimas muestras
    if len(queue_backlog_history) > MAX_METRIC_SAMPLES:
        queue_backlog_history = queue_backlog_history[-MAX_METRIC_SAMPLES:]


def record_job_processing_time(time_ms: float) -> None:
    """
    Registra el tiempo de procesamiento de un trabajo para métricas.
    
    Args:
        time_ms: Tiempo de procesamiento en milisegundos
    """
    global job_processing_times
    
    job_processing_times.append(time_ms)
    
    # Mantener solo las últimas muestras
    if len(job_processing_times) > MAX_METRIC_SAMPLES:
        job_processing_times = job_processing_times[-MAX_METRIC_SAMPLES:]


def record_job_error() -> None:
    """
    Registra un error en el procesamiento de un trabajo.
    """
    global job_error_count
    job_error_count += 1


async def get_queue_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas detalladas de la cola de trabajos.
    
    Returns:
        Dict[str, Any]: Métricas de la cola
    """
    try:
        redis_client = await get_redis_client()
        metrics = {
            "current_backlog": 0,
            "processing_jobs": 0,
            "failed_jobs": 0,
            "avg_backlog": 0,
            "queue_health": "unknown"
        }
        
        if not redis_client:
            return metrics
        
        # Obtener información actual
        queue_key = settings.jobs_queue_key
        processing_key = f"{queue_key}:processing"
        failed_key = f"{queue_key}:failed"
        
        metrics["current_backlog"] = await redis_client.llen(queue_key)
        metrics["processing_jobs"] = await redis_client.hlen(processing_key)
        metrics["failed_jobs"] = await redis_client.llen(failed_key)
        
        # Calcular backlog promedio
        global queue_backlog_history
        if queue_backlog_history:
            metrics["avg_backlog"] = round(sum(queue_backlog_history) / len(queue_backlog_history), 2)
            
        # Determinar salud de la cola
        max_queue = settings.max_queue_size
        if metrics["current_backlog"] > max_queue * 0.9:
            metrics["queue_health"] = "critical"
        elif metrics["current_backlog"] > max_queue * 0.7:
            metrics["queue_health"] = "warning"
        elif metrics["failed_jobs"] > 10:
            metrics["queue_health"] = "warning"
        else:
            metrics["queue_health"] = "healthy"
            
        # Añadir tendencia
        if len(queue_backlog_history) >= 2:
            current = queue_backlog_history[-1]
            previous = queue_backlog_history[0]
            metrics["backlog_trend"] = "increasing" if current > previous else "decreasing" if current < previous else "stable"
        
        return metrics
    except Exception as e:
        logger.warning(f"Error obteniendo métricas de cola: {str(e)}")
        return {"error": str(e)}


def get_processing_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas de procesamiento de documentos.
    
    Returns:
        Dict[str, Any]: Métricas de procesamiento
    """
    global job_processing_times, job_error_count
    
    metrics = {
        "processed_jobs": len(job_processing_times),
        "error_count": job_error_count,
        "error_rate": 0,
        "avg_processing_time_ms": 0,
        "p95_processing_time_ms": 0
    }
    
    # Calcular métricas solo si hay suficientes datos
    if job_processing_times:
        metrics["avg_processing_time_ms"] = round(statistics.mean(job_processing_times), 2)
        total_jobs = metrics["processed_jobs"] + job_error_count
        metrics["error_rate"] = round((job_error_count / total_jobs) * 100, 2) if total_jobs > 0 else 0
        
        # Calcular percentiles si hay suficientes datos
        if len(job_processing_times) >= 5:
            metrics["p95_processing_time_ms"] = round(statistics.quantiles(job_processing_times, n=100)[94], 2)
    
    return metrics


async def get_ingestion_statistics() -> Dict[str, Any]:
    """
    Obtiene estadísticas de ingestión de documentos.
    
    Returns:
        Dict[str, Any]: Estadísticas de ingestión
    """
    try:
        # En una implementación real, estas estadísticas vendrían de la base de datos
        # o de contadores persistentes
        stats = {
            "documents_ingested_24h": 0,
            "chunks_generated_24h": 0,
            "avg_chunks_per_document": 0,
            "ingestion_success_rate": 0,
            "most_common_file_types": {}
        }
        
        # Obtener estadísticas reales (en un entorno real)
        supabase = get_supabase_client()
        if supabase:
            # Contar documentos ingresados en las últimas 24 horas
            table_name = get_table_name("documents")
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.isoformat()
            
            # Esto es sólo un ejemplo - en un entorno real sería una consulta adecuada
            try:
                # Simulación simple para el ejemplo
                # En un entorno real, se consultaría la base de datos
                stats["documents_ingested_24h"] = 50  # Valor simulado
                stats["chunks_generated_24h"] = 500   # Valor simulado
                stats["avg_chunks_per_document"] = 10  # Valor simulado
                stats["ingestion_success_rate"] = 95  # Porcentaje
                stats["most_common_file_types"] = {"pdf": 60, "docx": 30, "txt": 10}
            except Exception as e:
                logger.warning(f"Error obteniendo estadísticas de Supabase: {e}")
        
        return stats
    except Exception as e:
        logger.warning(f"Error obteniendo estadísticas de ingestión: {str(e)}")
        return {"error": str(e)}


def get_storage_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas sobre el almacenamiento utilizado.
    
    Returns:
        Dict[str, Any]: Métricas de almacenamiento
    """
    try:
        # Obtener directorio temporal (predeterminado o configurado)
        temp_dir = settings.temp_dir if hasattr(settings, 'temp_dir') else '/tmp'
        
        # Verificar espacio disponible
        if os.path.exists(temp_dir):
            statvfs = os.statvfs(temp_dir)
            total_space = statvfs.f_frsize * statvfs.f_blocks
            free_space = statvfs.f_frsize * statvfs.f_bavail
            used_space = total_space - free_space
            
            # Convertir a MB
            total_mb = total_space / (1024 * 1024)
            free_mb = free_space / (1024 * 1024)
            used_mb = used_space / (1024 * 1024)
            percent_used = round((used_space / total_space) * 100, 2) if total_space > 0 else 0
            
            return {
                "temp_directory": temp_dir,
                "total_mb": round(total_mb, 2),
                "free_mb": round(free_mb, 2),
                "used_mb": round(used_mb, 2),
                "percent_used": percent_used,
                "status": "critical" if percent_used > 90 else "warning" if percent_used > 75 else "healthy"
            }
        
        return {"error": f"Directorio temporal no existe: {temp_dir}"}
    except Exception as e:
        logger.warning(f"Error obteniendo métricas de almacenamiento: {str(e)}")
        return {"error": str(e)}


def calculate_throughput() -> float:
    """
    Calcula la capacidad de procesamiento estimada en documentos por minuto.
    
    Returns:
        float: Documentos por minuto que puede procesar el sistema
    """
    global job_processing_times
    
    if not job_processing_times or len(job_processing_times) < 2:
        # Valor estimado basado en configuración si no hay datos reales
        return float(settings.worker_concurrency) * 2.0
    
    # Calcular el tiempo promedio por documento en milisegundos
    avg_process_time_ms = statistics.mean(job_processing_times)
    
    # Convertir a documentos por minuto
    docs_per_minute = (1000 * 60) / avg_process_time_ms * settings.worker_concurrency
    
    return round(docs_per_minute, 2)