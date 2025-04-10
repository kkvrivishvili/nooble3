# Actualización de embedding-service/services/embedding_provider.py

import logging
from typing import List, Dict, Any, Optional

from common.config import get_settings
from common.errors import (
    ServiceError, handle_service_error_simple, ErrorCode,
    EmbeddingGenerationError, EmbeddingModelError,
    TextTooLargeError, BatchTooLargeError, InvalidEmbeddingParamsError
)
from common.context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id, validate_tenant_context
from common.cache.manager import CacheManager  # Usar la implementación unificada de caché

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
        
        # Inicializar backend de embeddings (OpenAI o Ollama)
        if settings.use_ollama:
            from common.llm.ollama import get_embedding_model
            logger.info(f"Usando servicio de embeddings de Ollama con modelo {model_name}")
            self.embedder = get_embedding_model(model_name)
        else:
            from llama_index.embeddings.openai import OpenAIEmbedding
            logger.info(f"Usando servicio de embeddings de OpenAI con modelo {model_name}")
            self.openai_embed = OpenAIEmbedding(
                model_name=model_name,
                api_key=self.api_key,
                embed_batch_size=embed_batch_size
            )
    
    @handle_service_error_simple
    async def get_embedding(self, text: str) -> List[float]:
        """
        Obtiene un embedding con soporte de caché unificada.
        
        Args:
            text: Texto para generar embedding
            
        Returns:
            List[float]: Vector de embedding
            
        Raises:
            EmbeddingGenerationError: Si hay errores al generar el embedding
            TextTooLargeError: Si el texto excede el límite de tokens permitido
            ServiceError: Si no hay tenant válido disponible en el contexto y no se proporcionó uno
        """
        # Usar tenant_id proporcionado o el del contexto actual (validando que sea válido)
        tenant_id = self.tenant_id
        if tenant_id is None:
            tenant_id = get_current_tenant_id()
            tenant_id = validate_tenant_context(tenant_id)
            if tenant_id is None:
                raise ServiceError(ErrorCode.INVALID_TENANT_CONTEXT)
        
        if not text.strip():
            # Vector de ceros para texto vacío
            return [0.0] * self.dimensions
        
        # Validar longitud del texto antes de procesar
        token_count = self._estimate_token_count(text)
        if token_count > self.max_token_length_per_text:
            error_context = {
                "tenant_id": tenant_id,
                "model": self.model_name,
                "tokens": token_count,
                "max_tokens": self.max_token_length_per_text
            }
            logger.warning(f"Texto demasiado grande para embedding: {token_count} tokens", extra=error_context)
            raise TextTooLargeError(
                message=f"Text exceeds maximum token limit for embedding: {token_count} > {self.max_token_length_per_text}",
                details=error_context
            )
        
        # Verificar caché usando el sistema unificado
        cached_embedding = await CacheManager.get_embedding(
            text=text,
            model_name=self.model_name,
            tenant_id=tenant_id,
            agent_id=get_current_agent_id()
        )
        
        if cached_embedding:
            return cached_embedding
        
        # Obtener embedding desde el backend
        if hasattr(self, 'openai_embed'):
            embedding = await self.openai_embed._aget_text_embedding(text)
        else:
            embedding = await self.embedder.get_embedding(text)
        
        # Guardar en caché unificada
        await CacheManager.set_embedding(
            text=text,
            embedding=embedding,
            model_name=self.model_name,
            tenant_id=tenant_id,
            agent_id=get_current_agent_id(),
            ttl=86400  # 24 horas
        )
        
        return embedding
    
    @handle_service_error_simple
    async def get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Obtiene embeddings para un lote de textos con soporte de caché.
        
        Args:
            texts: Lista de textos para generar embeddings
            
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
            tenant_id = get_current_tenant_id()
            tenant_id = validate_tenant_context(tenant_id)
            if tenant_id is None:
                raise ServiceError(ErrorCode.INVALID_TENANT_CONTEXT)
        
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
            return await self._process_large_batch(texts, tenant_id)
        
        # Validar longitud de textos individuales y estimar tokens totales
        total_tokens = 0
        invalid_texts = []
        
        for i, text in enumerate(texts):
            if not text.strip():
                continue
                
            token_count = self._estimate_token_count(text)
            if token_count > self.max_token_length_per_text:
                invalid_texts.append((i, token_count))
            total_tokens += token_count
        
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
            return await self._process_large_batch(texts, tenant_id, total_tokens)
        
        # Preparar resultado con espacio para todos los textos
        result: List[Optional[List[float]]] = [None] * len(texts)
        
        # Verificar caché para todos los textos
        cached_embeddings = await CacheManager.get_embeddings_batch(
            texts=texts,
            model_name=self.model_name,
            tenant_id=tenant_id
        )
        
        # Identificar textos no cacheados que necesitan procesamiento
        texts_to_process = []
        indices_to_process = []
        
        for i, text in enumerate(texts):
            if i in cached_embeddings:
                # Usar embedding cacheado
                result[i] = cached_embeddings[i]
            elif not text.strip():
                # Vector de ceros para texto vacío
                result[i] = [0.0] * self.dimensions
            else:
                # Añadir a la lista para procesar
                texts_to_process.append(text)
                indices_to_process.append(i)
        
        # Procesar textos no cacheados si hay alguno
        if texts_to_process:
            try:
                if hasattr(self, 'openai_embed'):
                    new_embeddings = await self.openai_embed._aget_text_embedding_batch(texts_to_process)
                else:
                    new_embeddings = await self.embedder.get_batch_embeddings(texts_to_process)
                
                # Guardar en caché y asignar al resultado
                for idx, (i, embedding) in enumerate(zip(indices_to_process, new_embeddings)):
                    result[i] = embedding
                    
                    # Guardar en caché
                    await CacheManager.set_embedding(
                        text=texts[i],
                        embedding=embedding,
                        model_name=self.model_name,
                        tenant_id=tenant_id,
                        ttl=86400  # 24 horas
                    )
            except Exception as e:
                error_context = {
                    "tenant_id": tenant_id,
                    "model": self.model_name,
                    "batch_size": len(texts_to_process),
                    "error": str(e)
                }
                logger.error(f"Error generando embeddings para lote: {str(e)}", 
                           extra=error_context, exc_info=True)
                raise EmbeddingGenerationError(
                    message=f"Error generating embeddings for batch: {str(e)}",
                    details=error_context
                )
        
        # Verificar que todos los textos tienen embeddings
        for i, item in enumerate(result):
            if item is None:
                error_context = {
                    "tenant_id": tenant_id,
                    "model": self.model_name,
                    "index": i
                }
                logger.error(f"Falta embedding para el texto en posición {i}", extra=error_context)
                raise ServiceError(
                    message=f"Missing embedding for text at index {i}",
                    details=error_context
                )
        
        return result
    
    async def _process_large_batch(self, texts: List[str], tenant_id: str, estimated_tokens: Optional[int] = None) -> List[List[float]]:
        """
        Procesa un lote grande dividiéndolo en sublotes manejables.
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant
            estimated_tokens: Tokens estimados para el lote completo (opcional)
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
        """
        logger.info(f"Procesando lote grande con {len(texts)} textos en sublotes", 
                  extra={"tenant_id": tenant_id})
        
        # Determinar tamaño de sublote basado en restricciones
        if estimated_tokens and self.max_tokens_per_batch > 0:
            # Determinar sublotes por tokens
            avg_tokens_per_text = estimated_tokens / len(texts)
            texts_per_batch = min(
                max(1, int(self.max_tokens_per_batch / avg_tokens_per_text)),
                self.max_batch_size
            )
        else:
            # Determinar sublotes por cantidad
            texts_per_batch = self.max_batch_size
        
        # Crear sublotes
        batches = [texts[i:i+texts_per_batch] for i in range(0, len(texts), texts_per_batch)]
        logger.info(f"Dividiendo en {len(batches)} sublotes de aproximadamente {texts_per_batch} textos cada uno",
                  extra={"tenant_id": tenant_id})
        
        # Procesar cada sublote
        results = []
        for batch_idx, batch in enumerate(batches):
            logger.info(f"Procesando sublote {batch_idx+1}/{len(batches)} con {len(batch)} textos",
                      extra={"tenant_id": tenant_id, "batch_idx": batch_idx})
            
            # Recuperar embeddings temporalmente para este sublote
            temp_provider = CachedEmbeddingProvider(
                model_name=self.model_name,
                tenant_id=tenant_id,
                embed_batch_size=self.embed_batch_size,
                api_key=self.api_key
            )
            
            # Evitar recursión infinita asegurando que el sublote es más pequeño
            if len(batch) > self.max_batch_size:
                batch = batch[:self.max_batch_size]
                
            # Procesar sublote
            batch_results = await temp_provider.get_batch_embeddings(batch)
            results.extend(batch_results)
            
            # Liberar recursos explícitamente
            del temp_provider
            import gc
            gc.collect()
        
        return results
    
    def _estimate_token_count(self, text: str) -> int:
        """
        Estima el conteo de tokens para un texto.
        
        Args:
            text: Texto para estimar tokens
            
        Returns:
            int: Número estimado de tokens
        """
        if not text:
            return 0
            
        # Estimación simple: aprox. 4 caracteres por token para modelos como GPT
        estimated_tokens = len(text) // 4
        
        # Al menos 1 token para texto no vacío
        return max(1, estimated_tokens)