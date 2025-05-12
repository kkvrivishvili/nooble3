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
import asyncio
from typing import List, Dict, Any, Optional, Tuple

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
    async def get_embedding(self, text: str, tenant_id: Optional[str] = None, collection_id: Optional[str] = None, ctx: Context = None) -> List[float]:
        """
        Obtiene el embedding para un texto con soporte de caché.
        
        Args:
            text: Texto para generar embedding
            tenant_id: ID del tenant
            collection_id: ID de la colección (opcional, para mejorar especificidad en caché)
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[float]: Vector de embedding
            
        Raises:
            EmbeddingGenerationError: Si hay errores al generar los embeddings
            TextTooLargeError: Si el texto excede el límite de tokens
            ServiceError: Si no hay tenant válido disponible
        """
        # Si el texto está vacío, devolver vector de ceros
        if not text or not text.strip():
            return [0.0] * self.dimensions
        
        # Resolver parámetros de contexto
        tenant_id, coll_id = self._resolve_context_params(tenant_id=tenant_id, collection_id=collection_id, ctx=ctx)
        
        try:
            # Verificar longitud del texto
            await self._validate_text_length(text, tenant_id)
            
            # Utilizar la implementación centralizada compatible con ingestion-service
            embeddings, metadata = await generate_embeddings_with_llama_index(
                texts=[text], 
                tenant_id=tenant_id,
                model_name=self.model_name,
                collection_id=coll_id,  # Pasar collection_id para mejor caché
                ctx=ctx
            )
            
            # Retornar el primer (y único) embedding del resultado
            return embeddings[0]
        except Exception as e:
            # Mejorar manejo de errores con más contexto
            logger.error(f"Error al generar embedding: {str(e)}", 
                         extra={"tenant_id": tenant_id, "model": self.model_name})
            
            # Propagar el error con contexto enriquecido
            if isinstance(e, ServiceError):
                raise e
            else:
                raise EmbeddingGenerationError(
                    message=f"Error al generar embedding con el modelo {self.model_name}",
                    details={"original_error": str(e), "model": self.model_name}
                ) from e
    
    async def _validate_text_length(self, text: str, tenant_id: Optional[str] = None) -> None:
        """
        Valida que el texto no exceda el límite máximo de tokens permitido.
        
        Args:
            text: Texto a validar
            tenant_id: ID del tenant para contextualizar logs
            
        Raises:
            TextTooLargeError: Si el texto excede el límite máximo de tokens
        """
        if not text or not text.strip():
            return
            
        # Usar función centralizada para estimar tokens
        estimated_tokens = await estimate_prompt_tokens(text)
        
        if estimated_tokens > self.max_token_length_per_text:
            error_context = {
                "tenant_id": tenant_id,
                "model": self.model_name,
                "estimated_tokens": estimated_tokens,
                "max_tokens": self.max_token_length_per_text,
                "service": "embedding-service"
            }
            
            # Mejorar mensaje de error con más contexto
            error_msg = f"Texto excede el límite máximo de tokens para embedding: {estimated_tokens} > {self.max_token_length_per_text}"
            logger.warning(error_msg, extra=error_context)
            
            raise TextTooLargeError(
                message=error_msg,
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
        # Resolver tenant_id y collection_id usando método centralizado
        tenant_id, coll_id = self._resolve_context_params(tenant_id=ctx.get_tenant_id() if ctx else None, collection_id=collection_id, ctx=ctx)
        
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
        
        # Optimizar validación de longitud de textos individuales y estimar tokens totales
        total_tokens = 0
        invalid_texts = []
        processed_texts = []
        
        # Procesar textos en paralelo para estimar tokens más rápido
        token_estimation_tasks = []
        
        for i, text in enumerate(texts):
            if not text.strip():
                # Para textos vacíos, usaremos vector de ceros
                processed_texts.append("")
                continue
                
            # Crear tarea para estimación de tokens
            task = estimate_prompt_tokens(text)
            token_estimation_tasks.append((i, text, task))
        
        # Esperar todas las estimaciones y procesar resultados
        for i, text, task in token_estimation_tasks:
            estimated_tokens = await task
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
                "max_tokens": self.max_token_length_per_text,
                "service": "embedding-service"
            }
            error_indices = [idx for idx, _ in invalid_texts]
            error_tokens = [tokens for _, tokens in invalid_texts]
            
            # Mejorar mensaje de error con más contexto
            error_msg = f"{len(invalid_texts)} textos exceden el límite máximo de tokens para embedding ({self.max_token_length_per_text})"
            logger.error(f"{error_msg} en posiciones: {error_indices}", extra=error_context)
            
            # Construir detalles para mejor depuración
            details = {
                "indices": error_indices,
                "token_counts": error_tokens,
                "max_tokens": self.max_token_length_per_text,
                "model": self.model_name,
                "collection_id": coll_id or "no_collection"
            }
            
            raise TextTooLargeError(
                message=error_msg,
                details=details
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
        
        # Optimizar procesamiento de textos vacíos y no vacíos
        # Simplificar la lógica separando textos vacíos y no vacíos desde el principio
        textos_no_vacios = [text for text in texts if text.strip()]
        indices_vacios = [i for i, text in enumerate(texts) if not text.strip()]
        
        # Vector de ceros predefinido para textos vacíos
        vector_ceros = [0.0] * self.dimensions
        
        # Inicializar arreglo de resultados con tamaño adecuado
        result = [None] * len(texts)
        
        # Primero, asignar vectores de ceros a los textos vacíos
        for idx in indices_vacios:
            result[idx] = vector_ceros
        
        # Solo procesar embeddings para textos no vacíos
        if textos_no_vacios:
            try:
                # Usar la función centralizada de LlamaIndex
                embeddings, metadata = await generate_embeddings_with_llama_index(
                    texts=textos_no_vacios, 
                    tenant_id=tenant_id,
                    model_name=self.model_name,
                    collection_id=coll_id,
                    chunk_id=chunk_id,
                    ctx=ctx
                )
                
                # Asignar embeddings a posiciones correspondientes en el arreglo de resultados
                embed_idx = 0
                for i, text in enumerate(texts):
                    if text.strip():
                        result[i] = embeddings[embed_idx]
                        embed_idx += 1
            except Exception as e:
                # Mejorar manejo de errores con más contexto
                logger.error(f"Error al generar embeddings: {str(e)}", 
                             extra={"tenant_id": tenant_id, "model": self.model_name, 
                                    "texts_count": len(textos_no_vacios)})
                
                # Propagar el error con contexto enriquecido
                if isinstance(e, ServiceError):
                    raise e
                else:
                    raise EmbeddingGenerationError(
                        message=f"Error al generar embeddings con el modelo {self.model_name}",
                        details={"original_error": str(e), "model": self.model_name}
                    ) from e
            
        return result
    
    def _resolve_context_params(self, tenant_id: Optional[str] = None, collection_id: Optional[str] = None, ctx: Optional[Context] = None) -> Tuple[str, Optional[str]]:
        """
        Resuelve los parámetros de contexto (tenant_id, collection_id) de forma unificada.
        Prioridad: parámetros explícitos > contexto > valores de instancia
        
        Args:
            tenant_id: ID del tenant (opcional)
            collection_id: ID de la colección (opcional)
            ctx: Objeto Context (opcional)
            
        Returns:
            tuple[str, Optional[str]]: Tupla con (tenant_id, collection_id) resueltos
        
        Raises:
            ServiceError: Si no se puede resolver un tenant_id válido
        """
        # Resolver tenant_id: parámetro > contexto > instancia
        resolved_tenant_id = tenant_id or (ctx.get_tenant_id() if ctx else None) or self.tenant_id
        
        # Validar que exista un tenant_id válido
        if not resolved_tenant_id:
            raise ServiceError(
                message="Se requiere tenant_id para generar embeddings",
                error_code=ErrorCode.TENANT_REQUIRED,
                details={"source": "embedding_provider"}
            )
            
        # Resolver collection_id: parámetro > instancia > contexto
        resolved_collection_id = collection_id or self.collection_id
        if resolved_collection_id is None and ctx and hasattr(ctx, 'collection_id'):
            resolved_collection_id = ctx.collection_id
            
        return resolved_tenant_id, resolved_collection_id
    
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
        # Validar parámetros
        if not tenant_id:
            tenant_id, collection_id = self._resolve_context_params(tenant_id=tenant_id, collection_id=collection_id, ctx=ctx)
            
        logger.info(f"Procesando lote grande de {len(texts)} textos en sublotes")
        max_textos_por_solicitud = self.max_batch_size
        
        # Si tenemos tokens estimados y son demasiados, dividir por tokens
        if estimated_tokens and estimated_tokens > self.max_tokens_per_batch:
            # Calcular número aproximado de sublotes necesarios
            num_batches = (estimated_tokens // self.max_tokens_per_batch) + 1
            max_textos_por_solicitud = max(1, len(texts) // num_batches)
            
        # Procesar el lote en sublotes
        batch_size = max(1, max_textos_por_solicitud)
        results = []
        
        # Crear tareas para procesar sublotes en paralelo (hasta un límite razonable)
        max_concurrent_tasks = min(5, (len(texts) + batch_size - 1) // batch_size)
        tasks = []
        
        for i in range(0, len(texts), batch_size):
            # Obtener sublote de textos
            sublote = texts[i:i+batch_size]
            logger.debug(f"Preparando sublote {i//batch_size + 1} con {len(sublote)} textos")
            
            # Preparar los chunk_ids correspondientes si existen
            sublote_chunk_ids = None
            if chunk_id:
                sublote_chunk_ids = chunk_id[i:i+batch_size]
                logger.debug(f"Usando {len(sublote_chunk_ids)} chunk_ids para este sublote")
            
            # Crear tarea para procesar sublote
            task = self.get_batch_embeddings(
                texts=sublote, 
                collection_id=collection_id,
                chunk_id=sublote_chunk_ids,
                ctx=ctx
            )
            tasks.append(task)
            
            # Procesar en grupos para limitar la concurrencia
            if len(tasks) >= max_concurrent_tasks or i + batch_size >= len(texts):
                # Ejecutar tareas en paralelo y recolectar resultados
                batch_results = await asyncio.gather(*tasks)
                for br in batch_results:
                    results.extend(br)
                # Reiniciar lista de tareas
                tasks = []
        
        return results