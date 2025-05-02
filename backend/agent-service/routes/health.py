"""
Endpoints para verificación de salud y estado del servicio de agentes.

Este módulo implementa los endpoints estandarizados /health y /status
siguiendo el patrón unificado de la plataforma. El endpoint /health
proporciona una verificación rápida de disponibilidad, mientras que
/status ofrece información detallada sobre el estado del servicio.
"""

import time
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter

from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.config import get_settings
from common.utils.http import check_service_health
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health

from main import http_client

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Variables globales para métricas y seguimiento
service_start_time = time.time()

# Métricas para monitoreo de rendimiento y disponibilidad
llm_latency_ms = []            # Latencia del LLM en milisegundos
llm_error_count = 0           # Contador de errores del LLM
service_call_counts = {       # Contadores de llamadas a servicios
    "query_service": 0,
    "embedding_service": 0,
    "llm_service": 0
}
tool_usage_counts = {}        # Contador de uso de herramientas
MAX_METRIC_SAMPLES = 1000     # Máximo número de muestras a guardar

@router.get("/health", 
           response_model=None,
           summary="Estado básico del servicio",
           description="Verificación rápida de disponibilidad del servicio (liveness check)")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio de agentes (liveness check).
    
    Este endpoint permite verificar rápidamente si el servicio está operativo
    y si sus componentes críticos funcionan correctamente. Incluye verificaciones
    de servicios dependientes (query, embedding), disponibilidad del LLM
    y herramientas configuradas.
    
    Returns:
        HealthResponse: Estado básico del servicio
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar servicios dependientes (específicos del servicio de agentes)
    query_service_status = await check_query_service()
    embedding_service_status = await check_embedding_service()
    llm_service_status = await check_llm_service()
    tools_status = check_tools_availability()
    
    # Actualizar componentes con resultados de verificaciones
    components["query_service"] = query_service_status
    components["embedding_service"] = embedding_service_status
    components["llm_service"] = llm_service_status
    components["tools"] = tools_status
    
    # Generar respuesta estandarizada usando el helper común
    return get_service_health(
        components=components,
        service_version=settings.service_version
    )

@router.get("/status", 
            response_model=None,
            summary="Estado detallado del servicio",
            description="Información completa sobre el estado del servicio, incluyendo métricas y dependencias")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """
    Obtiene estado detallado del servicio de agentes con métricas y dependencias.
    
    Este endpoint proporciona información completa para observabilidad, incluyendo:
    - Tiempo de actividad del servicio
    - Estado detallado de componentes críticos (cache, DB, LLM)
    - Estado de servicios dependientes con métricas
    - Información sobre modelos y herramientas disponibles
    - Estadísticas de uso y rendimiento
    - Configuraciones y capacidades del servicio
    
    Returns:
        ServiceStatusResponse: Estado detallado del servicio con métricas completas
    """
    # Obtener métricas detalladas sobre el LLM
    llm_metrics = get_llm_metrics()
    tool_usage = get_tool_usage_metrics()
    dependency_metrics = get_dependency_metrics()
    
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="agent-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "query_service": check_query_service,
            "embedding_service": check_embedding_service,
            "llm_service": check_llm_service,
            "tools": check_tools_availability
        },
        # Métricas detalladas específicas del servicio
        extra_metrics={
            # Configuración de LLM
            "llm": {
                "provider": settings.llm_provider,
                "default_model": settings.default_llm_model,
                "available_models": settings.available_llm_models if hasattr(settings, "available_llm_models") else [settings.default_llm_model],
                "metrics": llm_metrics
            },
            
            # Herramientas
            "tools": {
                "enabled": settings.enabled_tools if hasattr(settings, "enabled_tools") else ["search", "calculator", "rag"],
                "usage_stats": tool_usage
            },
            
            # Límites y cuotas
            "limits": {
                "max_agents_per_tenant": settings.max_agents_per_tenant,
                "max_tokens_per_request": settings.max_tokens_per_request if hasattr(settings, "max_tokens_per_request") else 4096,
                "max_parallel_requests": settings.max_parallel_requests if hasattr(settings, "max_parallel_requests") else 10
            },
            
            # Métricas de servicios dependientes
            "dependencies": dependency_metrics
        }
    )

async def check_query_service() -> str:
    """
    Verifica el estado del servicio de consulta.
    Incluye verificación detallada si el servicio está disponible pero degradado.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        global service_call_counts
        service_call_counts["query_service"] += 1
        
        if not http_client:
            return "unknown"
            
        # Verificación básica
        response = await http_client.get(
            f"{settings.query_service_url}/health", 
            timeout=3.0
        )
        
        if response.status_code != 200:
            logger.warning(f"Health check de query_service falló con código {response.status_code}")
            return "degraded"
            
        # Verificar estado detallado
        try:
            status_response = await http_client.get(
                f"{settings.query_service_url}/status",
                timeout=3.0
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                # Verificar componentes críticos del query-service
                components = status_data.get("components", {})
                
                # Si alguno de los componentes críticos está degradado, el servicio está degradado
                for key in ["embedding_service", "vector_store"]:
                    if components.get(key) == "degraded":
                        logger.info(f"Componente {key} del query-service está degradado")
                        return "degraded"
                        
                # Si algún componente crítico no está disponible, el servicio está degradado
                for key in ["embedding_service", "vector_store"]:
                    if components.get(key) == "unavailable":
                        logger.warning(f"Componente {key} del query-service no está disponible")
                        return "degraded"
        except Exception as status_error:
            logger.info(f"No se pudo obtener estado detallado de query-service: {status_error}")
            # El servicio está disponible pero no pudimos verificar estado detallado
        
        return "available"
    except Exception as e:
        logger.warning(f"Servicio de consulta no disponible: {str(e)}")
        return "unavailable"

async def check_embedding_service() -> str:
    """
    Verifica el estado del servicio de embeddings.
    Incluye verificación detallada si el servicio está disponible pero degradado.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        global service_call_counts
        service_call_counts["embedding_service"] += 1
        
        if not http_client:
            return "unknown"
            
        # Verificación básica
        response = await http_client.get(
            f"{settings.embedding_service_url}/health", 
            timeout=3.0
        )
        
        if response.status_code != 200:
            logger.warning(f"Health check de embedding_service falló con código {response.status_code}")
            return "degraded"
            
        # Verificar estado detallado
        try:
            status_response = await http_client.get(
                f"{settings.embedding_service_url}/status",
                timeout=3.0
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                # Verificar el estado del proveedor de embeddings
                components = status_data.get("components", {})
                if components.get("embedding_provider") == "degraded":
                    logger.info("Proveedor de embeddings en estado degradado")
                    return "degraded"
                    
                # Verificar métricas de latencia si están disponibles
                metrics = status_data.get("metrics", {})
                if "latency_ms" in metrics and metrics["latency_ms"] > 5000:
                    logger.warning(f"Latencia alta en embedding-service: {metrics['latency_ms']}ms")
                    return "degraded"
        except Exception as status_error:
            logger.info(f"No se pudo obtener estado detallado de embedding-service: {status_error}")
            # El servicio está disponible pero no pudimos verificar estado detallado
        
        return "available"
    except Exception as e:
        logger.warning(f"Servicio de embeddings no disponible: {str(e)}")
        return "unavailable"

async def check_llm_service() -> str:
    """
    Verifica el estado del servicio LLM.
    Esta función comprueba la disponibilidad del proveedor LLM configurado.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        global service_call_counts, llm_error_count
        service_call_counts["llm_service"] += 1
        
        # Obtener el cliente LLM (simulado para el ejemplo)
        llm_provider = settings.llm_provider
        llm_model = settings.default_llm_model
        
        if not llm_provider or not llm_model:
            logger.warning("Configuración LLM incompleta")
            return "unavailable"
            
        # Verificar disponibilidad con una llamada simple
        # En una implementación real, esto haría una llamada real a la API
        # y verificaría latencia, errores, etc.
        
        # Simulación de verificación
        llm_ok = True  # Simular estado correcto
        
        if llm_provider == "openai":
            # Aquí iría el código real para verificar OpenAI
            # Por ejemplo, una solicitud simple para verificar las claves de API
            # y disponibilidad del modelo
            pass
        elif llm_provider == "anthropic":
            # Verificación específica para Anthropic
            pass
        elif llm_provider == "azure_openai":
            # Verificación específica para Azure OpenAI
            pass
        elif llm_provider == "ollama":
            # Verificación específica para Ollama local
            pass
        else:
            logger.warning(f"Proveedor LLM desconocido: {llm_provider}")
            return "unknown"
            
        # Registrar latencia simulada para métricas
        global llm_latency_ms
        llm_latency_ms.append(500)  # Valor simulado de 500ms
        
        # Mantener solo las últimas muestras
        if len(llm_latency_ms) > MAX_METRIC_SAMPLES:
            llm_latency_ms = llm_latency_ms[-MAX_METRIC_SAMPLES:]
            
        # Determinar estado basado en latencia promedio
        avg_latency = sum(llm_latency_ms) / len(llm_latency_ms) if llm_latency_ms else 0
        if avg_latency > 5000:  # Si latencia promedio > 5 segundos
            logger.warning(f"Latencia alta en LLM: {avg_latency}ms")
            return "degraded"
            
        return "available" if llm_ok else "degraded"
    except Exception as e:
        logger.warning(f"Error verificando servicio LLM: {str(e)}")
        llm_error_count += 1
        return "unavailable"

def check_tools_availability() -> str:
    """
    Verifica la disponibilidad de las herramientas configuradas.
    
    Returns:
        str: Estado de las herramientas ("available", "degraded" o "unavailable")
    """
    try:
        # Obtener lista de herramientas configuradas
        configured_tools = settings.enabled_tools if hasattr(settings, "enabled_tools") else ["search", "rag"]
        required_tools = ["search", "rag"]  # Herramientas críticas
        
        # Verificar herramientas críticas
        missing_tools = [tool for tool in required_tools if tool not in configured_tools]
        
        if missing_tools:
            logger.warning(f"Faltan herramientas críticas: {missing_tools}")
            return "degraded"
            
        # Verificar herramientas adicionales
        # Aquí iría la lógica específica para verificar cada herramienta
        # Por ejemplo, verificar que el intérprete de código esté disponible
        
        return "available"
    except Exception as e:
        logger.warning(f"Error verificando herramientas: {str(e)}")
        return "degraded"  # Las herramientas no son críticas para la disponibilidad básica


def get_llm_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas detalladas sobre el rendimiento del LLM.
    
    Returns:
        Dict[str, Any]: Métricas detalladas del LLM
    """
    global llm_latency_ms, llm_error_count, service_call_counts
    
    # Calcular métricas básicas
    avg_latency = sum(llm_latency_ms) / len(llm_latency_ms) if llm_latency_ms else 0
    calls_count = service_call_counts["llm_service"]
    
    # Calcular percentiles si hay suficientes datos
    p95_latency = 0
    if len(llm_latency_ms) >= 5:
        # Ordenar latencias para cálculo de percentiles
        sorted_latencies = sorted(llm_latency_ms)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[p95_index]
    
    return {
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "error_count": llm_error_count,
        "error_rate": round((llm_error_count / calls_count) * 100, 2) if calls_count > 0 else 0,
        "total_calls": calls_count,
        "samples_count": len(llm_latency_ms),
        "status": "degraded" if avg_latency > 5000 else "healthy"
    }


def get_tool_usage_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas sobre el uso de herramientas por los agentes.
    
    Returns:
        Dict[str, Any]: Estadísticas de uso de herramientas
    """
    global tool_usage_counts
    
    # En una implementación real, estas estadísticas vendrían de
    # contadores persistentes o base de datos
    
    # Si no hay datos reales, proporcionamos valores simulados
    if not tool_usage_counts:
        # Simular datos para el ejemplo
        tool_usage_counts = {
            "search": 120,
            "rag": 250,
            "calculator": 30,
            "code_interpreter": 15
        }
    
    # Calcular total y porcentajes
    total_uses = sum(tool_usage_counts.values())
    
    # Crear métricas para cada herramienta
    tool_metrics = {}
    for tool, count in tool_usage_counts.items():
        percentage = round((count / total_uses) * 100, 2) if total_uses > 0 else 0
        tool_metrics[tool] = {
            "count": count,
            "percentage": percentage
        }
    
    return {
        "most_used": max(tool_usage_counts.items(), key=lambda x: x[1])[0] if tool_usage_counts else "",
        "total_uses": total_uses,
        "tools": tool_metrics
    }


def get_dependency_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas sobre los servicios dependientes.
    
    Returns:
        Dict[str, Any]: Métricas de servicios dependientes
    """
    global service_call_counts
    
    # Obtener llamadas totales a cada servicio
    call_metrics = {}
    for service, count in service_call_counts.items():
        call_metrics[service] = {
            "calls": count,
            "last_status": "available"  # En una implementación real, guardaríamos el último estado
        }
    
    return {
        "calls": call_metrics,
        "total_external_calls": sum(service_call_counts.values()),
    }
