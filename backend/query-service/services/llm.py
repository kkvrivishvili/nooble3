"""
Funciones para interactuar con modelos de lenguaje (LLMs).
"""

import logging
from typing import Optional, Any, Dict

from common.models import TenantInfo
from common.auth import validate_model_access
from common.context import with_context, Context
from common.errors import handle_errors, ErrorCode

# Importar el proveedor de Groq desde el módulo local
from provider.groq import (
    GroqLLM, 
    GroqError, 
    GroqAuthenticationError, 
    GroqRateLimitError,
    GroqModelNotFoundError
)

# Importar configuración centralizada del servicio
from config.settings import get_settings
from config.constants import (
    LLM_DEFAULT_TEMPERATURE,
    LLM_MAX_TOKENS,
    TIMEOUTS,
    DEFAULT_LLM_MODEL,
    DEFAULT_EMBEDDING_MODEL,
    # Nuevos modelos de Groq
    DEFAULT_GROQ_MODEL,
    DEFAULT_GROQ_LLM_MODEL,
    GROQ_EXTENDED_CONTEXT_MODEL,
    GROQ_FAST_MODEL,
    GROQ_MAVERICK_MODEL,
    GROQ_SCOUT_MODEL
)

# Importar contadores de tokens para estimación de tokens
from utils.token_counters import estimate_model_max_tokens

logger = logging.getLogger(__name__)

@with_context(tenant=True)
@handle_errors(
    error_type="service", 
    log_traceback=True,
    error_map={
        GroqAuthenticationError: (ErrorCode.AUTHORIZATION_ERROR, 401),
        GroqRateLimitError: (ErrorCode.RATE_LIMIT_EXCEEDED, 429),
        GroqModelNotFoundError: (ErrorCode.MODEL_NOT_FOUND_ERROR, 404),
        GroqError: (ErrorCode.EXTERNAL_SERVICE_ERROR, 500)
    }
)
async def get_llm_for_tenant(tenant_info: TenantInfo, requested_model: Optional[str] = None, 
                             context_size: Optional[int] = None, fast_response: bool = False,
                             ctx: Context = None) -> Any:
    """
    Obtiene un modelo LLM apropiado para un tenant según su nivel de suscripción.
    
    Args:
        tenant_info: Información del tenant
        requested_model: Modelo solicitado (opcional)
        context_size: Tamaño de contexto necesario (opcional)
        fast_response: Priorizar velocidad de respuesta sobre calidad
        ctx: Contexto de la solicitud (proporcionado por el decorador with_context)
        
    Returns:
        Modelo LLM configurado compatible con LlamaIndex
    """
    settings = get_settings()
    
    # Si hay un modelo específicamente solicitado, usarlo si el tenant tiene acceso
    if requested_model:
        model_name = await validate_model_access(
            tenant_info, 
            requested_model,
            model_type="llm",
            tenant_id=tenant_info.tenant_id
        )
    else:
        # Seleccionar modelo basado en el tier y requisitos
        tier = tenant_info.tier.lower() if tenant_info.tier else "free"
        
        # Asignar modelos por tier, con modelos más avanzados para tiers superiores
        if tier in ["enterprise", "business"]:
            # Tiers superiores: acceso a Llama 4 y modelos de contexto extendido
            if context_size and context_size > 8192:
                # Para requisitos de contexto extenso, usar modelos Llama 4 o contexto extendido
                if context_size > 32768:
                    model_name = GROQ_EXTENDED_CONTEXT_MODEL  # 128K contexto
                else:
                    model_name = GROQ_MAVERICK_MODEL  # 32K contexto, alto rendimiento
            else:
                # Sin requisitos de contexto extenso
                if fast_response:
                    model_name = GROQ_SCOUT_MODEL  # Balanceado, rápido para empresas
                else:
                    model_name = GROQ_MAVERICK_MODEL  # Máxima calidad para empresas
        
        elif tier == "premium":
            # Tier premium: acceso a modelos Llama 3.1/3.3
            if context_size and context_size > 8192:
                model_name = GROQ_SCOUT_MODEL  # 32K contexto para premium
            else:
                if fast_response:
                    model_name = GROQ_FAST_MODEL  # Modelo rápido para premium
                else:
                    model_name = "llama-3.3-70b-versatile"  # Alta calidad para premium
        
        elif tier == "standard":
            # Tier standard: acceso a modelos 8B
            if fast_response:
                model_name = GROQ_FAST_MODEL  # Fast 8B model
            else:
                model_name = "llama3-8b-8192"  # Regular 8B model
        
        else:  # free u otros tiers básicos
            model_name = "llama3-8b-8192"  # Modelo básico para tiers gratuitos
    
    # Registrar info sobre el modelo seleccionado
    logger.info(f"Usando modelo Groq: {model_name} para tenant {tenant_info.tenant_id} (tier: {tenant_info.tier})")
    
    # Configuración común a todos los modelos
    common_params = {
        "temperature": settings.llm_temperature if hasattr(settings, 'llm_temperature') else LLM_DEFAULT_TEMPERATURE,
        "max_tokens": settings.llm_max_tokens if hasattr(settings, 'llm_max_tokens') else LLM_MAX_TOKENS
    }
    
    # Verificar que tenemos la API key configurada
    if not hasattr(settings, 'groq_api_key') or not settings.groq_api_key:
        logger.error("API key de Groq no configurada")
        raise GroqAuthenticationError("Se requiere API key de Groq para usar modelos de Groq")
        
    # Crear cliente Groq usando la implementación local (provider/groq.py)
    return GroqLLM(
        model=model_name,
        api_key=settings.groq_api_key,
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