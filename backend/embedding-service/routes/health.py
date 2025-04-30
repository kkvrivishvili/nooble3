"""
Endpoints para verificación de estado del servicio de embeddings.
"""

import logging
import os
from typing import Dict, Any

from fastapi import APIRouter

from common.models import HealthResponse
from common.errors import handle_errors
from common.context import with_context, Context
from common.config import get_settings
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name
from common.cache.manager import CacheManager

from llama_index.embeddings.openai import OpenAIEmbedding

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

@router.get("/health", response_model=None)
@router.get("/status", response_model=None)  # Alias para compatibilidad con agent-service
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """
    Verifica el estado del servicio de embeddings.
    
    Este endpoint permite monitorear el estado operativo del servicio.
    """
    # Verificar sistema de caché unificado
    cache_status = "unavailable"
    try:
        await CacheManager.get(
            data_type="system",
            resource_id="health_check"
        )
        cache_status = "available"
    except Exception as e:
        logger.warning(f"Cache no disponible: {e}")
    
    # Verificar Supabase
    supabase_status = "available"
    try:
        supabase = get_supabase_client()
        supabase.table(get_table_name("tenants")).select("tenant_id").limit(1).execute()
    except Exception as e:
        logger.warning(f"Supabase no disponible: {str(e)}")
        supabase_status = "unavailable"
    
    # Verificar OpenAI
    openai_status = "available"
    try:
        # Solo realizar un test rápido si no estamos usando Ollama
        if not settings.use_ollama:
            embed_model = OpenAIEmbedding(
                model_name=settings.default_embedding_model,
                api_key=settings.openai_api_key
            )
            test_result = embed_model._get_text_embedding("test")
            if not test_result or len(test_result) < 10:
                openai_status = "degraded"
    except Exception as e:
        logger.warning(f"OpenAI no disponible: {str(e)}")
        openai_status = "unavailable"
    
    # Determinar estado general
    components = {
        "cache": cache_status,
        "supabase": supabase_status,
    }
    
    # Añadir estado de OpenAI solo si no estamos usando Ollama
    if not settings.use_ollama:
        components["openai"] = openai_status
    # Añadir estado de Ollama si lo estamos usando
    else:
        # La verificación de Ollama sería más compleja y requeriría un endpoint específico
        components["ollama"] = "available"  # Simplificado para esta implementación
    
    is_healthy = all(s == "available" for s in components.values())
    
    return HealthResponse(
        success=True,  
        status="healthy" if is_healthy else "degraded",
        components=components,
        version=settings.service_version,
        message="Servicio de embeddings operativo" if is_healthy else "Servicio de embeddings con funcionalidad limitada"
    )