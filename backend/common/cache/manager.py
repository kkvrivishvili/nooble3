import logging
import time
import json
from typing import Dict, Any, List, Optional, Set, Union
import asyncio
import hashlib
import redis.asyncio as redis

from ..context.vars import get_current_tenant_id, get_current_agent_id
from ..context.vars import get_current_conversation_id, get_current_collection_id

logger = logging.getLogger(__name__)

# Caché en memoria para acceso ultrarrápido
_memory_cache: Dict[str, Any] = {}
_memory_expiry: Dict[str, float] = {}

# Configuración de límites de caché en memoria
MEMORY_CACHE_MAX_SIZE = 1000  # Número máximo de entradas
MEMORY_CACHE_CLEANUP_PERCENT = 0.2  # Porcentaje de entradas a eliminar (20%)

TTL_SHORT = 300       # 5 minutos (configuraciones, datos volátiles)
TTL_MEDIUM = 3600     # 1 hora (resultados de consulta, datos moderadamente estables)
TTL_LONG = 86400      # 24 horas (embeddings, datos altamente estables)
TTL_PERMANENT = 0     # Sin expiración (datos persistentes)

_redis_client = None

async def get_redis_client() -> Optional[Any]:
    """Obtiene un cliente Redis compartido para CacheManager"""
    global _redis_client
    if _redis_client is None:
        from ..config.settings import get_settings
        settings = get_settings()
        pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=getattr(settings, 'redis_max_connections', 10),
            decode_responses=True
        )
        client = redis.Redis(connection_pool=pool)
        try:
            await client.ping()
            logger.info("Redis conectado exitosamente en CacheManager")
            _redis_client = client
        except Exception as e:
            logger.warning(f"Redis connection failed: {str(e)} - running without cache.")
            return None
    return _redis_client

def generate_hash(data: Any) -> str:
    """Genera un hash MD5 para cualquier tipo de dato"""
    if isinstance(data, str):
        return hashlib.md5(data.encode()).hexdigest()
    else:
        return hashlib.md5(json.dumps(data).encode()).hexdigest()

class CacheManager:
    """
    Sistema de caché unificado para la plataforma Linktree AI.
    
    Proporciona caché multinivel (memoria + Redis) con soporte para:
    - Aislamiento por tenant, agente, conversación y colección
    - Especializaciones para todos los tipos de datos de la plataforma
    - Invalidación selectiva por contexto
    """
    
    _lock = asyncio.Lock()
    
    @staticmethod
    async def initialize() -> bool:
        """
        Inicializa y verifica la conexión a Redis.
        """
        try:
            redis_client = await get_redis_client()
            if redis_client and await redis_client.ping():
                logger.info("CacheManager initialized successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Error inicializando caché: {str(e)}")
            return False
    
    @staticmethod
    def _build_key(
        data_type: str, 
        resource_id: str, 
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> str:
        """Genera una clave de caché estandarizada."""
        # Usar contexto actual si no se proporciona
        tenant_id = tenant_id or get_current_tenant_id()
        
        # Construir clave base
        key_parts = [tenant_id, data_type]
        
        # Añadir componentes de contexto disponibles
        if agent_id:
            key_parts.append(f"agent:{agent_id}")
        if conversation_id:
            key_parts.append(f"conv:{conversation_id}")
        if collection_id:
            key_parts.append(f"coll:{collection_id}")
        
        # Añadir ID del recurso
        key_parts.append(resource_id)
        
        return ":".join(filter(None, key_parts))
    
    @staticmethod
    def _generate_search_keys(
        data_type: str,
        resource_id: str,
        tenant_id: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> List[str]:
        """Genera claves de búsqueda en orden jerárquico (más específica a más general)."""
        keys = []
        
        # 1. Clave más específica (todos los niveles disponibles)
        if agent_id and conversation_id and collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, conversation_id, collection_id))
        
        # 2. Nivel agente + conversación
        if agent_id and conversation_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, conversation_id))
        
        # 3. Nivel agente + colección
        if agent_id and collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, collection_id=collection_id))
                
        # 4. Nivel solo agente
        if agent_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id))
                
        # 5. Nivel solo colección
        if collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, collection_id=collection_id))
                
        # 6. Nivel base (solo tenant)
        keys.append(CacheManager._build_key(
            data_type, resource_id, tenant_id))
            
        return keys
    
    @staticmethod
    async def get(
        data_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        use_memory: bool = True,
        search_hierarchy: bool = True
    ) -> Optional[Any]:
        """
        Obtiene un valor de la caché multinivel.
        
        Args:
            data_type: Tipo de datos ("embedding", "query", "agent", etc.)
            resource_id: ID del recurso específico
            tenant_id, agent_id, etc.: Componentes contextuales opcionales
            use_memory: Si debe verificar la caché en memoria
            search_hierarchy: Si debe buscar en toda la jerarquía de claves
            
        Returns:
            Any: Valor cacheado o None si no se encuentra
        """
        # Usar contexto actual si necesario
        tenant_id = tenant_id or get_current_tenant_id()
        agent_id = agent_id or get_current_agent_id()
        conversation_id = conversation_id or get_current_conversation_id()
        collection_id = collection_id or get_current_collection_id()
        
        # Verificar caché en memoria primero
        if use_memory:
            # Clave para memoria (siempre usamos la clave más específica)
            memory_key = CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, 
                conversation_id, collection_id
            )
            
            if memory_key in _memory_cache:
                if time.time() < _memory_expiry.get(memory_key, 0):
                    return _memory_cache[memory_key]
                # Limpiar si expiró
                if memory_key in _memory_cache:
                    del _memory_cache[memory_key]
                if memory_key in _memory_expiry:
                    del _memory_expiry[memory_key]
                
        # Generar claves de búsqueda
        if search_hierarchy:
            search_keys = CacheManager._generate_search_keys(
                data_type, resource_id, tenant_id, agent_id, 
                conversation_id, collection_id
            )
        else:
            # Usar solo la clave exacta
            search_keys = [CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, 
                conversation_id, collection_id
            )]
            
        # Buscar en Redis
        redis_client = await get_redis_client()
        if not redis_client:
            return None
            
        for key in search_keys:
            try:
                value = await redis_client.get(key)
                if value:
                    # Deserializar JSON si es necesario
                    try:
                        result = json.loads(value)
                    except json.JSONDecodeError:
                        result = value
                        
                    # Guardar en memoria para futuras consultas
                    if use_memory:
                        memory_key = search_keys[0]  # La clave más específica
                        CacheManager._add_to_memory_cache(memory_key, result)
                        
                    return result
            except Exception as e:
                logger.warning(f"Error al leer de Redis con clave {key}: {e}")
                continue
                
        return None
    
    @staticmethod
    async def set(
        data_type: str,
        resource_id: str,
        value: Any,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        ttl: int = TTL_MEDIUM,
        use_memory: bool = True
    ) -> bool:
        """
        Guarda un valor en la caché multinivel.
        
        Args:
            data_type: Tipo de datos ("embedding", "query", "agent", etc.)
            resource_id: ID del recurso específico
            value: Valor a almacenar
            tenant_id, agent_id, etc.: Componentes contextuales opcionales
            ttl: Tiempo de vida en segundos
            use_memory: Si debe guardar también en memoria
            
        Returns:
            bool: True si se guardó correctamente
        """
        tenant_id = tenant_id or get_current_tenant_id()
        agent_id = agent_id or get_current_agent_id()
        conversation_id = conversation_id or get_current_conversation_id()
        collection_id = collection_id or get_current_collection_id()
        
        # Generar clave completa
        key = CacheManager._build_key(
            data_type, resource_id, tenant_id, agent_id, 
            conversation_id, collection_id
        )
        
        # Guardar en Redis
        redis_client = await get_redis_client()
        if not redis_client:
            return False
            
        try:
            # Serializar a JSON si es necesario
            if not isinstance(value, (str, bytes)):
                serialized = json.dumps(value)
            else:
                serialized = value
                
            # Guardar con TTL
            if ttl > 0:
                await redis_client.setex(key, ttl, serialized)
            else:
                await redis_client.set(key, serialized)
                
            # Guardar en memoria para acceso rápido
            if use_memory:
                CacheManager._add_to_memory_cache(key, value, ttl)
                
            return True
        except Exception as e:
            logger.warning(f"Error al guardar en Redis con clave {key}: {e}")
            return False
            
    @staticmethod
    def _add_to_memory_cache(key: str, value: Any, ttl: int = TTL_MEDIUM):
        """
        Añade una entrada a la caché en memoria con TTL y limpieza de exceso de tamaño.
        """
        now = time.time()
        _memory_cache[key] = value
        _memory_expiry[key] = now + ttl
        if len(_memory_cache) > MEMORY_CACHE_MAX_SIZE:
            to_remove = int(len(_memory_cache) * MEMORY_CACHE_CLEANUP_PERCENT)
            sorted_items = sorted(_memory_expiry.items(), key=lambda item: item[1])
            for k, _ in sorted_items[:to_remove]:
                _memory_cache.pop(k, None)
                _memory_expiry.pop(k, None)
    
    @staticmethod
    async def delete(
        data_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> bool:
        """
        Elimina un valor específico de la caché.
        
        Args:
            data_type: Tipo de datos
            resource_id: ID del recurso
            tenant_id, agent_id, etc.: Componentes contextuales
            
        Returns:
            bool: True si se eliminó correctamente
        """
        # Generar clave
        key = CacheManager._build_key(
            data_type, resource_id, tenant_id, agent_id, 
            conversation_id, collection_id
        )
        
        # Eliminar de memoria
        if key in _memory_cache:
            del _memory_cache[key]
        if key in _memory_expiry:
            del _memory_expiry[key]
            
        # Eliminar de Redis
        redis_client = await get_redis_client()
        if not redis_client:
            return True  # Ya se eliminó de memoria
            
        try:
            await redis_client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Error al eliminar de Redis con clave {key}: {e}")
            return False
            
    @staticmethod
    async def invalidate(
        tenant_id: str,
        data_type: str,
        resource_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
    ) -> int:
        """
        Elimina entradas de caché de Redis y memoria según patrón.
        """
        pattern = CacheManager._build_key(
            data_type,
            resource_id or "*",
            tenant_id,
            agent_id,
            conversation_id,
            collection_id
        )
        redis_client = await get_redis_client()
        if not redis_client:
            return 0
        total_deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await redis_client.delete(*keys)
                    total_deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Error invalidando caché con patrón {pattern}: {e}")
        to_remove = [k for k in _memory_cache if k.startswith(pattern.rstrip("*"))]
        for k in to_remove:
            _memory_cache.pop(k, None)
            _memory_expiry.pop(k, None)
        return total_deleted
    
    @staticmethod
    async def invalidate_agent_complete(tenant_id: str, agent_id: str) -> int:
        """
        Invalida todas las cachés relacionadas con un agente.
        """
        total_deleted = 0
        try:
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="agent_config",
                agent_id=agent_id,
            )
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="agent_response",
                agent_id=agent_id,
            )
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="conversation_messages",
                agent_id=agent_id,
            )
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="agent_stats",
                agent_id=agent_id,
            )
            logger.info(f"Caché completa de agente {agent_id} invalidada: {total_deleted} entradas")
        except Exception as e:
            logger.error(f"Error invalidando caché completa de agente: {str(e)}")
        return total_deleted
    
    @staticmethod
    async def invalidate_collection_complete(tenant_id: str, collection_id: str) -> int:
        """
        Invalida todas las cachés relacionadas con una colección.
        """
        total_deleted = 0
        try:
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="vector_store",
                collection_id=collection_id,
            )
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="query_result",
                collection_id=collection_id,
            )
            total_deleted += await CacheManager.invalidate(
                tenant_id=tenant_id,
                data_type="collection_stats",
                collection_id=collection_id,
            )
            logger.info(f"Caché completa de colección {collection_id} invalidada: {total_deleted} entradas")
        except Exception as e:
            logger.error(f"Error invalidando caché completa de colección: {str(e)}")
        return total_deleted
    
    @staticmethod
    async def get_embedding(text: str, model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> Optional[List[float]]:
        """
        Obtiene un embedding vectorial almacenado en caché.
        """
        text_hash = generate_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        return await CacheManager.get(
            data_type="embedding",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
    
    @staticmethod
    async def set_embedding(text: str, embedding: List[float], model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> bool:
        """
        Almacena un embedding en la caché con TTL estándar para embeddings.
        """
        text_hash = generate_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        return await CacheManager.set(
            data_type="embedding",
            resource_id=resource_id,
            value=embedding,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ttl=TTL_LONG,
        )
    
    @staticmethod
    async def get_query_result(query: str, collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> Optional[Dict[str, Any]]:
        """
        Obtiene el resultado de una consulta de la caché.
        """
        params_hash = generate_hash(f"{similarity_top_k}:{response_mode}")
        query_hash = generate_hash(query)
        resource_id = f"{query_hash}:{params_hash}"
        return await CacheManager.get(
            data_type="query_result",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
        )
    
    @staticmethod
    async def set_query_result(query: str, result: Dict[str, Any], collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> bool:
        """
        Almacena el resultado de una consulta en la caché con TTL estándar para consultas.
        """
        params_hash = generate_hash(f"{similarity_top_k}:{response_mode}")
        query_hash = generate_hash(query)
        resource_id = f"{query_hash}:{params_hash}"
        return await CacheManager.set(
            data_type="query_result",
            resource_id=resource_id,
            value=result,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
            ttl=TTL_MEDIUM,
        )
    
    @staticmethod
    async def get_agent_config(
        agent_id: str,
        tenant_id: Optional[str] = None,
        use_memory: bool = True
    ) -> Optional[Any]:
        """
        Obtiene la configuración del agente desde cache.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        resource_id = f"agent_config:{agent_id}"
        return await CacheManager.get(
            data_type="agent_config",
            resource_id=resource_id,
            tenant_id=tenant_id,
            use_memory=use_memory
        )

    @staticmethod
    async def set_agent_config(
        agent_id: str,
        config: Any,
        tenant_id: Optional[str] = None,
        ttl: int = TTL_MEDIUM,
        use_memory: bool = True
    ) -> bool:
        """
        Guarda la configuración del agente en cache.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        resource_id = f"agent_config:{agent_id}"
        return await CacheManager.set(
            data_type="agent_config",
            resource_id=resource_id,
            value=config,
            tenant_id=tenant_id,
            ttl=ttl,
            use_memory=use_memory
        )

    @staticmethod
    async def get_agent_response(
        agent_id: str,
        query: str,
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        use_memory: bool = True
    ) -> Optional[Any]:
        """
        Obtiene una respuesta de agente cacheada.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        conversation_id = conversation_id or get_current_conversation_id()
        query_hash = generate_hash(query)
        resource_id = f"{agent_id}:{conversation_id}:{query_hash}"
        return await CacheManager.get(
            data_type="agent_response",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            use_memory=use_memory
        )
    
    @staticmethod
    async def set_agent_response(
        agent_id: str,
        query: str,
        response: Any,
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ttl: int = TTL_MEDIUM,
        use_memory: bool = True
    ) -> bool:
        """
        Guarda una respuesta de agente en cache.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        conversation_id = conversation_id or get_current_conversation_id()
        query_hash = generate_hash(query)
        resource_id = f"{agent_id}:{conversation_id}:{query_hash}"
        return await CacheManager.set(
            data_type="agent_response",
            resource_id=resource_id,
            value=response,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=ttl,
            use_memory=use_memory
        )
    
    @staticmethod
    async def get_conversation_messages(
        conversation_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Obtiene los mensajes de una conversación de la caché.
        
        Args:
            conversation_id: ID de la conversación
            tenant_id, agent_id: Contexto opcional
            
        Returns:
            Optional[List[Dict[str, Any]]]: Lista de mensajes o None
        """
        return await CacheManager.get(
            data_type="conversation_messages",
            resource_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    
    @staticmethod
    async def set_conversation_messages(
        conversation_id: str,
        messages: List[Dict[str, Any]],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ttl: int = TTL_MEDIUM
    ) -> bool:
        """
        Almacena los mensajes de una conversación en la caché.
        
        Args:
            conversation_id: ID de la conversación
            messages: Lista de mensajes a almacenar
            tenant_id, agent_id: Contexto opcional
            ttl: Tiempo de vida en segundos
            
        Returns:
            bool: True si se guardó correctamente
        """
        return await CacheManager.set(
            data_type="conversation_messages",
            resource_id=conversation_id,
            value=messages,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=ttl
        )

    @staticmethod
    async def increment_counter(
        scope: str,
        resource_id: str,
        tokens: int = 0,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: str = "llm"
    ) -> bool:
        """
        Incrementa un contador de tokens de forma atómica usando CacheManager.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        key = f"{scope}:{resource_id}"
        async with CacheManager._lock:
            current = await CacheManager.get(
                token_type, key,
                tenant_id, agent_id, conversation_id, collection_id,
                use_memory=False, search_hierarchy=False
            ) or 0
            await CacheManager.set(
                token_type, key, current + tokens,
                tenant_id, agent_id, conversation_id, collection_id,
                ttl=0, use_memory=False
            )
        return True

    @staticmethod
    async def get_counter(
        scope: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: str = "llm"
    ) -> int:
        """
        Obtiene el valor del contador de tokens.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        key = f"{scope}:{resource_id}"
        value = await CacheManager.get(
            token_type, key,
            tenant_id, agent_id, conversation_id, collection_id,
            use_memory=False, search_hierarchy=False
        )
        return int(value) if value else 0

    @staticmethod
    async def ttl(
        data_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> int:
        """
        Obtiene el TTL de un valor en Redis.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        agent_id = agent_id or get_current_agent_id()
        conversation_id = conversation_id or get_current_conversation_id()
        collection_id = collection_id or get_current_collection_id()
        key = CacheManager._build_key(
            data_type, resource_id, tenant_id, agent_id, conversation_id, collection_id
        )
        redis_client = await get_redis_client()
        if not redis_client:
            return -1
        try:
            ttl_value = await redis_client.ttl(key)
            return ttl_value if ttl_value is not None else -1
        except Exception as e:
            logger.warning(f"Error al obtener TTL de Redis con clave {key}: {e}")
            return -1

    @staticmethod
    async def invalidate_cache(
        scope: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> int:
        """
        Invalida la caché en memoria y Redis para un ámbito/contexto dado.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        pattern_parts = [tenant_id, scope]
        if agent_id: pattern_parts.append(f"agent:{agent_id}")
        if conversation_id: pattern_parts.append(f"conv:{conversation_id}")
        if collection_id: pattern_parts.append(f"coll:{collection_id}")
        pattern = ":".join(pattern_parts)
        # Eliminar claves en Redis
        redis_client = await get_redis_client()
        keys = await redis_client.keys(f"{pattern}*")
        deleted = 0
        if keys:
            deleted += await redis_client.delete(*keys)
        # Eliminar de caché en memoria
        to_delete = [k for k in _memory_cache if k.startswith(pattern)]
        for k in to_delete:
            _memory_cache.pop(k, None)
            _memory_expiry.pop(k, None)
            deleted += 1
        return deleted
    
    @staticmethod
    async def rpush(
        list_name: str,
        value: Any,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> int:
        """
        Agrega un valor a una lista de Redis (cola) para procesamiento de trabajos.
        """
        redis_client = await get_redis_client()
        if not redis_client:
            return 0
        try:
            return await redis_client.rpush(list_name, value)
        except Exception as e:
            logger.warning(f"Error al hacer rpush en Redis lista {list_name}: {e}")
            return 0

    @staticmethod
    async def lpop(
        queue_name: str
    ) -> Optional[Any]:
        """
        Extrae (pop izquierdo) un valor de una lista de Redis (cola) para procesamiento de trabajos.
        """
        redis_client = await get_redis_client()
        if not redis_client:
            return None
        try:
            return await redis_client.lpop(queue_name)
        except Exception as e:
            logger.warning(f"Error al hacer lpop en Redis lista {queue_name}: {e}")
            return None