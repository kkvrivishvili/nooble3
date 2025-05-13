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
from common.context import with_context, Context, validate_tenant_context
from common.tracking import track_token_usage, estimate_prompt_tokens
from common.auth.models import validate_model_access
from common.cache import generate_resource_id_hash

# Importar el nuevo proveedor de OpenAI
from provider.openai import (
    OpenAIEmbeddingProvider,
    get_openai_embedding,
    is_openai_embedding_model,
    estimate_openai_tokens,
    OpenAIEmbeddingError,
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIModelNotFoundError
)

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
    Usa OpenAI como backend exclusivo para generación de embeddings con soporte de contexto multinivel.
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        tenant_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        embed_batch_size: int = settings.embedding_batch_size,
        api_key: Optional[str] = None,
        tier: Optional[str] = "free"
    ):
        self.api_key = api_key or settings.openai_api_key
        self.embed_batch_size = embed_batch_size
        self.tenant_id = tenant_id
        self.collection_id = collection_id  # Añadir collection_id para especificidad en caché
        self.tier = tier
        
        # Si no se especifica un modelo, se seleccionará dinámicamente según el tier
        # en el momento de la generación
        self.model_name = model_name
        
        # Importar la función para seleccionar el mejor modelo
        from services.llama_index_utils import select_best_embedding_model
        
        # Determinar dimensiones del embedding desde la configuración centralizada
        self.dimensions = DEFAULT_EMBEDDING_DIMENSION
        
        # Si se especifica un modelo, intentar determinar sus dimensiones
        if model_name:
            model_name_lower = model_name.lower()
            for name, dims in EMBEDDING_DIMENSIONS.items():
                if name in model_name_lower:
                    self.dimensions = dims
                    break
        # Si no se especifica modelo, usar dimensión por defecto (text-embedding-3-small = 1536)
        
        # Límites de procesamiento para controlar uso de memoria y tokens
        self.max_batch_size = settings.max_batch_size
        self.max_tokens_per_batch = settings.max_tokens_per_batch
        self.max_token_length_per_text = settings.max_token_length_per_text
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        EmbeddingGenerationError: (ErrorCode.EMBEDDING_ERROR, 500),
        EmbeddingModelError: (ErrorCode.MODEL_ERROR, 500),
        TextTooLargeError: (ErrorCode.TEXT_TOO_LARGE, 413),
        BatchTooLargeError: (ErrorCode.BATCH_TOO_LARGE, 413),
        OpenAIEmbeddingError: (ErrorCode.EXTERNAL_SERVICE_ERROR, 500),
        OpenAIAuthenticationError: (ErrorCode.AUTHORIZATION_ERROR, 401),
        OpenAIRateLimitError: (ErrorCode.RATE_LIMIT_EXCEEDED, 429),
        OpenAIModelNotFoundError: (ErrorCode.MODEL_NOT_FOUND_ERROR, 404)
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
            OpenAIEmbeddingError: Si hay errores específicos con OpenAI
        """
        # Si el texto está vacío, devolver vector de ceros
        if not text or not text.strip():
            return [0.0] * self.dimensions
        
        # Resolver parámetros de contexto
        tenant_id, coll_id = self._resolve_context_params(tenant_id=tenant_id, collection_id=collection_id, ctx=ctx)
        
        try:
            # Verificar longitud del texto
            await self._validate_text_length(text, tenant_id)
            
            # Determinar el tier a partir del contexto o usar el predeterminado
            current_tier = self.tier
            if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
                current_tier = ctx.tenant_info.tier
            
            # Seleccionar el modelo apropiado si no se especificó uno explícitamente
            model_to_use = self.model_name
            if not model_to_use:
                # Usar la función standard de tiers para seleccionar el mejor modelo
                available_models = get_available_embedding_models(current_tier, tenant_id)
                if available_models:
                    model_to_use = available_models[0]  # Usar el primer modelo disponible
                else:
                    model_to_use = "text-embedding-3-small"  # Modelo por defecto
            
            # Crear un proveedor de OpenAI para este modelo
            provider = OpenAIEmbeddingProvider(
                model=model_to_use,
                api_key=self.api_key
            )
            
            # Usar directamente el proveedor de OpenAI
            embedding = await provider.embed_query(
                text=text,
                tenant_id=tenant_id,
                ctx=ctx
            )
            
            return embedding
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
                
    @handle_errors(error_type="service", log_traceback=True, error_map={
        EmbeddingGenerationError: (ErrorCode.EMBEDDING_ERROR, 500),
        EmbeddingModelError: (ErrorCode.MODEL_ERROR, 500),
        TextTooLargeError: (ErrorCode.TEXT_TOO_LARGE, 413),
        BatchTooLargeError: (ErrorCode.BATCH_TOO_LARGE, 413),
        InvalidEmbeddingParamsError: (ErrorCode.INVALID_REQUEST, 400),
        OpenAIEmbeddingError: (ErrorCode.EXTERNAL_SERVICE_ERROR, 500),
        OpenAIAuthenticationError: (ErrorCode.AUTHORIZATION_ERROR, 401),
        OpenAIRateLimitError: (ErrorCode.RATE_LIMIT_EXCEEDED, 429),
        OpenAIModelNotFoundError: (ErrorCode.MODEL_NOT_FOUND_ERROR, 404)
    })
    @with_context(tenant=True, validate_tenant=True)
    async def batch_embeddings(
        self, 
        texts: List[str], 
        tenant_id: Optional[str] = None, 
        collection_id: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_ids: Optional[List[str]] = None,
        ctx: Context = None
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """
        Genera embeddings para una lista de textos con soporte de caché.
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant
            collection_id: ID de la colección (para mejorar especificidad en caché)
            document_id: ID del documento (para mejorar especificidad en caché)
            chunk_ids: Lista opcional de IDs de chunks (para mejorar especificidad en caché)
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            Tuple[List[List[float]], Dict[str, Any]]: 
                - Lista de embeddings generados
                - Metadatos del proceso (tokens, tiempos, etc)
                
        Raises:
            EmbeddingGenerationError: Si hay errores al generar los embeddings
            BatchTooLargeError: Si el batch excede el límite máximo
            ServiceError: Si no hay tenant válido disponible
            OpenAIEmbeddingError: Si hay errores específicos con OpenAI
        """
        # Si no hay textos, retornar lista vacía y metadatos básicos
        if not texts:
            return [], {
                "total_tokens": 0,
                "num_texts": 0,
                "source": "generation",
                "latency": 0
            }

        # Si todos los textos están vacíos, retornar vectores de ceros
        if all(not text.strip() for text in texts):
            zero_embeddings = [[0.0] * self.dimensions for _ in range(len(texts))]
            return zero_embeddings, {
                "total_tokens": 0,
                "num_texts": len(texts),
                "source": "generation",
                "latency": 0
            }
        
        # Resolver parámetros de contexto
        tenant_id, coll_id = self._resolve_context_params(tenant_id=tenant_id, collection_id=collection_id, ctx=ctx)
        
        try:
            # Verificar que el número de textos no exceda el máximo permitido
            await self._validate_batch_size(texts, tenant_id)
            
            # Verificar que cada texto no exceda el límite de tokens
            for i, text in enumerate(texts):
                if text.strip():  # Solo verificar textos no vacíos
                    await self._validate_text_length(text, tenant_id)

            # Determinar el tier a partir del contexto o usar el predeterminado
            current_tier = self.tier
            if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
                current_tier = ctx.tenant_info.tier
            
            # Seleccionar el modelo apropiado si no se especificó uno explícitamente
            model_to_use = self.model_name
            if not model_to_use:
                from services.llama_index_utils import select_best_embedding_model
                available_models = get_available_embedding_models(current_tier, tenant_id)
                if available_models:
                    model_to_use = available_models[0]  # Usar el primer modelo disponible
                else:
                    model_to_use = "text-embedding-3-small"  # Modelo por defecto

            # Crear un proveedor de OpenAI para este modelo
            provider = OpenAIEmbeddingProvider(
                model=model_to_use,
                api_key=self.api_key
            )
            
            # Usar directamente el proveedor de OpenAI para documentos
            embeddings = await provider.embed_documents(
                texts=texts,
                tenant_id=tenant_id,
                collection_id=collection_id,
                document_id=document_id,
                chunk_ids=chunk_ids,
                ctx=ctx
            )
            
            # Crear metadatos básicos
            start_time = time.time()
            total_tokens = 0
            for text in texts:
                if text.strip():  # Solo contar tokens en textos no vacíos
                    total_tokens += estimate_openai_tokens(text, model_to_use)
            
            elapsed_time = time.time() - start_time
            
            metadata = {
                "model": model_to_use,
                "usage": {
                    "total_tokens": total_tokens,
                    "prompt_tokens": total_tokens
                },
                "latency": elapsed_time,
                "source": "batch",
                "num_texts": len(texts),
                "provider": "openai"
            }
            
            # Retornar embeddings y metadatos
            return embeddings, metadata
        except Exception as e:
            # Mejorar manejo de errores con más contexto
            logger.error(f"Error al generar embeddings en batch: {str(e)}", 
                         extra={"tenant_id": tenant_id, "model": self.model_name, "batch_size": len(texts)})
            
            # Propagar el error con contexto enriquecido
            if isinstance(e, ServiceError):
                raise e
            else:
                raise EmbeddingGenerationError(
                    message=f"Error al generar embeddings en batch con el modelo {self.model_name}",
                    details={
                        "original_error": str(e), 
                        "model": self.model_name,
                        "batch_size": len(texts)
                    }
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
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        EmbeddingGenerationError: (ErrorCode.EMBEDDING_ERROR, 500),
        EmbeddingModelError: (ErrorCode.MODEL_ERROR, 500),
        TextTooLargeError: (ErrorCode.TEXT_TOO_LARGE, 413),
        BatchTooLargeError: (ErrorCode.BATCH_TOO_LARGE, 413)
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
        
        # Determinar el tier a partir del contexto o usar el predeterminado
        current_tier = self.tier
        if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
            current_tier = ctx.tenant_info.tier
            
        # Seleccionar el modelo apropiado si no se especificó uno explícitamente
        model_to_use = self.model_name
        if not model_to_use:
            from services.llama_index_utils import select_best_embedding_model
            model_to_use = select_best_embedding_model(current_tier, tenant_id)
        
        # Verificaciones básicas
        if not texts:
            return []
            
        # Validar que no exceda el tamaño máximo de lote
        if len(texts) > self.max_batch_size:
            error_context = {
                "tenant_id": tenant_id,
                "texts_count": len(texts),
                "max_batch_size": self.max_batch_size
            }
            
            logger.warning(f"Lote demasiado grande. Se procesará en sublotes: {len(texts)} > {self.max_batch_size}", 
                        extra=error_context)
            
            # Procesar lotes grandes dividiéndolos en sublotes
            return await self._process_large_batch(
                texts=texts,
                tenant_id=tenant_id,
                ctx=ctx,
                collection_id=coll_id,
                chunk_id=chunk_id
            )
        
        # Estimar tokens totales para controlar uso
        estimated_tokens = 0
        for text in texts:
            # Saltar textos vacíos
            if not text or not text.strip():
                continue
                
            try:
                # Estimar tokens para este texto
                text_tokens = await estimate_prompt_tokens(text)
                
                # Verificar si excede límite individual
                if text_tokens > self.max_token_length_per_text:
                    error_context = {
                        "tenant_id": tenant_id,
                        "estimated_tokens": text_tokens,
                        "max_tokens": self.max_token_length_per_text
                    }
                    
                    logger.warning(f"Texto individual excede límite: {text_tokens} > {self.max_token_length_per_text}", 
                                extra=error_context)
                    
                    raise TextTooLargeError(
                        message=f"Texto excede el límite máximo de tokens: {text_tokens} > {self.max_token_length_per_text}",
                        details=error_context
                    )
                
                # Acumular tokens estimados
                estimated_tokens += text_tokens
                
            except Exception as e:
                if not isinstance(e, TextTooLargeError):
                    logger.warning(f"Error estimando tokens: {str(e)}")
        
        # Verificar si el lote completo excede límite de tokens
        if estimated_tokens > self.max_tokens_per_batch:
            error_context = {
                "tenant_id": tenant_id,
                "texts_count": len(texts),
                "estimated_tokens": estimated_tokens,
                "max_tokens": self.max_tokens_per_batch
            }
            
            logger.warning(f"Lote excede límite de tokens. Se procesará en sublotes: {estimated_tokens} > {self.max_tokens_per_batch}", 
                        extra=error_context)
            
            # Procesar lote grande dividiendo por tokens
            return await self._process_large_batch(
                texts=texts,
                tenant_id=tenant_id,
                ctx=ctx,
                estimated_tokens=estimated_tokens,
                collection_id=coll_id,
                chunk_id=chunk_id
            )
        
        try:
            # Utilizar la implementación centralizada para generar embeddings
            embeddings, metadata = await generate_embeddings_with_llama_index(
                texts=texts,
                tenant_id=tenant_id,
                model_name=model_to_use,
                collection_id=coll_id,
                chunk_id=chunk_id,
                ctx=ctx
            )
            
            return embeddings
        except Exception as e:
            logger.error(f"Error al generar embeddings en lote: {str(e)}", 
                       extra={"tenant_id": tenant_id, "batch_size": len(texts)})
            
            if isinstance(e, ServiceError):
                raise e
            else:
                raise EmbeddingGenerationError(
                    message=f"Error al generar embeddings para {len(texts)} textos",
                    details={"original_error": str(e), "batch_size": len(texts)}
                ) from e
    
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
        # Resolver tenant_id
        resolved_tenant_id = tenant_id
        
        # Si no se proporcionó explícitamente, intentar obtener del contexto
        if not resolved_tenant_id and ctx and ctx.has_tenant_id():
            resolved_tenant_id = ctx.get_tenant_id()
            
        # Si aún no tenemos, usar el de la instancia
        if not resolved_tenant_id:
            resolved_tenant_id = self.tenant_id
            
        # Validar que tenemos un tenant_id válido
        if not resolved_tenant_id or resolved_tenant_id == "default":
            raise ServiceError(
                message="Se requiere un tenant_id válido para generar embeddings",
                error_code=ErrorCode.TENANT_REQUIRED,
                status_code=400
            )
            
        # Resolver collection_id
        resolved_collection_id = collection_id
        
        # Si no se proporcionó explícitamente, intentar obtener del contexto
        if not resolved_collection_id and ctx and hasattr(ctx, 'get_collection_id'):
            resolved_collection_id = ctx.get_collection_id()
            
        # Si aún no tenemos, usar el de la instancia
        if not resolved_collection_id:
            resolved_collection_id = self.collection_id
            
        return resolved_tenant_id, resolved_collection_id
    
    async def _process_large_batch(self, texts: List[str], tenant_id: str, ctx: Context, estimated_tokens: Optional[int] = None, collection_id: Optional[str] = None, chunk_id: Optional[List[str]] = None, model_name: Optional[str] = None) -> List[List[float]]:
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
        # Estimar tamaño de sublote basado en tokens o número máximo
        batch_size = self.embed_batch_size
        
        # Ajustar batch_size si tenemos estimación de tokens
        if estimated_tokens and len(texts) > 0:
            # Calcular ratio de tokens por texto
            tokens_per_text = estimated_tokens / len(texts)
            
            # Calcular tamaño de lote que no exceda el límite de tokens
            adjusted_batch_size = max(1, int(self.max_tokens_per_batch / tokens_per_text))
            
            # Usar el menor de los dos límites
            batch_size = min(adjusted_batch_size, self.embed_batch_size)
            
        logger.info(f"Procesando lote grande en sublotes de {batch_size} textos", 
                  extra={"tenant_id": tenant_id, "total_texts": len(texts)})
        
        # Dividir lote en sublotes
        sublotes = [texts[i:i+batch_size] for i in range(0, len(texts), batch_size)]
        
        # Dividir chunk_ids si se proporcionaron
        chunk_id_batches = None
        if chunk_id:
            chunk_id_batches = [chunk_id[i:i+batch_size] for i in range(0, len(chunk_id), batch_size)]
        
        # Procesar cada sublote en paralelo
        tasks = []
        for i, sublote in enumerate(sublotes):
            # Obtener chunk_ids para este sublote si existen
            current_chunk_ids = chunk_id_batches[i] if chunk_id_batches else None
            
            # Crear tarea para proceso asíncrono
            task = asyncio.create_task(
                generate_embeddings_with_llama_index(
                    texts=sublote,
                    tenant_id=tenant_id,
                    model_name=model_name or self.model_name,  # Usar el modelo proporcionado o el predeterminado
                    collection_id=collection_id,
                    chunk_id=current_chunk_ids,
                    ctx=ctx
                )
            )
            tasks.append(task)
        
        # Esperar a que todos los sublotes terminen
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesar resultados y posibles errores
        all_embeddings = []
        
        for i, result in enumerate(results):
            # Verificar si hubo una excepción
            if isinstance(result, Exception):
                logger.error(f"Error en sublote {i}: {str(result)}", 
                           extra={"tenant_id": tenant_id, "batch_index": i})
                
                # Para no bloquear todo el proceso, usar embeddings vacíos como fallback
                # Incluir tantos embeddings vacíos como textos en el sublote
                missing_embeddings = [[0.0] * self.dimensions for _ in range(len(sublotes[i]))]
                all_embeddings.extend(missing_embeddings)
            else:
                # Desempaquetar resultado (embeddings, metadata)
                embeddings, _ = result
                all_embeddings.extend(embeddings)
        
        # Verificar que tenemos el número correcto de embeddings
        if len(all_embeddings) != len(texts):
            logger.warning(f"Discrepancia en el número de embeddings: {len(all_embeddings)} vs {len(texts)} esperados", 
                         extra={"tenant_id": tenant_id})
            
            # Completar los faltantes con embeddings vacíos
            while len(all_embeddings) < len(texts):
                all_embeddings.append([0.0] * self.dimensions)
                
            # O recortar si tenemos más de lo esperado
            if len(all_embeddings) > len(texts):
                all_embeddings = all_embeddings[:len(texts)]
        
        logger.info(f"Procesamiento por lotes completado: {len(all_embeddings)} embeddings generados", 
                  extra={"tenant_id": tenant_id})
        
        return all_embeddings
