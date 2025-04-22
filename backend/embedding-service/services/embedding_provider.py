"""
Servicio de generación de embeddings vectoriales.

Este módulo proporciona clases y funciones para generar embeddings
con soporte de caché y contexto multitenancy.
"""

import logging
from typing import List, Dict, Any, Optional

from common.config import get_settings
from common.config.tiers import get_available_embedding_models
from common.errors import (
    ServiceError, handle_errors, ErrorCode,
    EmbeddingGenerationError, EmbeddingModelError,
    TextTooLargeError, BatchTooLargeError, InvalidEmbeddingParamsError
)
from common.context import with_context, Context
from common.tracking import track_token_usage, estimate_prompt_tokens
from common.auth.models import validate_model_access
from common.cache import generate_resource_id_hash

# Importar la nueva implementación compatible con el servicio de ingestión
from services.llama_index_utils import generate_embeddings_with_llama_index

logger = logging.getLogger(__name__)
settings = get_settings()

class CachedEmbeddingProvider:
    """
    Proveedor de embeddings con soporte de caché.
    Soporta múltiples backends (OpenAI, Ollama) y contexto multinivel.
    """
    
    def __init__(
        self,
        model_name: str = settings.default_embedding_model,
        tenant_id: Optional[str] = None, 
        embed_batch_size: int = settings.embedding_batch_size,
        api_key: Optional[str] = None
    ):
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key
        self.embed_batch_size = embed_batch_size
        self.tenant_id = tenant_id
        self.dimensions = settings.default_embedding_dimension
        
        # Límites de procesamiento para controlar uso de memoria y tokens
        self.max_batch_size = min(self.embed_batch_size, settings.max_embedding_batch_size) if hasattr(settings, 'max_embedding_batch_size') else self.embed_batch_size
        self.max_tokens_per_batch = settings.max_tokens_per_batch if hasattr(settings, 'max_tokens_per_batch') else 50000
        self.max_token_length_per_text = settings.max_token_length_per_text if hasattr(settings, 'max_token_length_per_text') else 8000
    
    @handle_errors(error_type="simple", log_traceback=False, error_map={
        EmbeddingGenerationError: ("EMBEDDING_GENERATION_ERROR", 500),
        EmbeddingModelError: ("EMBEDDING_MODEL_ERROR", 500),
        TextTooLargeError: ("TEXT_TOO_LARGE", 413),
        BatchTooLargeError: ("BATCH_TOO_LARGE", 413)
    })
    @with_context(tenant=True, validate_tenant=True)
    async def get_embedding(self, text: str, tenant_id: Optional[str] = None, ctx: Context = None) -> List[float]:
        """
        Obtiene el embedding para un texto con soporte de caché.
        
        Args:
            text: Texto para generar embedding
            tenant_id: ID del tenant
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[float]: Vector de embedding
        """
        # Si el texto está vacío, devolver vector de ceros
        if not text:
            return [0.0] * self.dimensions
        
        # Verificar longitud del texto
        await self._validate_text_length(text, tenant_id)
        
        # Utilizar la implementación centralizada compatible con ingestion-service
        embeddings, metadata = await generate_embeddings_with_llama_index(
            texts=[text], 
            tenant_id=tenant_id or self.tenant_id,
            model_name=self.model_name,
            ctx=ctx
        )
        
        # Retornar el primer (y único) embedding del resultado
        return embeddings[0]
    
    async def _validate_text_length(self, text: str, tenant_id: Optional[str] = None) -> None:
        """
        Valida que el texto no exceda el límite máximo de tokens permitido.
        
        Args:
            text: Texto a validar
            tenant_id: ID del tenant para contextualizar logs
            
        Raises:
            TextTooLargeError: Si el texto excede el límite máximo de tokens
        """
        if not text:
            return
            
        # Usar función centralizada para estimar tokens
        estimated_tokens = await estimate_prompt_tokens(text)
        
        if estimated_tokens > self.max_token_length_per_text:
            error_context = {
                "tenant_id": tenant_id,
                "model": self.model_name,
                "estimated_tokens": estimated_tokens,
                "max_tokens": self.max_token_length_per_text
            }
            logger.warning(f"Texto demasiado grande para embedding: {estimated_tokens} tokens", 
                         extra=error_context)
            raise TextTooLargeError(
                message=f"Text exceeds maximum token limit for embedding: {estimated_tokens} > {self.max_token_length_per_text}",
                details=error_context
            )
    
    @handle_errors(error_type="simple", log_traceback=False, error_map={
        EmbeddingGenerationError: ("EMBEDDING_GENERATION_ERROR", 500),
        EmbeddingModelError: ("EMBEDDING_MODEL_ERROR", 500),
        TextTooLargeError: ("TEXT_TOO_LARGE", 413),
        BatchTooLargeError: ("BATCH_TOO_LARGE", 413)
    })
    @with_context(tenant=True, validate_tenant=True)
    async def get_batch_embeddings(self, texts: List[str], ctx: Context = None) -> List[List[float]]:
        """
        Obtiene embeddings para un lote de textos con soporte de caché.
        
        Args:
            texts: Lista de textos para generar embeddings
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
            
        Raises:
            EmbeddingGenerationError: Si hay errores al generar los embeddings
            BatchTooLargeError: Si el lote es demasiado grande para procesarse en una sola solicitud
            TextTooLargeError: Si algún texto individual excede el límite de tokens
            ServiceError: Si no hay tenant válido disponible en el contexto y no se proporcionó uno
        """
        # Validar tenant_id (usar el proporcionado o el del contexto)
        tenant_id = self.tenant_id
        if tenant_id is None:
            tenant_id = ctx.get_tenant_id()
        
        if not texts:
            return []
        
        # Verificar el tamaño del lote
        if len(texts) > self.max_batch_size:
            error_context = {
                "tenant_id": tenant_id,
                "batch_size": len(texts),
                "max_batch_size": self.max_batch_size
            }
            logger.warning(f"Tamaño de lote excede el máximo permitido: {len(texts)} > {self.max_batch_size}", 
                         extra=error_context)
            
            # Procesar en sublotes si es posible
            return await self._process_large_batch(texts, tenant_id, ctx)
        
        # Validar longitud de textos individuales y estimar tokens totales
        total_tokens = 0
        invalid_texts = []
        processed_texts = []
        
        for i, text in enumerate(texts):
            if not text.strip():
                # Para textos vacíos, usaremos vector de ceros
                processed_texts.append("")
                continue
                
            # Usar función centralizada para estimar tokens
            estimated_tokens = await estimate_prompt_tokens(text)
            if estimated_tokens > self.max_token_length_per_text:
                invalid_texts.append((i, estimated_tokens))
            total_tokens += estimated_tokens
            processed_texts.append(text)
        
        # Reportar textos inválidos si hay alguno
        if invalid_texts:
            error_context = {
                "tenant_id": tenant_id,
                "model": self.model_name,
                "invalid_count": len(invalid_texts),
                "max_tokens": self.max_token_length_per_text
            }
            error_indices = [idx for idx, _ in invalid_texts]
            error_tokens = [tokens for _, tokens in invalid_texts]
            
            logger.error(f"Textos demasiado grandes para embedding en posiciones: {error_indices}", 
                       extra=error_context)
            raise TextTooLargeError(
                message=f"{len(invalid_texts)} texts exceed maximum token limit for embedding",
                details={
                    "indices": error_indices,
                    "token_counts": error_tokens,
                    "max_tokens": self.max_token_length_per_text
                }
            )
        
        # Verificar tokens totales del lote
        if total_tokens > self.max_tokens_per_batch:
            error_context = {
                "tenant_id": tenant_id,
                "total_tokens": total_tokens,
                "max_tokens": self.max_tokens_per_batch
            }
            logger.warning(f"Tokens totales exceden el máximo por lote: {total_tokens} > {self.max_tokens_per_batch}", 
                         extra=error_context)
            
            # Procesar en sublotes divididos por tokens
            return await self._process_large_batch(texts, tenant_id, ctx, total_tokens)
        
        # Reemplazar textos vacíos con vectores de ceros después del procesamiento
        result = []
        textos_no_vacios = [text for text in processed_texts if text.strip()]
        indices_no_vacios = [i for i, text in enumerate(processed_texts) if text.strip()]
        
        if textos_no_vacios:
            # Utilizar la implementación centralizada compatible con ingestion-service
            embeddings, metadata = await generate_embeddings_with_llama_index(
                texts=textos_no_vacios, 
                tenant_id=tenant_id,
                model_name=self.model_name,
                ctx=ctx
            )
            
            # Crear resultado con vectores vacíos para textos vacíos
            embedding_idx = 0
            for i, text in enumerate(processed_texts):
                if text.strip():
                    result.append(embeddings[embedding_idx])
                    embedding_idx += 1
                else:
                    result.append([0.0] * self.dimensions)
        else:
            # Si todos los textos están vacíos, retornar vectores de ceros
            result = [[0.0] * self.dimensions for _ in processed_texts]
            
        return result
    
    async def _process_large_batch(self, texts: List[str], tenant_id: str, ctx: Context, estimated_tokens: Optional[int] = None) -> List[List[float]]:
        """
        Procesa un lote grande dividiéndolo en sublotes manejables.
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant
            ctx: Contexto proporcionado por el decorador with_context
            estimated_tokens: Tokens estimados para el lote completo (opcional)
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
        """
        logger.info(f"Procesando lote grande de {len(texts)} textos en sublotes")
        
        # Si tenemos tokens estimados y son demasiados, dividir por tokens
        if estimated_tokens and estimated_tokens > self.max_tokens_per_batch:
            # Calcular número aproximado de sublotes
            num_batches = (estimated_tokens // self.max_tokens_per_batch) + 1
            batch_size = max(1, len(texts) // num_batches)
        else:
            # Dividir por tamaño de lote
            batch_size = self.max_batch_size
        
        # Procesar sublotes
        results = []
        
        for i in range(0, len(texts), batch_size):
            sublote = texts[i:i+batch_size]
            logger.debug(f"Procesando sublote {i//batch_size + 1} con {len(sublote)} textos")
            
            # Procesar sublote usando el método principal
            batch_result = await self.get_batch_embeddings(sublote, ctx)
            results.extend(batch_result)
        
        return results