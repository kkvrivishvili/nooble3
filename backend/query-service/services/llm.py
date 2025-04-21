"""
Funciones para interactuar con modelos de lenguaje (LLMs).
"""

import logging
from typing import Optional, Any, Dict

from llama_index.llms.openai import OpenAI

from common.models import TenantInfo
from common.auth import validate_model_access
from common.config import get_settings
from common.llm.ollama import get_llm_model

logger = logging.getLogger(__name__)

async def get_llm_for_tenant(tenant_info: TenantInfo, requested_model: Optional[str] = None) -> Any:
    """
    Obtiene un modelo LLM apropiado para un tenant según su nivel de suscripción.
    
    Args:
        tenant_info: Información del tenant
        requested_model: Modelo solicitado (opcional)
        
    Returns:
        Modelo LLM configurado compatible con LlamaIndex
    """
    settings = get_settings()
    
    # Determinar modelo basado en tier del tenant y solicitud
    model_name = await validate_model_access(
        tenant_info, 
        requested_model or settings.default_llm_model,
        model_type="llm",
        tenant_id=tenant_info.tenant_id
    )
    
    # Configuración común a todos los modelos
    common_params = {
        "temperature": settings.llm_temperature if hasattr(settings, 'llm_temperature') else 0.7,
        "max_tokens": settings.llm_max_tokens if hasattr(settings, 'llm_max_tokens') else 2048
    }
    
    # Configurar el LLM según si usamos Ollama u OpenAI
    if settings.use_ollama:
        # get_llm_model devuelve un modelo compatible con LlamaIndex
        logger.info(f"Usando modelo Ollama: {model_name}")
        return get_llm_model(model_name, **common_params)
    else:
        # Usar OpenAI
        logger.info(f"Usando modelo OpenAI: {model_name}")
        return OpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            **common_params
        )

async def generate_embedding_via_service(text: str) -> Dict[str, Any]:
    """
    Genera un embedding para un texto a través del servicio de embeddings.
    
    Args:
        text: Texto para generar embedding
        
    Returns:
        Dict: Respuesta del servicio de embeddings con vector y metadatos
    """
    from common.context.vars import get_current_tenant_id, get_current_agent_id
    from common.context.vars import get_current_conversation_id
    from common.utils.http import call_service
    from common.errors import (
        EmbeddingGenerationError, EmbeddingModelError, 
        TextTooLargeError, ServiceError, ErrorCode
    )
    
    settings = get_settings()
    tenant_id = get_current_tenant_id()
    agent_id = get_current_agent_id()
    conversation_id = get_current_conversation_id()
    
    try:
        # Preparar solicitud al servicio de embeddings
        payload = {
            "model": settings.default_embedding_model,
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
            else:
                # Si es un error no específico, usar el genérico
                raise ServiceError(
                    message=f"Error en servicio de embeddings: {error_msg}",
                    error_code=error_code,
                    details=error_details
                )
        
        # Extraer datos de la respuesta estandarizada
        response_data = response.get("data", {})
        embeddings = response_data.get("embeddings", [])
        
        # Retornar el primer embedding (si existe)
        if embeddings and len(embeddings) > 0:
            return {
                "embedding": embeddings[0],
                "model": response_data.get("model", settings.default_embedding_model)
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