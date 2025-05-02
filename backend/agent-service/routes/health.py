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

# Variable global para registrar el inicio del servicio (para cálculo de uptime)
service_start_time = time.time()

@router.get("/health", 
           response_model=None,
           summary="Estado básico del servicio",
           description="Verificación rápida de disponibilidad del servicio (liveness check)")
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado básico del servicio de agentes (liveness check).
    
    Este endpoint permite verificar rápidamente si el servicio está operativo.
    Ideal para health checks de Kubernetes y sistemas de monitoreo.
    """
    # Obtener componentes básicos usando el helper común
    components = await basic_health_check()
    
    # Verificar servicios dependientes (específicos del servicio de agentes)
    query_service_status = await check_query_service()
    embedding_service_status = await check_embedding_service()
    
    components["query_service"] = query_service_status
    components["embedding_service"] = embedding_service_status
    
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
    - Estado de componentes críticos (cache, DB)
    - Estado de servicios dependientes (query-service, embedding-service)
    - Información sobre modelos y herramientas disponibles
    - Versión y entorno de ejecución
    """
    # Usar el helper común con verificaciones específicas del servicio
    return await detailed_status_check(
        service_name="agent-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "query_service": check_query_service,
            "embedding_service": check_embedding_service
        },
        # Métricas adicionales específicas del servicio
        extra_metrics={
            "default_llm_model": settings.default_llm_model,
            "supported_tools": ["search", "calculator", "rag", "code_interpreter"],
            "max_agents_per_tenant": settings.max_agents_per_tenant
        }
    )

async def check_query_service() -> str:
    """
    Verifica el estado del servicio de consulta.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        if not http_client:
            return "unknown"
            
        response = await http_client.get(
            f"{settings.query_service_url}/health", 
            timeout=5.0
        )
        
        if response.status_code == 200:
            return "available"
        else:
            return "degraded"
    except Exception as e:
        logger.warning(f"Servicio de consulta no disponible: {str(e)}")
        return "unavailable"

async def check_embedding_service() -> str:
    """
    Verifica el estado del servicio de embeddings.
    
    Returns:
        str: Estado del servicio ("available", "degraded" o "unavailable")
    """
    try:
        if not http_client:
            return "unknown"
            
        response = await http_client.get(
            f"{settings.embedding_service_url}/health", 
            timeout=5.0
        )
        
        if response.status_code == 200:
            return "available"
        else:
            return "degraded"
    except Exception as e:
        logger.warning(f"Servicio de embeddings no disponible: {str(e)}")
        return "unavailable"
