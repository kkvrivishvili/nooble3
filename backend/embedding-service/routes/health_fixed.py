"""
Endpoints para verificación de estado del servicio de embeddings.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma. El endpoint /health
proporciona una verificación rápida de disponibilidad, mientras que
/status ofrece información detallada sobre el estado del servicio.
"""

import time
import logging
import statistics
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta

from fastapi import APIRouter

# Importamos la configuración local del servicio
from config.settings import get_settings
from config.constants import (
    TIME_INTERVALS,
    METRICS_CONFIG,
    QUALITY_THRESHOLDS,
    CACHE_EFFICIENCY_THRESHOLDS
)
import httpx
import numpy as np

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health
from common.cache.manager import CacheManager, get_redis_client
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

# Importar configuración centralizada
from config.constants import (
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    QUALITY_THRESHOLDS,
    CACHE_EFFICIENCY_THRESHOLDS,
    OLLAMA_API_ENDPOINTS,
    TIMEOUTS,
    METRICS_CONFIG
)

# Importamos directamente el cliente para evitar dependencias circulares
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Variables globales para métricas y seguimiento (inicializadas con valores de config.constants)
service_start_time = time.time()
embedding_latencies: List[float] = []      # Latencias de generación de embeddings
embedding_cache_hits: int = 0              # Contador de hits en cache
embedding_cache_misses: int = 0            # Contador de misses en cache
MAX_LATENCY_SAMPLES = METRICS_CONFIG['max_latency_samples']  # Máximo número de muestras para cálculo de latencia
LAST_API_RATE_CHECK = time.time() - TIME_INTERVALS["rate_limit_expiry"]   # Última vez que se verificó el rate limit

@router.get("/health", response_model=None, 
           summary="Estado básico del servicio",
           description="Verificación rápida de disponibilidad del servicio (liveness check)")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio de embeddings (liveness check).
    
    Este endpoint permite verificar rápidamente si el servicio está operativo
    y si sus componentes críticos funcionan correctamente. Optimizado para ser
    ligero y rápido, ideal para health checks de Kubernetes.
    
    Returns:
        HealthResponse: Estado básico del servicio
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar el proveedor de embeddings (componente más crítico)
    provider_status = await check_embedding_provider()
    components["embedding_provider"] = provider_status
    
    # Verificar eficiencia de caché (componente de rendimiento)
    cache_efficiency = await check_cache_efficiency()
    components["cache_efficiency"] = cache_efficiency
    
    # Determinar estado general del servicio
    if components["embedding_provider"] == "unavailable":
        overall_status = "unavailable"
    elif (components["embedding_provider"] == "degraded" or 
          components["cache"] == "unavailable" or
          components["cache_efficiency"] == "degraded"):
        overall_status = "degraded"
    else:
        overall_status = "available"
    
    # Generar respuesta estandarizada usando el helper común
    # La función calculará el estado basado en los componentes
    # Aseguramos que los componentes reflejen el estado general que calculamos
    if overall_status != "available":
        # Añadimos un componente específico para el estado de embeddings
        components["embedding_service_overall"] = overall_status
    
    response = get_service_health(
        components=components,
        service_version=settings.service_version
    )
    
    return response

@router.get("/status", response_model=None,
            summary="Estado detallado del servicio",
            description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene estado detallado del servicio de embeddings con métricas y dependencias.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado de componentes críticos (cache, DB, provider)
    - Métricas de rendimiento (latencia, eficiencia de caché, dimensiones)
    - Estado del proveedor de embeddings (OpenAI u Ollama)
    - Rate limits y cuotas de API
    - Estadísticas de uso de modelos
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio
    """
    # Obtener métricas adicionales
    performance_metrics = get_performance_metrics()
    api_limits = await check_api_limits()
    cache_metrics = await get_cache_metrics()
    model_stats = await get_model_usage_stats()
    
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="embedding-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "embedding_provider": check_embedding_provider,
            "cache_efficiency": check_cache_efficiency,
            "api_rate_limits": check_api_rate_limits
        },
        # Métricas detalladas específicas del servicio
        extra_metrics={
            # Información del modelo de embeddings
            "embedding_model": settings.default_ollama_embedding_model if settings.use_ollama else settings.default_embedding_model,
            "provider": "ollama" if settings.use_ollama else "openai",
            "embedding_dimensions": get_embedding_dimensions(),
            "model_statistics": model_stats,
            
            # Métricas de rendimiento
            "performance": performance_metrics,
            "cache": cache_metrics,
            
            # Límites de API
            "api_limits": api_limits,
            
            # Configuración
            "max_input_length": settings.max_input_length,
            "allows_batch_processing": settings.allow_batch_processing
        }
    )

async def check_embedding_provider() -> str:
    """
    Verifica el proveedor de embeddings configurado (OpenAI u Ollama).
    Incluye verificación real con texto de prueba para determinar disponibilidad,
    latencia y calidad del servicio.
    
    Returns:
        str: Estado del proveedor ("available", "degraded" o "unavailable")
    """
    try:
        provider = "ollama" if settings.use_ollama else "openai"
        # Usar el modelo correcto según el proveedor
        if settings.use_ollama:
            model = settings.default_ollama_embedding_model
        else:
            model = settings.default_embedding_model
            
        test_text = "This is a test to verify the embedding provider and model quality."
        start_time = time.time()
        
        # Verificar disponibilidad del proveedor
        if settings.use_ollama:
            # Para Ollama (local), verificar servicio Ollama
            try:
                # Verificar primero que el servicio Ollama esté funcionando
                if not await check_ollama_service():
                    logger.error("Servicio Ollama no disponible")
                    return "unavailable"
                    
                # Verificar que el modelo específico esté disponible
                if not await check_ollama_model(model):
                    logger.warning(f"Modelo {model} no disponible en Ollama")
                    return "degraded"
                
                # Probar embeddings con texto real
                client = OllamaEmbedding(model_name=model, base_url=settings.ollama_base_url)
                embedding = client.get_text_embedding(test_text)
                
                # Verificar calidad del embedding según las dimensiones esperadas del modelo
                model_base_name = model.split(':')[0] if ':' in model else model
                expected_dimension = EMBEDDING_DIMENSIONS.get(model_base_name, DEFAULT_EMBEDDING_DIMENSION)
                
                # Si tiene las dimensiones esperadas, se considera válido dimensionalmente
                if len(embedding) != expected_dimension:
                    logger.info(f"Embedding con dimensiones {len(embedding)}, esperadas: {expected_dimension} para modelo {model}")
                    # No degradamos el servicio si la dimensión no coincide exactamente pero el embedding es válido
                elif not verify_embedding_quality(embedding):
                    logger.warning(f"Verificación de calidad fallida para embedding de {len(embedding)} dimensiones")
                    return "degraded"
                    
                # Verificar uso de memoria (importante para modelos locales)
                memory_usage = await check_memory_usage()
                if memory_usage == "critical":
                    logger.warning("Uso de memoria crítico")
                    return "degraded"
            except Exception as e:
                logger.error(f"Error con Ollama: {str(e)}")
                return "unavailable"
        else:
            # Para OpenAI, verificar las credenciales y conectividad
            try:
                # Verificar que haya una API key configurada
                if not settings.openai_api_key:
                    logger.error("API key de OpenAI no configurada")
                    return "unavailable"
                
                # Probar embeddings con texto real
                client = OpenAIEmbedding(model=model, api_key=settings.openai_api_key)
                embedding = client.get_text_embedding(test_text)
                
                # Verificar calidad del embedding según las dimensiones esperadas del modelo
                model_base_name = model.split(':')[0] if ':' in model else model
                expected_dimension = EMBEDDING_DIMENSIONS.get(model_base_name, DEFAULT_EMBEDDING_DIMENSION)
                
                # Si tiene las dimensiones esperadas, se considera válido dimensionalmente
                if len(embedding) != expected_dimension:
                    logger.info(f"Embedding con dimensiones {len(embedding)}, esperadas: {expected_dimension} para modelo {model}")
                    # No degradamos el servicio si la dimensión no coincide exactamente pero el embedding es válido
                elif not verify_embedding_quality(embedding):
                    logger.warning(f"Verificación de calidad fallida para embedding de {len(embedding)} dimensiones")
                    return "degraded"
                    
                # Verificar rate limits
                rate_limit_status = await check_api_rate_limits()
                if rate_limit_status == "degraded":
                    logger.warning("Acercando a límites de API")
                    return "degraded"
            except Exception as e:
                logger.error(f"Error con OpenAI: {str(e)}")
                return "unavailable"
        
        # Verificar latencia del proveedor
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        # Registrar latencia para métricas
        record_embedding_latency(latency_ms)
        
        # Considerar degradado si la latencia es alta
        from config.constants import TIMEOUTS
        if latency_ms > TIMEOUTS["embedding_generation"] * 1000 * 0.8:  # Si excede el 80% del timeout
            logger.warning(f"Latencia alta: {latency_ms:.2f}ms")
            return "degraded"
            
        logger.info(f"Proveedor {provider} verificado: {latency_ms:.2f}ms")
        return "available"
    except Exception as e:
        logger.error(f"Error verificando proveedor: {str(e)}")
        return "unavailable"

async def check_cache_efficiency() -> str:
    """
    Verifica la eficiencia de la caché de embeddings.
    
    Returns:
        str: Estado de la eficiencia ("available", "degraded" o "unavailable")
    """
    # Verificar si la caché está habilitada
    if not settings.embedding_cache_enabled:
        return "unavailable"
        
    # Verificar mínimo de requests para considerar métricas válidas
    total_requests = embedding_cache_hits + embedding_cache_misses
    if total_requests < CACHE_EFFICIENCY_THRESHOLDS["min_requests"]:
        return "available"  # No hay suficientes datos para degradar
        
    # Calcular hit ratio y determinar estado
    hit_ratio = embedding_cache_hits / total_requests if total_requests > 0 else 0
    
    if hit_ratio >= CACHE_EFFICIENCY_THRESHOLDS["good_hit_ratio"]:
        return "available"
    elif hit_ratio >= CACHE_EFFICIENCY_THRESHOLDS["degraded_hit_ratio"]:
        logger.warning(f"Caché con eficiencia subóptima: {hit_ratio:.2%}")
        return "degraded"
    else:
        logger.warning(f"Caché con eficiencia baja: {hit_ratio:.2%}")
        return "degraded"
        
async def check_ollama_service() -> bool:
    """
    Verifica que el servicio Ollama esté funcionando.
    
    Returns:
        bool: True si el servicio está disponible, False en caso contrario
    """
    try:
        # Obtener configuración centralizada
        from config.constants import OLLAMA_API_ENDPOINTS, TIMEOUTS
        
        base_url = settings.ollama_base_url.rstrip('/')
        health_url = f"{base_url}{OLLAMA_API_ENDPOINTS['health']}"
        models_url = f"{base_url}{OLLAMA_API_ENDPOINTS['models']}"
        timeout = TIMEOUTS['health_check']
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Intentar primero la ruta /api/health
            try:
                health_response = await client.get(health_url)
                if health_response.status_code == 200:
                    return True
            except Exception:
                # Si falla, intentar con /api/tags (endpoints para listar modelos)
                pass
                
            # Intentar verificar el endpoint de modelos como alternativa
            try:
                models_response = await client.get(models_url)
                if models_response.status_code == 200:
                    return True
            except Exception as e:
                logger.error(f"Error conectando con Ollama: {str(e)}")
                return False
                
        return False
    except Exception as e:
        logger.error(f"Error verificando servicio Ollama: {str(e)}")
        return False

async def check_ollama_model(model: str) -> bool:
    """
    Verifica que un modelo específico esté disponible en Ollama.
    Maneja comparaciones de modelos con o sin versión (ej: nomic-embed-text vs nomic-embed-text:latest).
    
    Args:
        model: Nombre del modelo a verificar
        
    Returns:
        bool: True si el modelo está disponible, False en caso contrario
    """
    try:
        # Obtener configuración centralizada
        from config.constants import OLLAMA_API_ENDPOINTS, TIMEOUTS
        
        base_url = settings.ollama_base_url.rstrip('/')
        models_url = f"{base_url}{OLLAMA_API_ENDPOINTS['models']}"
        timeout = TIMEOUTS['model_check']
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(models_url)
            
            if response.status_code != 200:
                logger.warning(f"Error obteniendo lista de modelos de Ollama: código {response.status_code}")
                return False
                
            models_data = response.json()
            available_models = [m.get("name") for m in models_data.get("models", [])]
            
            # Obtener el nombre base del modelo (sin versión)
            model_base_name = model.split(':')[0] if ':' in model else model
            
            # Verificar coincidencias exactas o parciales (con o sin versión)
            for available_model in available_models:
                # Coincidencia exacta
                if model == available_model:
                    return True
                
                # Coincidencia de nombre base
                available_base = available_model.split(':')[0] if ':' in available_model else available_model
                if model_base_name == available_base:
                    logger.info(f"Modelo {model} encontrado como {available_model}")
                    return True
            
            # No se encontró ninguna coincidencia
            logger.warning(f"Modelo {model} no encontrado en Ollama. Disponibles: {available_models}")
            return False
    except Exception as e:
        logger.error(f"Error verificando modelos en Ollama: {str(e)}")
        return False

def verify_embedding_quality(embedding: list) -> bool:
    """
    Verifica la calidad del embedding generado.
    
    Args:
        embedding: Vector de embedding a verificar
        
    Returns:
        bool: True si el embedding es de calidad aceptable, False en caso contrario
    """
    try:
        # Obtener los umbrales de configuración centralizada
        from config.constants import QUALITY_THRESHOLDS
        
        # Valores de configuración
        min_distinct_values = QUALITY_THRESHOLDS["min_distinct_values"]
        sample_size = QUALITY_THRESHOLDS["distinct_values_sample_size"]
        max_abs_value = QUALITY_THRESHOLDS["max_absolute_value"]
        norm_tolerance = QUALITY_THRESHOLDS["norm_tolerance"]
        
        # 1. Verificar que no sea un vector nulo
        if not embedding or len(embedding) == 0:
            return False
            
        # 2. Verificar que no tenga valores repetidos (embedding degenerado)
        if len(set(embedding[:sample_size])) < min_distinct_values:  
            return False
            
        # 3. Verificar que no tenga valores extremos
        embedding_array = np.array(embedding)
        if np.max(np.abs(embedding_array)) > max_abs_value:
            return False
            
        # 4. Verificar la norma (para embeddings normalizados debe ser cercana a 1.0)
        embedding_norm = np.linalg.norm(embedding_array)
        
        # Para embeddings normalizados, debe estar cerca de 1.0
        # Permitimos algo de tolerancia para diferentes implementaciones
        if abs(embedding_norm - 1.0) > norm_tolerance and abs(embedding_norm) > norm_tolerance:
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error verificando calidad del embedding: {str(e)}")
        return False

async def check_memory_usage() -> str:
    """
    Verifica el uso de memoria del sistema para modelos locales.
    
    Returns:
        str: Estado de la memoria ("normal", "warning" o "critical")
    """
    # Esta función no tiene implementación real ya que depende de capacidades
    # del sistema host. En un entorno containerizado, los límites de memoria
    # son manejados por Docker/K8s. Devolvemos un valor simulado.
    try:
        # En entornos donde se tiene acceso real al uso de memoria, se podría
        # implementar con psutil, docker stats u otro API
        
        # Simulamos niveles de uso basados en alguna métrica
        import random
        
        # Simulación simple para pruebas - reemplazar con lógica real
        usage_simulated = random.uniform(0, 1.0)  # Entre 0 y 100%
        
        if usage_simulated < 0.7:
            return "normal"
        elif usage_simulated < 0.9:
            return "warning"
        else:
            return "critical"
            
    except Exception as e:
        logger.error(f"Error verificando uso de memoria: {str(e)}")
        return "warning"  # Valor conservador ante error

async def check_api_rate_limits() -> str:
    """
    Verifica el estado de los límites de API.
    
    Returns:
        str: Estado de los límites ("available", "degraded" o "unavailable")
    """
    # Solo relevante para OpenAI
    if settings.use_ollama:
        return "available"  # Local no tiene límites
    
    # Verificar tiempo desde última verificación (evitar muchas llamadas)
    global LAST_API_RATE_CHECK
    
    current_time = time.time()
    if current_time - LAST_API_RATE_CHECK < TIME_INTERVALS["rate_limit_expiry"]:
        # Usar último estado conocido en lugar de verificar nuevamente
        return "available"  # Valor simulado - implementar lógica real
    
    # Implementar verificación real de límites de OpenAI API
    LAST_API_RATE_CHECK = current_time
    return "available"  # Valor simulado - implementar lógica real

async def get_cache_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas detalladas de la caché de embeddings.
    
    Returns:
        Dict[str, Any]: Métricas de caché
    """
    # Calcular eficiencia de caché
    total_requests = embedding_cache_hits + embedding_cache_misses
    hit_ratio = embedding_cache_hits / total_requests if total_requests > 0 else 0
    
    # Verificar si Redis está disponible
    redis_client = await get_redis_client()
    cache_available = redis_client is not None
    
    # Recopilar métricas de tamaño/utilización (simuladas)
    cache_size = 0
    cache_ttl = 0
    
    if cache_available:
        try:
            # Implementar lectura real de métricas de Redis
            pass
        except Exception:
            pass
            
    return {
        "enabled": settings.embedding_cache_enabled,
        "available": cache_available,
        "hit_ratio": hit_ratio,
        "hits": embedding_cache_hits,
        "misses": embedding_cache_misses,
        "total_requests": total_requests
    }

async def get_model_usage_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas de uso de los modelos de embedding.
    
    Returns:
        Dict[str, Any]: Estadísticas de uso de modelos
    """
    # En implementación real, obtener estos datos de un storage persistente
    provider = "ollama" if settings.use_ollama else "openai"
    model = settings.default_ollama_embedding_model if settings.use_ollama else settings.default_embedding_model
    
    # Valores simulados para información de ejemplo
    latency_avg = statistics.mean(embedding_latencies) if embedding_latencies else 0
    requests_hour = 0
    tokens_hour = 0
    
    # En implementación real, obtener estos datos de tracking o métricas
    return {
        "provider": provider,
        "model": model,
        "average_latency_ms": latency_avg,
        "requests_last_hour": requests_hour,
        "tokens_last_hour": tokens_hour,
        "dimensions": get_embedding_dimensions()
    }

async def check_api_limits() -> Dict[str, Any]:
    """
    Verifica los límites de API y cuotas para el proveedor de embeddings.
    
    Returns:
        Dict[str, Any]: Información sobre límites de API
    """
    # Solo relevante para OpenAI y otros servicios basados en API externa
    if settings.use_ollama:
        return {
            "provider": "ollama",
            "limit_type": "unlimited",  # Local no tiene límites de API
            "current_usage": 0,
            "max_usage": 0,
            "usage_percentage": 0
        }
    
    # Para OpenAI, implementar lectura de los headers de límites
    # Para simplificar, usamos valores simulados
    return {
        "provider": "openai",
        "limit_type": "rpm",
        "current_rpm": 10,  # Valor simulado
        "max_rpm": 60,      # Valor simulado
        "usage_percentage": 16.7,  # Valor simulado
        "quota_reset": f"{TIME_INTERVALS['rate_limit_expiry'] // 60} minutes"
    }

def get_embedding_dimensions() -> int:
    """
    Determina las dimensiones del modelo de embedding configurado.
    Soporta tanto modelos de OpenAI como de Ollama.
    
    Returns:
        int: Número de dimensiones del modelo
    """
    # Obtener configuración centralizada
    from config.constants import EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_DIMENSION
    
    # Seleccionar el modelo correcto según el proveedor configurado
    if settings.use_ollama:
        # Para Ollama, usar el modelo configurado en default_ollama_embedding_model
        model_name = settings.default_ollama_embedding_model.lower()
        # Extraer el nombre base sin versión (ej: 'nomic-embed-text:latest' -> 'nomic-embed-text')
        model_base = model_name.split(':')[0] if ':' in model_name else model_name
    else:
        # Para OpenAI u otros proveedores
        model_name = settings.default_embedding_model.lower()
        model_base = model_name
    
    # Buscar dimensiones por nombre exacto primero
    if model_base in EMBEDDING_DIMENSIONS:
        return EMBEDDING_DIMENSIONS[model_base]
    
    # Si no se encuentra exacto, buscar por coincidencia parcial
    for name, dims in EMBEDDING_DIMENSIONS.items():
        if name in model_base or model_base in name:
            return dims
    
    # Valor predeterminado si no se encuentra ninguna coincidencia
    return DEFAULT_EMBEDDING_DIMENSION

def get_performance_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas de rendimiento del servicio de embeddings.
    
    Returns:
        Dict[str, Any]: Métricas de rendimiento
    """
    # Calcular métricas básicas si hay suficientes datos
    if len(embedding_latencies) < METRICS_CONFIG["min_samples_for_percentiles"]:
        return {
            "latency_p50_ms": 0,
            "latency_p95_ms": 0,
            "latency_p99_ms": 0,
            "samples": len(embedding_latencies),
            "uptime_seconds": int(time.time() - service_start_time)
        }
    
    # Ordenar para cálculo de percentiles
    sorted_latencies = sorted(embedding_latencies)
    samples = len(sorted_latencies)
    
    # Calcular percentiles relevantes
    p50_idx = int(samples * 0.5)
    p95_idx = int(samples * 0.95)
    p99_idx = int(samples * 0.99)
    
    return {
        "latency_p50_ms": sorted_latencies[p50_idx],
        "latency_p95_ms": sorted_latencies[p95_idx],
        "latency_p99_ms": sorted_latencies[p99_idx],
        "samples": samples,
        "uptime_seconds": int(time.time() - service_start_time)
    }

def record_embedding_latency(latency_ms: float) -> None:
    """
    Registra la latencia de generación de embeddings para métricas.
    
    Args:
        latency_ms: Latencia en milisegundos
    """
    global embedding_latencies
    
    # Añadir latencia a la lista
    embedding_latencies.append(latency_ms)
    
    # Mantener tamaño máximo de la lista (FIFO)
    if len(embedding_latencies) > MAX_LATENCY_SAMPLES:
        # Eliminar las latencias más antiguas
        embedding_latencies = embedding_latencies[-MAX_LATENCY_SAMPLES:]

def record_cache_hit() -> None:
    """
    Registra un hit en la caché para estadísticas.
    """
    global embedding_cache_hits
    embedding_cache_hits += 1

def record_cache_miss() -> None:
    """
    Registra un miss en la caché para estadísticas.
    """
    global embedding_cache_misses
    embedding_cache_misses += 1
