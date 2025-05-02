"""
Servicio de generación de embeddings vectoriales.

Este módulo proporciona clases y funciones para generar embeddings
con soporte de caché y contexto multitenancy.

# ATENCIÓN: CUMPLIMIENTO DEL PATRÓN CACHE-ASIDE CENTRALIZADO
# Este archivo y todos los métodos de embeddings cumplen estrictamente con el patrón Cache-Aside optimizado,
# utilizando exclusivamente la función centralizada get_with_cache_aside (common.cache) para todas las operaciones
# de caché de embeddings, siguiendo los TTLs y jerarquía de claves definidos en la arquitectura RAG.
# Cualquier modificación futura debe mantener este estándar y evitar implementaciones propias o directas sobre Redis.
# La serialización de embeddings se garantiza como listas planas de Python.
"""

import logging
from typing import List, Dict, Any, Optional

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

# Importar configuración centralizada
from config.constants import (
    EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_DIMENSION,
    TIMEOUTS
)
from config.settings import get_settings

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
        collection_id: Optional[str] = None,
        embed_batch_size: int = settings.embedding_batch_size,
        api_key: Optional[str] = None
    ):
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key
        self.embed_batch_size = embed_batch_size
        self.tenant_id = tenant_id
        self.collection_id = collection_id  # Añadir collection_id para especificidad en caché
        
        # Determinar dimensiones del embedding desde la configuración centralizada
        model_name_lower = model_name.lower()
        self.dimensions = DEFAULT_EMBEDDING_DIMENSION
        for name, dims in EMBEDDING_DIMENSIONS.items():
            if name in model_name_lower:
                self.dimensions = dims
                break
        
        # Límites de procesamiento para controlar uso de memoria y tokens
        self.max_batch_size = settings.max_batch_size
        self.max_tokens_per_batch = settings.max_tokens_per_batch
        self.max_token_length_per_text = settings.max_token_length_per_text
    
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
    async def get_batch_embeddings(self, texts: List[str], collection_id: Optional[str] = None, chunk_id: Optional[List[str]] = None, ctx: Context = None) -> List[List[float]]:
        """
        Obtiene embeddings para un lote de textos con soporte de caché.
        
        Args:
            texts: Lista de textos para generar embeddings
            collection_id: ID de la colección a la que pertenecen los textos (para caché)
            chunk_id: Lista de IDs únicos para cada chunk/texto (para caché y seguimiento)
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
            
        Raises:
            EmbeddingGenerationError: Si hay errores al generar los embeddings
            BatchTooLargeError: Si el lote es demasiado grande para procesarse en una sola solicitud
            TextTooLargeError: Si algún texto individual excede el límite de tokens
            ServiceError: Si no hay tenant válido disponible en el contexto y no se proporcionó uno
        """
        # Validar tenant_id y collection_id (usar el proporcionado o el del contexto)
        tenant_id = self.tenant_id
        if tenant_id is None:
            tenant_id = ctx.get_tenant_id()
            
        # Usar collection_id del parámetro, de la instancia, o del contexto si existe
        coll_id = collection_id or self.collection_id
        if coll_id is None and ctx and hasattr(ctx, 'collection_id'):
            coll_id = ctx.collection_id
        
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
            # Usar la función centralizada de LlamaIndex
            embeddings, metadata = await generate_embeddings_with_llama_index(
                texts=textos_no_vacios, 
                tenant_id=tenant_id,
                model_name=self.model_name,
                collection_id=coll_id,
                chunk_id=chunk_id,  # Pasar los IDs de chunks para mejor caché y seguimiento
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
    
    async def _process_large_batch(self, texts: List[str], tenant_id: str, ctx: Context, estimated_tokens: Optional[int] = None, collection_id: Optional[str] = None, chunk_id: Optional[List[str]] = None) -> List[List[float]]:
        """
        Procesa un lote grande dividiéndolo en sublotes manejables.
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant
            ctx: Contexto proporcionado por el decorador with_context
            estimated_tokens: Tokens estimados para el lote completo (opcional)
            collection_id: ID de la colección a la que pertenecen los textos (para caché)
            chunk_id: Lista de IDs únicos para cada chunk/texto (para caché y seguimiento)
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
        """
        logger.info(f"Procesando lote grande de {len(texts)} textos en sublotes")
        max_textos_por_solicitud = self.max_batch_size
        
        # Si tenemos tokens estimados y son demasiados, dividir por tokens
        if estimated_tokens and estimated_tokens > self.max_tokens_per_batch:
            # Calcular número aproximado de sublotes
            num_batches = (estimated_tokens // self.max_tokens_per_batch) + 1
            max_textos_por_solicitud = max(1, len(texts) // num_batches)
            
        # Procesar el lote en sublotes
        batch_size = max(1, max_textos_por_solicitud)
        results = []
        
        for i in range(0, len(texts), batch_size):
            # Obtener sublote de textos
            sublote = texts[i:i+batch_size]
            logger.debug(f"Procesando sublote {i//batch_size + 1} con {len(sublote)} textos")
            
            # Preparar los chunk_ids correspondientes si existen
            sublote_chunk_ids = None
            if chunk_id:
                sublote_chunk_ids = chunk_id[i:i+batch_size]
                logger.debug(f"Usando {len(sublote_chunk_ids)} chunk_ids para este sublote")
            
            # Procesar sublote con los parámetros correspondientes
            batch_results = await self.get_batch_embeddings(
                texts=sublote, 
                collection_id=collection_id or self.collection_id,
                chunk_id=sublote_chunk_ids,
                ctx=ctx
            )
            results.extend(batch_results)
        
        return results