# Actualización de embedding-service/services/embedding_provider.py

import logging
from typing import List, Dict, Any, Optional

from common.config import get_settings
from common.errors import ServiceError, handle_service_error_simple
from common.context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id
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
        tenant_id: str = None, 
        embed_batch_size: int = settings.embedding_batch_size,
        api_key: Optional[str] = None
    ):
        self.model_name = model_name
        self.api_key = api_key or settings.openai_api_key
        self.embed_batch_size = embed_batch_size
        self.tenant_id = tenant_id
        self.dimensions = settings.default_embedding_dimension
        
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
        """Obtiene un embedding con soporte de caché unificada."""
        if not text.strip():
            # Vector de ceros para texto vacío
            return [0.0] * self.dimensions
        
        # Usar tenant_id del contexto si no se proporcionó
        tenant_id = self.tenant_id or get_current_tenant_id()
        agent_id = get_current_agent_id()
        
        # Verificar caché usando el sistema unificado
        cached_embedding = await CacheManager.get_embedding(
            text=text,
            model_name=self.model_name,
            tenant_id=tenant_id,
            agent_id=agent_id
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
            agent_id=agent_id,
            ttl=86400  # 24 horas
        )
        
        return embedding
    
    @handle_service_error_simple
    async def get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Obtiene embeddings para un lote de textos con soporte de caché."""
        if not texts:
            return []
        
        # Obtener tenant_id del contexto si no se proporcionó
        tenant_id = self.tenant_id or get_current_tenant_id()
        
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
        
        # Verificar que todos los textos tienen embeddings
        for i, item in enumerate(result):
            if item is None:
                # Esto no debería ocurrir, pero por seguridad
                result[i] = [0.0] * self.dimensions
        
        return result