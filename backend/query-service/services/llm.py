"""
Funciones para interactuar con modelos de lenguaje (LLMs).
"""

import logging
from typing import Optional, Any, Dict

from llama_index.llms.openai import OpenAI

from common.models import TenantInfo
from common.auth import validate_model_access
from common.llm.ollama import get_llm_model
from common.context import with_context, Context
from common.errors import handle_errors, ErrorCode

# Importar módulos de proveedores LLM
from common.llm.groq import GroqLLM

# Importar configuración centralizada del servicio
from config.settings import get_settings
from config.constants import (
    LLM_DEFAULT_TEMPERATURE,
    LLM_MAX_TOKENS,
    TIMEOUTS,
    DEFAULT_LLM_MODEL,
    DEFAULT_EMBEDDING_MODEL
)

logger = logging.getLogger(__name__)

@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def get_llm_for_tenant(tenant_info: TenantInfo, requested_model: Optional[str] = None, ctx: Context = None) -> Any:
    """
    Obtiene un modelo LLM apropiado para un tenant según su nivel de suscripción.
    
    Args:
        tenant_info: Información del tenant
        requested_model: Modelo solicitado (opcional)
        ctx: Contexto de la solicitud (proporcionado por el decorador with_context)
        
    Returns:
        Modelo LLM configurado compatible con LlamaIndex
    """
    settings = get_settings()
    
    # Determinar modelo basado en tier del tenant y solicitud
    model_name = await validate_model_access(
        tenant_info, 
        requested_model or DEFAULT_LLM_MODEL,
        model_type="llm",
        tenant_id=tenant_info.tenant_id
    )
    
    # Configuración común a todos los modelos
    common_params = {
        "temperature": settings.llm_temperature if hasattr(settings, 'llm_temperature') else LLM_DEFAULT_TEMPERATURE,
        "max_tokens": settings.llm_max_tokens if hasattr(settings, 'llm_max_tokens') else LLM_MAX_TOKENS
    }
    
    # Detectar y configurar el proveedor LLM correcto (Ollama, Groq u OpenAI)
    if hasattr(settings, 'use_ollama') and settings.use_ollama:
        # Usar Ollama (get_llm_model devuelve un modelo compatible con LlamaIndex)
        logger.info(f"Usando modelo Ollama: {model_name}")
        return get_llm_model(model_name, **common_params)
    elif hasattr(settings, 'use_groq') and settings.use_groq:
        # Usar Groq
        logger.info(f"Usando modelo Groq: {model_name}")
        # Verificar que tenemos la API key configurada
        if not hasattr(settings, 'groq_api_key') or not settings.groq_api_key:
            logger.error("API key de Groq no configurada")
            raise ValueError("Se requiere API key de Groq para usar modelos de Groq")
            
        # Crear cliente Groq usando el wrapper compatible con LlamaIndex
        return GroqLLM(
            model=model_name,
            api_key=settings.groq_api_key,
            **common_params
        )
    else:
        # Usar OpenAI (default fallback)
        logger.info(f"Usando modelo OpenAI: {model_name}")
        return OpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            **common_params
        )

@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="detailed", log_traceback=True)
async def generate_embedding_via_service(text: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Genera un embedding para un texto a través del servicio de embeddings.
    
    Args:
        text: Texto para generar embedding
        ctx: Contexto de la solicitud (proporcionado por el decorador with_context)
        
    Returns:
        Dict: Respuesta del servicio de embeddings con vector y metadatos
    """
    from common.utils.http import call_service
    from common.errors import (
        EmbeddingGenerationError, EmbeddingModelError, 
        TextTooLargeError, ServiceError, ErrorCode
    )
    
    settings = get_settings()
    
    # Obtener valores del contexto usando el patrón recomendado
    tenant_id = ctx.get_tenant_id() if ctx else None
    agent_id = ctx.get_agent_id() if ctx else None
    conversation_id = ctx.get_conversation_id() if ctx else None
    
    if not tenant_id:
        raise ErrorCode(
            message="Se requiere tenant_id para generar embeddings",
            error_code="MISSING_TENANT_ID",
            status_code=400
        )
    
    try:
        # Preparar solicitud al servicio de embeddings
        payload = {
            "model": DEFAULT_EMBEDDING_MODEL,
            "texts": [text],
            "tenant_id": tenant_id
        }
        
        # Realizar solicitud con contexto propagado y formato estandarizado
        # Utilizamos el cache_ttl recomendado para embeddings según el patrón establecido (24 horas)
        response = await call_service(
            url=f"{settings.embedding_service_url}/internal/embed",
            data=payload,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            operation_type="embedding",
            use_cache=True,  # Aprovechar caché para embeddings repetidos
            cache_ttl=86400  # 24 horas según recomendación para embeddings
        )
        
        # Verificar éxito y extraer datos según el formato estandarizado
        if not response.get("success", False):
            error_info = response.get("error", {})
            error_msg = response.get("message", "Error desconocido generando embedding")
            error_code = error_info.get("details", {}).get("error_code", ErrorCode.EMBEDDING_GENERATION_ERROR)
            error_details = error_info.get("details", {})
            
            logger.error(f"Error en servicio de embeddings: {error_msg} (código: {error_code})")
            
            # Crear error específico según el código de error recibido
            if error_code == ErrorCode.TEXT_TOO_LARGE:
                raise TextTooLargeError(
                    message=f"Texto demasiado grande para generar embedding: {error_msg}",
                    details=error_details
                )
            elif error_code == ErrorCode.EMBEDDING_MODEL_ERROR:
                raise EmbeddingModelError(
                    message=f"Error con el modelo de embedding: {error_msg}",
                    details=error_details
                )
            elif error_code == ErrorCode.EMBEDDING_GENERATION_ERROR:
                raise EmbeddingGenerationError(
                    message=f"Error generando embedding: {error_msg}",
                    details=error_details
                )
        
        # Extraer embeddings de la respuesta y verificar formato
        embedding_data = response.get("data", None)
        if not embedding_data:
            raise EmbeddingGenerationError(
                message="No se recibieron embeddings del servicio",
                details={"tenant_id": tenant_id, "response": response}
            )
        
        # Los embeddings ahora vienen directamente en data y no en data.embeddings
        embeddings = embedding_data
        
        # Retornar el primer embedding (si existe)
        if embeddings and len(embeddings) > 0:
            return {
                "embedding": embeddings[0],
                "model": response.get("metadata", {}).get("model_used", DEFAULT_EMBEDDING_MODEL)
            }
        else:
            # Si no hay embeddings, lanzar un error específico
            raise EmbeddingGenerationError(
                message="No se generó ningún embedding",
                details={"text_length": len(text) if text else 0}
            )
    except ServiceError:
        # Reenviar errores específicos ya creados
        raise
    except Exception as e:
        logger.error(f"Error generando embedding: {str(e)}")
        # Convertir otros errores en EmbeddingGenerationError
        raise EmbeddingGenerationError(
            message=f"Error inesperado generando embedding: {str(e)}",
            details={"error_type": e.__class__.__name__}
        )