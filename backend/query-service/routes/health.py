"""
Endpoints para verificación de salud y estado del servicio.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma, proporcionando
endpoints consistentes para verificación de liveness y estado detallado.
"""

import time
import logging
import json
import statistics
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from fastapi import APIRouter
import httpx
from redis.asyncio import Redis

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.config import get_settings
from common.utils.http import check_service_health
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health
from common.cache.manager import get_redis_client
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Variables globales para métricas y seguimiento
service_start_time = time.time()
query_latencies: List[float] = []  # Almacena las últimas latencias de consulta
MAX_LATENCY_SAMPLES = 100          # Máximo número de muestras para cálculo de latencia

@router.get(
    "/health",
    response_model=None,
    summary="Estado básico del servicio",
    description="Verificación rápida de disponibilidad del servicio (liveness check)"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio (liveness check).
    
    Este endpoint proporciona información sobre la disponibilidad básica del servicio
    y sus componentes esenciales como caché, base de datos y servicios dependientes.
    Optimizado para ser rápido y ligero, ideal para health checks de Kubernetes.
    
    Returns:
        HealthResponse: Estado básico del servicio
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar el servicio de embeddings (dependencia crítica)
    embedding_status = await check_embedding_service()
    components["embedding_service"] = "available" if embedding_status else "unavailable"
    
    # Verificar acceso a vector stores (componente crítico)
    vector_store_status = await check_vector_stores()
    components["vector_stores"] = vector_store_status
    
    # Determinar estado general del servicio
    if components["embedding_service"] == "unavailable" or components["vector_stores"] == "unavailable":
        overall_status = "unavailable"
    elif components["vector_stores"] == "degraded" or components["cache"] == "unavailable":
        overall_status = "degraded"
    else:
        overall_status = "available"
    
    # Generar respuesta estandarizada
    response = get_service_health(
        components=components,
        service_version=settings.service_version
    )
    
    # Actualizar estado general
    response["status"] = overall_status
    
    return response

@router.get(
    "/status",
    response_model=None,
    summary="Estado detallado del servicio",
    description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias"
)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene el estado detallado del servicio con métricas avanzadas.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado detallado de componentes críticos (cache, DB, vector stores)
    - Estado de servicios dependientes (embedding-service)
    - Métricas de rendimiento (latencia, hit ratio de caché)
    - Estadísticas sobre índices y colecciones
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio
    """
    # Recopilar métricas avanzadas
    vector_metrics = await get_vector_store_metrics()
    performance_metrics = get_performance_metrics()
    
    # Usar el helper común con verificaciones específicas
    return await detailed_status_check(
        service_name="query-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "embedding_service": check_embedding_service_status,
            "vector_stores": check_vector_stores_detailed,
            "indices": check_indices_status
        },
        # Métricas avanzadas y específicas del servicio
        extra_metrics={
            # Información de capacidad
            "vector_databases": ["supabase", "redis"],
            "supported_query_types": ["similarity", "hybrid", "mmr"],
            "max_similarity_top_k": settings.max_similarity_top_k,
            
            # Métricas de rendimiento
            "performance": performance_metrics,
            
            # Estadísticas sobre índices y datos
            "vector_store_metrics": vector_metrics,
            
            # Información de configuración
            "embedding_dimensions": settings.embedding_dimensions,
            "default_response_mode": settings.default_response_mode
        }
    )


async def check_embedding_service() -> bool:
    """
    Verifica la disponibilidad del servicio de embeddings usando la función común.
    
    Returns:
        bool: True si el servicio está disponible, False en caso contrario
    """
    return await check_service_health(
        service_url=settings.embedding_service_url, 
        service_name="embedding-service"
    )

async def check_embedding_service_status() -> str:
    """
    Verifica el estado detallado del servicio de embeddings.
    Intenta obtener más detalles usando el endpoint /status.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        basic_check = await check_embedding_service()
        if not basic_check:
            return "unavailable"
            
        # Verificar detalles usando /status
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.embedding_service_url}/status")
            
            if response.status_code != 200:
                return "degraded"
                
            status_data = response.json()
            
            # Verificar el estado del proveedor de embeddings
            provider_status = status_data.get("components", {}).get("embedding_provider")
            if provider_status == "degraded":
                return "degraded"
                
            return "available"
    except Exception as e:
        logger.warning(f"Error verificando estado detallado de embedding-service: {e}")
        return "degraded" if basic_check else "unavailable"

async def check_vector_stores() -> str:
    """
    Verifica el estado de las bases de datos vectoriales.
    
    Returns:
        str: Estado de los vector stores ("available", "degraded" o "unavailable")
    """
    try:
        # Verificar conexión a Supabase (vector store principal)
        supabase = get_supabase_client()
        table_name = get_table_name("document_chunks")
        
        # Intentar consulta básica
        result = await supabase.table(table_name).select("count").limit(1).execute()
        
        # Si hay algún problema con el almacenamiento secundario, marcar como degradado
        redis_client = await get_redis_client()
        if not redis_client:
            return "degraded"
            
        return "available"
    except Exception as e:
        logger.warning(f"Error verificando vector stores: {e}")
        return "unavailable"
        
async def check_vector_stores_detailed() -> str:
    """
    Verifica el estado detallado de las bases de datos vectoriales.
    
    Returns:
        str: Estado detallado de los vector stores
    """
    return await check_vector_stores()

async def check_indices_status() -> str:
    """
    Verifica el estado de los índices vectoriales.
    
    Returns:
        str: Estado de los índices ("available", "degraded" o "unavailable")
    """
    try:
        # Verificar que los índices estén disponibles
        supabase = get_supabase_client()
        table_name = get_table_name("collections")
        
        # Contar colecciones con índices
        result = await supabase.table(table_name).select("collection_id").execute()
        collections = result.data
        
        if not collections:
            return "degraded"  # No hay colecciones configuradas
        
        return "available"
    except Exception as e:
        logger.warning(f"Error verificando índices: {e}")
        return "unavailable"

async def get_vector_store_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas detalladas de los vector stores.
    
    Returns:
        Dict[str, Any]: Métricas de vector stores
    """
    try:
        supabase = get_supabase_client()
        metrics = {
            "total_collections": 0,
            "total_chunks": 0,
            "avg_chunks_per_collection": 0,
            "empty_collections": 0
        }
        
        # Obtener número de colecciones
        collections_table = get_table_name("collections")
        collections_result = await supabase.table(collections_table).select("collection_id").execute()
        collections = collections_result.data
        metrics["total_collections"] = len(collections)
        
        # Obtener número total de chunks
        chunks_table = get_table_name("document_chunks")
        chunks_result = await supabase.table(chunks_table).select("count").execute()
        total_chunks = chunks_result.data[0]["count"] if chunks_result.data else 0
        metrics["total_chunks"] = total_chunks
        
        # Calcular promedio si hay colecciones
        if metrics["total_collections"] > 0:
            metrics["avg_chunks_per_collection"] = round(total_chunks / metrics["total_collections"], 2)
        
        return metrics
    except Exception as e:
        logger.warning(f"Error obteniendo métricas de vector stores: {e}")
        return {"error": str(e)}

def get_performance_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas de rendimiento del servicio.
    
    Returns:
        Dict[str, Any]: Métricas de rendimiento
    """
    global query_latencies
    
    if not query_latencies:
        return {
            "query_count": 0,
            "avg_latency_ms": 0,
            "p95_latency_ms": 0,
            "p99_latency_ms": 0
        }
    
    metrics = {
        "query_count": len(query_latencies),
        "avg_latency_ms": round(statistics.mean(query_latencies), 2),
    }
    
    # Añadir percentiles si hay suficientes datos
    if len(query_latencies) >= 5:
        metrics["p95_latency_ms"] = round(statistics.quantiles(query_latencies, n=100)[94], 2)
        metrics["p99_latency_ms"] = round(statistics.quantiles(query_latencies, n=100)[98], 2)
    
    return metrics

def record_query_latency(latency_ms: float) -> None:
    """
    Registra la latencia de una consulta para cálculo de métricas.
    
    Args:
        latency_ms: Latencia de la consulta en milisegundos
    """
    global query_latencies
    
    query_latencies.append(latency_ms)
    
    # Mantener solo las últimas MAX_LATENCY_SAMPLES muestras
    if len(query_latencies) > MAX_LATENCY_SAMPLES:
        query_latencies = query_latencies[-MAX_LATENCY_SAMPLES:]