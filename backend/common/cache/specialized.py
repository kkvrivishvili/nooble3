# 3. Implementación de common/cache/specialized.py - CACHÉ ESPECIALIZADA

import time
import logging
import json
from typing import Dict, Any, List, Optional, Union

from ..context.vars import get_current_tenant_id, get_current_agent_id
from .redis import get_redis_client, generate_hash
from .contextual import cache_value_multi_level, get_cached_value_multi_level, invalidate_cache_hierarchy

logger = logging.getLogger(__name__)

class EmbeddingCache:
    """Caché especializado para embeddings vectoriales."""
    
    @staticmethod
    async def get(
        text: str, 
        model_name: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Optional[List[float]]:
        """Obtiene un embedding de la caché."""
        
        # Generar ID de recurso basado en texto y modelo
        text_hash = generate_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        
        # Usar sistema multinivel
        return await get_cached_value_multi_level(
            key_type="embed",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    
    @staticmethod
    async def set(
        text: str,
        embedding: List[float],
        model_name: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ttl: int = 86400
    ) -> bool:
        """Guarda un embedding en la caché."""
        
        # Generar ID de recurso
        text_hash = generate_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        
        # Usar sistema multinivel
        return await cache_value_multi_level(
            key_type="embed",
            resource_id=resource_id,
            value=embedding,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=ttl
        )
    
    @staticmethod
    async def get_batch(
        texts: List[str],
        model_name: str,
        tenant_id: Optional[str] = None
    ) -> Dict[int, List[float]]:
        """
        Obtiene embeddings para múltiples textos, devolviendo los que están en caché.
        
        Returns:
            Dict[int, List[float]]: Diccionario de {índice: embedding} para los encontrados
        """
        cached_embeddings = {}
        
        for i, text in enumerate(texts):
            if not text.strip():
                continue
                
            embedding = await EmbeddingCache.get(text, model_name, tenant_id)
            if embedding:
                cached_embeddings[i] = embedding
        
        return cached_embeddings

class QueryResultCache:
    """Caché especializado para resultados de consultas RAG."""
    
    @staticmethod
    async def get(
        query: str,
        collection_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        similarity_top_k: int = 4,
        response_mode: str = "compact"
    ) -> Optional[Dict[str, Any]]:
        """Obtiene un resultado de consulta RAG de la caché."""
        
        # Generar hash único para la consulta
        query_hash = generate_hash(query)
        
        # Incluir parámetros en el hash para evitar colisiones
        params_hash = generate_hash(f"{similarity_top_k}:{response_mode}")
        resource_id = f"{query_hash}:{params_hash}"
        
        return await get_cached_value_multi_level(
            key_type="query_result",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id
        )
    
    @staticmethod
    async def set(
        query: str,
        result: Dict[str, Any],
        collection_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        similarity_top_k: int = 4,
        response_mode: str = "compact",
        ttl: int = 3600
    ) -> bool:
        """Guarda un resultado de consulta RAG en la caché."""
        
        # Generar hash único para la consulta y parámetros
        query_hash = generate_hash(query)
        params_hash = generate_hash(f"{similarity_top_k}:{response_mode}")
        resource_id = f"{query_hash}:{params_hash}"
        
        return await cache_value_multi_level(
            key_type="query_result",
            resource_id=resource_id,
            value=result,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
            ttl=ttl
        )

class ConversationCache:
    """Caché especializado para conversaciones e historial."""
    
    @staticmethod
    async def get_conversation(
        conversation_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Obtiene datos de una conversación de la caché."""
        redis_client = await get_redis_client()
        if not redis_client:
            return None
        
        key = f"conv:{conversation_id}"
        cached_data = await redis_client.hgetall(key)
        
        if not cached_data:
            return None
            
        # Convertir tipos de datos
        result = dict(cached_data)
        
        # Convertir campos específicos
        if "is_active" in result:
            result["is_active"] = result["is_active"].lower() == "true"
            
        if "message_count" in result:
            result["message_count"] = int(result["message_count"])
            
        if "created_at" in result:
            result["created_at"] = float(result["created_at"])
            
        return result
    
    @staticmethod
    async def get_messages(
        conversation_id: str,
        start: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Obtiene mensajes de una conversación de la caché."""
        redis_client = await get_redis_client()
        if not redis_client:
            return []
        
        key = f"conv:{conversation_id}:messages"
        end = start + limit - 1 if limit > 0 else -1
        
        messages_data = await redis_client.lrange(key, start, end)
        
        if not messages_data:
            return []
            
        messages = []
        for msg_data in messages_data:
            try:
                msg = json.loads(msg_data)
                messages.append(msg)
            except json.JSONDecodeError:
                continue
                
        return messages
    
    @staticmethod
    async def add_message(
        conversation_id: str,
        message: Dict[str, Any],
        tenant_id: Optional[str] = None,
        ttl: int = 86400
    ) -> bool:
        """Añade un mensaje a la caché de conversación."""
        redis_client = await get_redis_client()
        if not redis_client:
            return False
        
        try:
            # Serializar mensaje
            message_json = json.dumps(message)
            
            # Clave de los mensajes
            messages_key = f"conv:{conversation_id}:messages"
            
            # Clave de la conversación
            conv_key = f"conv:{conversation_id}"
            
            # Añadir mensaje y actualizar metadatos
            pipeline = redis_client.pipeline()
            
            # Añadir a la lista de mensajes
            await pipeline.rpush(messages_key, message_json)
            await pipeline.expire(messages_key, ttl)
            
            # Incrementar contador y actualizar timestamp
            await pipeline.hincrby(conv_key, "message_count", 1)
            await pipeline.hset(conv_key, "updated_at", time.time())
            await pipeline.expire(conv_key, ttl)
            
            await pipeline.execute()
            
            return True
        except Exception as e:
            logger.warning(f"Error adding message to cache: {str(e)}")
            return False

class AgentCache:
    """Caché especializado para configuración y estado de agentes."""
    
    @staticmethod
    async def get_config(
        agent_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración de un agente de la caché."""
        return await get_cached_value_multi_level(
            key_type="agent_config",
            resource_id=agent_id,
            tenant_id=tenant_id
        )
    
    @staticmethod
    async def set_config(
        agent_id: str,
        config: Dict[str, Any],
        tenant_id: Optional[str] = None,
        ttl: int = 300
    ) -> bool:
        """Guarda la configuración de un agente en la caché."""
        return await cache_value_multi_level(
            key_type="agent_config",
            resource_id=agent_id,
            value=config,
            tenant_id=tenant_id,
            ttl=ttl
        )
    
    @staticmethod
    async def get_response(
        agent_id: str,
        query_hash: str,
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Obtiene una respuesta previa del agente de la caché."""
        return await get_cached_value_multi_level(
            key_type="agent_response",
            resource_id=query_hash,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    
    @staticmethod
    async def set_response(
        agent_id: str,
        query_hash: str,
        response: Dict[str, Any],
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ttl: int = 1800
    ) -> bool:
        """Guarda una respuesta del agente en la caché."""
        return await cache_value_multi_level(
            key_type="agent_response",
            resource_id=query_hash,
            value=response,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=ttl
        )