import logging
import time
import json
from typing import Dict, Any, List, Optional, Set, Union
import asyncio
import hashlib
import redis.asyncio as redis

from ..context.vars import get_current_tenant_id, get_current_agent_id
from ..context.vars import get_current_conversation_id, get_current_collection_id

# Importamos directamente desde core.constants en lugar de common.cache
# para evitar importaciones circulares
from ..core.constants import (
    TTL_SHORT, TTL_STANDARD, TTL_EXTENDED, TTL_PERMANENT,
    DEFAULT_TTL_MAPPING,
    METRIC_SERIALIZATION_ERROR
)
from common.cache.helpers import generate_resource_id_hash, serialize_for_cache, deserialize_from_cache, get_default_ttl_for_data_type, track_cache_metrics

logger = logging.getLogger(__name__)

# Caché en memoria para acceso ultrarrápido
_memory_cache: Dict[str, Any] = {}
_memory_expiry: Dict[str, float] = {}

# Conexión Redis
_redis_client = None

async def get_redis_client() -> Optional[Any]:
    """Obtiene un cliente Redis compartido para CacheManager con configuración mejorada para resiliencia"""
    global _redis_client
    if _redis_client is None:
        from ..config import get_settings
        settings = get_settings()
        try:
            # Configuración más robusta con parámetros explícitos
            pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                decode_responses=True,
                socket_timeout=5.0,            # Timeout para operaciones de socket
                socket_connect_timeout=5.0,    # Timeout para conexión inicial
                health_check_interval=15,      # Verificar la conexión cada 15 segundos
                retry_on_timeout=True          # Reintentar automáticamente en caso de timeout
            )
            client = redis.Redis(connection_pool=pool)
            
            # Verificar conexión con ping
            await client.ping()
            logger.info("Redis conectado exitosamente en CacheManager")
            _redis_client = client
        except Exception as e:
            logger.warning(f"Redis connection failed: {str(e)} - running without cache.")
            return None
    return _redis_client

class CacheManager:
    """
    Gestor de caché centralizado. Proporciona métodos para almacenar y recuperar
    datos de diferentes tipos con un modelo jerárquico de claves.
    
    Soporta:
    - Caché en memoria para acceso ultra-rápido
    - Caché en Redis para persistencia
    - Claves jerarquizadas por tenant, agente, conversación, colección
    - TTL configurable por tipo de dato
    - Métodos específicos para tipos de datos comunes
    """
    
    # Instancia singleton
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Obtiene o crea la instancia singleton del CacheManager"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Inicialización del gestor de caché."""
        from ..config import get_settings
        self.settings = get_settings()
        
        # Usar valores desde la configuración centralizada en config
        self.ttl_short = TTL_SHORT
        self.ttl_standard = TTL_STANDARD
        self.ttl_extended = TTL_EXTENDED
        self.ttl_permanent = TTL_PERMANENT
        self.use_memory_cache = self.settings.use_memory_cache
        
        # Cachear funciones auxiliares para evitar importaciones repetidas
        self._serialize_for_cache = serialize_for_cache
        self._deserialize_from_cache = deserialize_from_cache
    
    # Mutex para operaciones concurrentes
    _lock = asyncio.Lock()
    
    async def initialize(self) -> bool:
        """
        Inicializa la conexión a Redis y verifica que esté funcionando.
        
        Returns:
            bool: True si la inicialización fue exitosa, False en caso contrario
        """
        try:
            client = await get_redis_client()
            return client is not None
        except Exception as e:
            logger.error(f"Error inicializando caché: {str(e)}")
            return False
    
    # Método estático compatible que llama al método de instancia
    @staticmethod
    async def initialize_static() -> bool:
        """
        Versión estática del método initialize() para compatibilidad.
        """
        instance = CacheManager.get_instance()
        return await instance.initialize()
    
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
        """
        Genera una lista de claves de caché en orden de especificidad.
        
        Se utiliza para buscar en la jerarquía de claves, desde la más específica
        a la más general.
        """
        keys = []
        
        # 1. Nivel completo (tenant + agent + conversation + collection)
        if tenant_id and agent_id and conversation_id and collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, 
                conversation_id, collection_id))
                
        # 2. Nivel tenant + agent + conversation
        if tenant_id and agent_id and conversation_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, conversation_id))
                
        # 3. Nivel tenant + agent + collection 
        if tenant_id and agent_id and collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id, 
                None, collection_id))
                
        # 4. Nivel tenant + agent
        if tenant_id and agent_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, agent_id))
                
        # 5. Nivel tenant + collection
        if tenant_id and collection_id:
            keys.append(CacheManager._build_key(
                data_type, resource_id, tenant_id, None, 
                None, collection_id))
                
        # 6. Nivel tenant
        keys.append(CacheManager._build_key(
            data_type, resource_id, tenant_id))
            
        return keys
    
    async def _get_internal(
        self,
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
        # Control de recursión usando contexto de task
        task = asyncio.current_task()
        if not hasattr(task, "_cache_recursion_depth"):
            setattr(task, "_cache_recursion_depth", 0)
        else:
            current_depth = getattr(task, "_cache_recursion_depth")
            if current_depth > 2:  # Limitar a 3 niveles máximo
                logger.warning(f"Alcanzada profundidad máxima de recursión en caché para {data_type}:{resource_id}")
                return None
            setattr(task, "_cache_recursion_depth", current_depth + 1)
            
        try:
            # Validar parámetros obligatorios
            tenant_id = tenant_id or get_current_tenant_id()
            # Aceptar 'system' como tenant_id válido para health checks
            # y otros casos especiales donde no hay tenant específico
            if not tenant_id and data_type != "system":
                logger.warning(f"Tenant ID es obligatorio para obtener {data_type} de caché")
                return None
                
            if not resource_id:
                logger.warning(f"Resource ID es obligatorio para obtener {data_type} de caché")
                return None
            
            # Usar contexto actual si necesario
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
                logger.warning(f"Redis no disponible, no se puede obtener {data_type}:{resource_id} de caché")
                return None
                
            for key in search_keys:
                try:
                    value = await redis_client.get(key)
                    if value:
                        # Deserializar valor de caché
                        deserialize_success = True
                        try:
                            if isinstance(value, str) and value.startswith('{') or value.startswith('['):
                                decoded = json.loads(value)
                            else:
                                # Si no parece JSON válido, usar el valor tal cual
                                decoded = value
                        except json.JSONDecodeError as json_err:
                            logger.debug(f"Valor no es JSON válido para {key}, usando raw: {str(json_err)}")
                            decoded = value
                        except Exception as decode_err:
                            logger.warning(f"Error deserializando valor para {key}: {str(decode_err)}")
                            deserialize_success = False
                            continue
                            
                        # Aplicar deserialización específica del tipo
                        try:
                            result = self._deserialize_from_cache(decoded, data_type)
                        except Exception as deserialize_err:
                            logger.warning(f"Error en deserialización específica para {data_type}: {str(deserialize_err)}")
                            # Tratar de utilizar el valor decodificado como fallback
                            result = decoded
                        
                        # Guardar en memoria para futuras consultas
                        if use_memory:
                            memory_key = search_keys[0]  # La clave más específica
                            self._add_to_memory_cache(memory_key, result)
                            
                        return result
                except Exception as e:
                    logger.warning(f"Error al leer de Redis con clave {key}: {str(e)}")
                    continue
                    
        finally:
            # Restaurar el contador de recursión
            if hasattr(task, "_cache_recursion_depth"):
                current_depth = getattr(task, "_cache_recursion_depth")
                if current_depth > 0:
                    setattr(task, "_cache_recursion_depth", current_depth - 1)
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
        Método estático compatible que llama al método de instancia get().
        """
        instance = CacheManager.get_instance()
        # Para evitar el error, usar parámetros con nombre excepto para los que causan el error
        return await instance._get_internal(
            data_type,  # Parámetro posicional para evitar duplicación
            resource_id,  # Parámetro posicional para evitar duplicación
            tenant_id=tenant_id,  # El resto como parámetros con nombre
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            use_memory=use_memory,
            search_hierarchy=search_hierarchy
        )
    
    async def set(
        self,
        data_type: str,
        resource_id: str,
        value: Any,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        ttl: Optional[int] = None,
        use_memory: bool = True
    ) -> bool:
        """
        Almacena un valor en la caché.
        
        El TTL se determina automáticamente si no se proporciona:
        - Si es None: Se usa el TTL predeterminado para el tipo de datos desde DEFAULT_TTL_MAPPING
        - Si es 0: La caché no expira
        - Otro valor: Se usa el valor proporcionado (en segundos)
        
        Args:
            data_type: Tipo de datos ("embedding", "vector_store", etc.)
            resource_id: ID único del recurso
            value: Valor a almacenar
            tenant_id: ID del tenant (opcional)
            agent_id: ID del agente (opcional)
            conversation_id: ID de la conversación (opcional)
            collection_id: ID de la colección (opcional)
            ttl: Tiempo de vida en segundos (opcional, usa el predeterminado para el tipo si es None)
            use_memory: Flag para usar caché en memoria (opcional)
            
        Returns:
            bool: True si se almacenó correctamente
        """
        tenant_id = tenant_id or get_current_tenant_id()
        agent_id = agent_id or get_current_agent_id()
        conversation_id = conversation_id or get_current_conversation_id()
        collection_id = collection_id or get_current_collection_id()
        
        # Determinar TTL si no se proporciona
        if ttl is None:
            ttl = get_default_ttl_for_data_type(data_type)
        
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
            # Usar la función de serialización centralizada en lugar de importarla en cada llamada
            try:
                value_to_cache = self._serialize_for_cache(value, data_type)
            except Exception as e:
                logger.warning(f"Error de serialización al guardar {data_type} en caché: {e}")
                await track_cache_metrics(
                    data_type=data_type,
                    tenant_id=tenant_id,
                    metric_type=METRIC_SERIALIZATION_ERROR,
                    value=1,
                    metadata={"error": str(e)}
                )
                return False
            
            # Convertir a JSON si no es un tipo primitivo
            if not isinstance(value_to_cache, (str, bytes)):
                serialized = json.dumps(value_to_cache)
            else:
                serialized = value_to_cache
                
            # Guardar con TTL
            if ttl > 0:
                await redis_client.setex(key, ttl, serialized)
            else:
                await redis_client.set(key, serialized)
                
            # Guardar en memoria para acceso rápido
            if use_memory:
                self._add_to_memory_cache(key, value_to_cache, ttl)
                
            return True
        except Exception as e:
            logger.warning(f"Error al guardar en Redis con clave {key}: {e}")
            return False
            
    @staticmethod
    async def set(
        data_type: str,
        resource_id: str,
        value: Any,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        ttl: Optional[int] = None,
        use_memory: bool = True
    ) -> bool:
        """
        Método estático compatible que llama al método de instancia set().
        """
        instance = CacheManager.get_instance()
        return await instance.set(
            data_type=data_type,
            resource_id=resource_id,
            value=value,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            ttl=ttl,
            use_memory=use_memory
        )


    def _add_to_memory_cache(self, key: str, value: Any, ttl: int = TTL_STANDARD):
        """
        Añade una entrada a la caché en memoria con TTL y limpieza de exceso de tamaño.
        """
        now = time.time()
        _memory_cache[key] = value
        _memory_expiry[key] = now + ttl
        if len(_memory_cache) > self.settings.memory_cache_size:
            to_remove = int(len(_memory_cache) * self.settings.memory_cache_cleanup_percent)
            sorted_items = sorted(_memory_expiry.items(), key=lambda item: item[1])
            for k, _ in sorted_items[:to_remove]:
                _memory_cache.pop(k, None)
                _memory_expiry.pop(k, None)
    
    async def delete(
        self,
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
            logger.warning(f"Redis no disponible, no se puede eliminar de caché remota {data_type}:{resource_id}")
            return True  # Consideramos éxito parcial ya que se eliminó de memoria
            
        try:
            result = await redis_client.delete(key)
            if result > 0:
                logger.debug(f"Eliminada correctamente la clave {key} de Redis")
            return True
        except Exception as e:
            logger.warning(f"Error al eliminar de Redis con clave {key}: {str(e)}")
            return False
            
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
        Método estático compatible que llama al método de instancia delete().
        """
        instance = CacheManager.get_instance()
        return await instance.delete(
            data_type=data_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id
        )
    
    async def invalidate(
        self,
        tenant_id: str,
        data_type: str,
        resource_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
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
    async def invalidate(
        tenant_id: str,
        data_type: str,
        resource_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> int:
        """
        Método estático compatible que llama al método de instancia invalidate().
        """
        instance = CacheManager.get_instance()
        return await instance.invalidate(
            tenant_id=tenant_id,
            data_type=data_type,
            resource_id=resource_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id
        )
    
    async def get_embedding(self, text: str, model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> Optional[List[float]]:
        """
        Obtiene un embedding vectorial almacenado en caché.
        """
        text_hash = generate_resource_id_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        return await self.get(
            data_type="embedding",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
    
    async def set_embedding(self, text: str, embedding: List[float], model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> bool:
        """
        Almacena un embedding en la caché con TTL estándar para embeddings.
        """
        text_hash = generate_resource_id_hash(text)
        resource_id = f"{model_name}:{text_hash}"
        
        ttl = DEFAULT_TTL_MAPPING.get("embedding", TTL_EXTENDED)
        
        return await self.set(
            data_type="embedding",
            resource_id=resource_id,
            value=embedding,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ttl=ttl
        )
    
    async def get_query_result(self, query: str, collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> Optional[Dict[str, Any]]:
        """
        Obtiene el resultado de una consulta de la caché.
        """
        params = {"similarity_top_k": similarity_top_k, "response_mode": response_mode}
        params_hash = generate_resource_id_hash(params)
        query_hash = generate_resource_id_hash(query)
        resource_id = f"{query_hash}:{params_hash}"
        
        return await self.get(
            data_type="query_result",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
        )
    
    async def set_query_result(self, query: str, result: Dict[str, Any], collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> bool:
        """
        Almacena el resultado de una consulta en la caché con TTL estándar para consultas.
        """
        params = {"similarity_top_k": similarity_top_k, "response_mode": response_mode}
        params_hash = generate_resource_id_hash(params)
        query_hash = generate_resource_id_hash(query)
        resource_id = f"{query_hash}:{params_hash}"
        
        ttl = DEFAULT_TTL_MAPPING.get("query_result", TTL_SHORT)
        
        return await self.set(
            data_type="query_result",
            resource_id=resource_id,
            value=result,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
            ttl=ttl,
        )
    
    @staticmethod
    async def get_embedding(text: str, model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> Optional[List[float]]:
        """
        Método estático compatible que llama al método de instancia get_embedding().
        """
        instance = CacheManager.get_instance()
        return await instance.get_embedding(text, model_name, tenant_id, agent_id)
        
    @staticmethod
    async def set_embedding(text: str, embedding: List[float], model_name: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None) -> bool:
        """
        Método estático compatible que llama al método de instancia set_embedding().
        """
        instance = CacheManager.get_instance()
        return await instance.set_embedding(text, embedding, model_name, tenant_id, agent_id)
        
    @staticmethod
    async def get_query_result(query: str, collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> Optional[Dict[str, Any]]:
        """
        Método estático compatible que llama al método de instancia get_query_result().
        """
        instance = CacheManager.get_instance()
        return await instance.get_query_result(query, collection_id, tenant_id, agent_id, similarity_top_k, response_mode)
        
    @staticmethod
    async def set_query_result(query: str, result: Dict[str, Any], collection_id: str, tenant_id: Optional[str] = None, agent_id: Optional[str] = None, similarity_top_k: int = 4, response_mode: str = "compact") -> bool:
        """
        Método estático compatible que llama al método de instancia set_query_result().
        """
        instance = CacheManager.get_instance()
        return await instance.set_query_result(query, result, collection_id, tenant_id, agent_id, similarity_top_k, response_mode)
        
    async def get_agent_config(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
        use_memory: bool = True
    ) -> Optional[Any]:
        """
        Obtiene la configuración del agente desde cache.
        """
        tenant_id = tenant_id or get_current_tenant_id()
        resource_id = f"agent_config:{agent_id}"
        return await self.get(
            data_type="agent_config",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            use_memory=use_memory
        )

    async def set_agent_config(
        self,
        agent_id: str,
        config: Any,
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None,
        use_memory: bool = True
    ) -> bool:
        """
        Guarda la configuración del agente en cache.
        
        Args:
            agent_id: ID del agente
            config: Configuración a almacenar
            tenant_id: ID del tenant (opcional)
            ttl: Tiempo de vida en segundos (opcional, usa el valor predeterminado si no se proporciona)
            use_memory: Si se debe usar la caché en memoria
            
        Returns:
            bool: True si se guardó correctamente
        """
        tenant_id = tenant_id or get_current_tenant_id()
        resource_id = f"agent_config:{agent_id}"
        
        # Obtener TTL específico para configuraciones de agente desde el mapeo centralizado
        agent_config_ttl = ttl or DEFAULT_TTL_MAPPING.get("agent_config", TTL_STANDARD)
        
        return await self.set(
            data_type="agent_config",
            resource_id=resource_id,
            value=config,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ttl=agent_config_ttl,
            use_memory=use_memory
        )

    async def get_agent_response(
        self,
        agent_id: str,
        query: str,
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        use_memory: bool = True
    ) -> Optional[Any]:
        """
        Obtiene una respuesta de agente cacheada.
        
        Args:
            agent_id: ID del agente
            query: Consulta original
            tenant_id: ID del tenant (opcional)
            conversation_id: ID de la conversación (opcional)
            use_memory: Si se debe usar la caché en memoria
            
        Returns:
            Optional[Any]: Respuesta cacheada o None si no existe
        """
        tenant_id = tenant_id or get_current_tenant_id()
        conversation_id = conversation_id or get_current_conversation_id()
        query_hash = generate_resource_id_hash(query)
        resource_id = f"{agent_id}:{conversation_id}:{query_hash}"
        return await self.get(
            data_type="agent_response",
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            use_memory=use_memory
        )
    
    async def set_agent_response(
        self,
        agent_id: str,
        query: str,
        response: Any,
        tenant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        ttl: Optional[int] = None,
        use_memory: bool = True
    ) -> bool:
        """
        Guarda una respuesta de agente en cache.
        
        Args:
            agent_id: ID del agente
            query: Consulta original
            response: Respuesta a almacenar
            tenant_id: ID del tenant (opcional)
            conversation_id: ID de la conversación (opcional)
            ttl: Tiempo de vida en segundos (opcional, usa el valor predeterminado si no se proporciona)
            use_memory: Si se debe usar la caché en memoria
            
        Returns:
            bool: True si se guardó correctamente
        """
        tenant_id = tenant_id or get_current_tenant_id()
        conversation_id = conversation_id or get_current_conversation_id()
        query_hash = generate_resource_id_hash(query)
        resource_id = f"{agent_id}:{conversation_id}:{query_hash}"
        
        # Obtener TTL específico para respuestas de agente desde el mapeo centralizado
        agent_response_ttl = ttl or DEFAULT_TTL_MAPPING.get("agent_response", TTL_SHORT)
        
        return await self.set(
            data_type="agent_response",
            resource_id=resource_id,
            value=response,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=agent_response_ttl,
            use_memory=use_memory
        )
    
    async def get_conversation_messages(
        self,
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
        return await self.get(
            data_type="conversation_messages",
            resource_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id
        )
    
    async def set_conversation_messages(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Almacena los mensajes de una conversación en la caché.
        
        Args:
            conversation_id: ID de la conversación
            messages: Lista de mensajes a almacenar
            tenant_id, agent_id: Contexto opcional
            ttl: Tiempo de vida en segundos (opcional, usa el valor predeterminado si no se proporciona)
            
        Returns:
            bool: True si se guardó correctamente
        """
        # Obtener TTL específico para conversaciones desde el mapeo centralizado
        conversation_ttl = ttl or DEFAULT_TTL_MAPPING.get("conversation_messages", TTL_STANDARD)
        
        return await self.set(
            data_type="conversation_messages",
            resource_id=conversation_id,
            value=messages,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            ttl=conversation_ttl
        )

    async def increment_counter(
        self,
        counter_type: Optional[str] = None,
        amount: int = 0,
        resource_id: str = "total",
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        scope: Optional[str] = None
    ) -> int:
        """
        Incrementa un contador en caché y devuelve el nuevo valor.
        
        Args:
            counter_type: Tipo de contador ('token_usage', 'embedding_usage', 'api_call', etc.)
            amount: Cantidad a incrementar
            resource_id: ID del recurso específico (modelo, operación, etc.)
            tenant_id, agent_id, etc: Componentes contextuales
            token_type: Tipo de token si es un contador de tokens
            metadata: Metadatos adicionales del contador
            ttl: Tiempo de vida del contador en segundos (usar None para ttl_extended)
            scope: Alias de counter_type para compatibilidad con versiones anteriores
            
        Returns:
            int: Nuevo valor del contador
        """
        tenant_id = tenant_id or get_current_tenant_id()
        
        # Usar counter_type si está definido, o scope como fallback
        counter_type_to_use = counter_type or scope
        if not counter_type_to_use:
            logger.warning(f"Se debe proporcionar counter_type o scope para increment_counter")
            counter_type_to_use = "unknown"
        
        counter_key_parts = [tenant_id, f"counter:{counter_type_to_use}"]
        
        if token_type:
            counter_key_parts.append(f"type:{token_type}")
        if agent_id:
            counter_key_parts.append(f"agent:{agent_id}")
        if conversation_id:
            counter_key_parts.append(f"conv:{conversation_id}")
        if collection_id:
            counter_key_parts.append(f"coll:{collection_id}")
            
        counter_key_parts.append(resource_id)
        
        counter_key = ":".join(filter(None, counter_key_parts))
        
        redis_client = await get_redis_client()
        if not redis_client:
            logger.warning(f"Redis no disponible, no se puede incrementar contador {counter_key}")
            return amount  # Si no hay Redis, devolver el incremento como valor
        
        try:
            new_value = await redis_client.incrby(counter_key, amount)
            
            if new_value == amount:
                await redis_client.expire(
                    counter_key, 
                    ttl or self.ttl_extended
                )
            
            if metadata:
                metadata_key = f"{counter_key}:metadata"
                await redis_client.hset(metadata_key, mapping=metadata)
                await redis_client.expire(
                    metadata_key, 
                    ttl or self.ttl_extended
                )
            
            return new_value
        except Exception as e:
            logger.warning(f"Error incrementando contador {counter_key}: {str(e)}")
            return amount  # En caso de error, devolver el incremento
    
    @staticmethod
    async def increment_counter(
        scope: Optional[str] = None,
        amount: int = 0,
        resource_id: str = "total",
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        counter_type: Optional[str] = None,
        **kwargs  # Para capturar parámetros adicionales inesperados
    ) -> int:
        """
        Versión estática del método increment_counter para compatibilidad.
        
        Args:
            scope: (Obsoleto) Usar counter_type en su lugar. Se mantiene para compatibilidad.
            counter_type: Tipo de contador ('token_usage', 'embedding_usage', 'rate_limit', etc)
            amount: Cantidad a incrementar
            resource_id: ID del recurso específico (modelo, operación, etc.)
            tenant_id, agent_id, etc: Componentes contextuales
            token_type: Tipo de token si es un contador de tokens
            metadata: Metadatos adicionales
            ttl: Tiempo de vida en segundos
            
        Returns:
            int: Nuevo valor del contador
        """
        instance = CacheManager.get_instance()
        
        # Preferir counter_type sobre scope si ambos están presentes
        counter_type_to_use = counter_type or scope
        
        # Delegar al método de instancia con los parámetros adecuados
        return await instance.increment_counter(
            counter_type=counter_type_to_use,
            amount=amount,
            resource_id=resource_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            token_type=token_type,
            metadata=metadata,
            ttl=ttl
        )
    
    async def get_counter(
        self,
        scope: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: Optional[str] = None
    ) -> int:
        """
        Obtiene el valor de un contador.
        
        Args:
            scope: Tipo de contador
            resource_id: ID del recurso
            tenant_id, agent_id, etc: Componentes contextuales
            token_type: Tipo de token si es un contador de tokens
            
        Returns:
            int: Valor del contador
        """
        tenant_id = tenant_id or get_current_tenant_id()
        counter_key_parts = [tenant_id, f"counter:{scope}"]
        if token_type:
            counter_key_parts.append(f"type:{token_type}")
        if agent_id:
            counter_key_parts.append(f"agent:{agent_id}")
        if conversation_id:
            counter_key_parts.append(f"conv:{conversation_id}")
        if collection_id:
            counter_key_parts.append(f"coll:{collection_id}")
        counter_key_parts.append(resource_id)
        counter_key = ":".join(filter(None, counter_key_parts))
        redis_client = await get_redis_client()
        if not redis_client:
            return 0
        try:
            value = await redis_client.get(counter_key)
            return int(value) if value else 0
        except Exception as e:
            logger.warning(f"Error al obtener contador {counter_key}: {str(e)}")
            return 0
    
    async def ttl(
        self,
        data_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> int:
        """
        Obtiene el tiempo de vida restante en segundos de una clave en Redis.
        
        Args:
            data_type: Tipo de datos
            resource_id: ID del recurso
            tenant_id, agent_id, etc: Componentes contextuales de la clave
            
        Returns:
            int: Tiempo restante en segundos, -2 si la clave no existe, -1 si no tiene TTL
        """
        # Utilizar los valores de contexto actuales si no se proporcionan
        tenant_id = tenant_id or get_current_tenant_id()
        
        # Construir la clave
        key = CacheManager._build_key(
            data_type, resource_id, tenant_id, agent_id, 
            conversation_id, collection_id
        )
        
        # Obtener TTL de Redis
        redis_client = await get_redis_client()
        if not redis_client:
            return -2
            
        try:
            return await redis_client.ttl(key)
        except Exception as e:
            logger.warning(f"Error obteniendo TTL para {key}: {str(e)}")
            return -2

    async def invalidate_cache(
        self,
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
        pattern = ":".join(filter(None, pattern_parts))
        redis_client = await get_redis_client()
        keys = await redis_client.keys(f"{pattern}*")
        deleted = 0
        if keys:
            deleted += await redis_client.delete(*keys)
        to_delete = [k for k in _memory_cache if k.startswith(pattern)]
        for k in to_delete:
            _memory_cache.pop(k, None)
            _memory_expiry.pop(k, None)
            deleted += 1
        return deleted
    
    async def rpush(
        self,
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

    async def lpop(
        self,
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
    
    async def invalidate_agent_complete(self, tenant_id: str, agent_id: str) -> int:
        """
        Invalida todas las cachés relacionadas con un agente.
        """
        total_deleted = 0
        try:
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="agent_config",
                agent_id=agent_id,
            )
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="agent_response",
                agent_id=agent_id,
            )
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="conversation_messages",
                agent_id=agent_id,
            )
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="agent_stats",
                agent_id=agent_id,
            )
            logger.info(f"Caché completa de agente {agent_id} invalidada: {total_deleted} entradas")
        except Exception as e:
            logger.error(f"Error invalidando caché completa de agente: {str(e)}")
        return total_deleted
    
    async def invalidate_collection_complete(self, tenant_id: str, collection_id: str) -> int:
        """
        Invalida todas las cachés relacionadas con una colección.
        """
        total_deleted = 0
        try:
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="vector_store",
                collection_id=collection_id,
            )
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="query_result",
                collection_id=collection_id,
            )
            total_deleted += await self.invalidate(
                tenant_id=tenant_id,
                data_type="collection_stats",
                collection_id=collection_id,
            )
            logger.info(f"Caché completa de colección {collection_id} invalidada: {total_deleted} entradas")
        except Exception as e:
            logger.error(f"Error invalidando caché completa de colección: {str(e)}")
        return total_deleted
    
    @staticmethod
    async def invalidate_agent_complete(tenant_id: str, agent_id: str) -> int:
        """
        Método estático compatible que llama al método de instancia invalidate_agent_complete().
        """
        instance = CacheManager.get_instance()
        return await instance.invalidate_agent_complete(tenant_id, agent_id)
        
    @staticmethod
    async def invalidate_collection_complete(tenant_id: str, collection_id: str) -> int:
        """
        Método estático compatible que llama al método de instancia invalidate_collection_complete().
        """
        instance = CacheManager.get_instance()
        return await instance.invalidate_collection_complete(tenant_id, collection_id)
    
    @staticmethod
    async def lpop(queue_name: str) -> Optional[Any]:
        """
        Método estático compatible que llama al método de instancia lpop().
        """
        instance = CacheManager.get_instance()
        return await instance.lpop(queue_name)


    
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
        Método estático compatible que llama al método de instancia rpush().
        """
        instance = CacheManager.get_instance()
        return await instance.rpush(
            list_name=list_name,
            value=value,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id
        )
    
    @staticmethod
    async def get_counter(
        scope: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        token_type: str = "tokens"
    ) -> int:
        """
        Método estático compatible que llama al método de instancia get_counter().
        """
        instance = CacheManager.get_instance()
        return await instance.get_counter(
            scope, resource_id, tenant_id, agent_id, 
            conversation_id, collection_id, token_type
        )
    
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
        Versión estática del método ttl() para compatibilidad.
        """
        instance = CacheManager.get_instance()
        return await instance.ttl(
            data_type, resource_id, tenant_id, 
            agent_id, conversation_id, collection_id
        )
    
    async def add_to_set(
        self,
        set_name: str,
        value: str,
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> int:
        """
        Añade un valor a un conjunto (set) en Redis.
        
        Args:
            set_name: Nombre del conjunto
            value: Valor a añadir
            tenant_id: ID del tenant
            ttl: Tiempo de vida en segundos (None para ttl_extended)
            
        Returns:
            int: Número de elementos añadidos (0 si ya existía, 1 si se añadió)
        """
        tenant_id = tenant_id or get_current_tenant_id() or "system"
        
        key = f"{tenant_id}:set:{set_name}"
        
        redis_client = await get_redis_client()
        if not redis_client:
            logger.warning(f"Redis no disponible, no se puede añadir a conjunto {set_name}")
            return 0
            
        try:
            result = await redis_client.sadd(key, value)
            
            if ttl is not None or await redis_client.ttl(key) < 0:
                await redis_client.expire(key, ttl or self.ttl_extended)
                
            return result
        except Exception as e:
            logger.warning(f"Error añadiendo a conjunto {set_name}: {str(e)}")
            return 0
    
    async def remove_from_set(
        self,
        set_name: str,
        value: str,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Elimina un valor de un conjunto (set) en Redis.
        
        Args:
            set_name: Nombre del conjunto
            value: Valor a eliminar
            tenant_id: ID del tenant
            
        Returns:
            int: Número de elementos eliminados (0 si no existía, 1 si se eliminó)
        """
        tenant_id = tenant_id or get_current_tenant_id() or "system"
        
        key = f"{tenant_id}:set:{set_name}"
        
        redis_client = await get_redis_client()
        if not redis_client:
            logger.warning(f"Redis no disponible, no se puede eliminar de conjunto {set_name}")
            return 0
            
        try:
            return await redis_client.srem(key, value)
        except Exception as e:
            logger.warning(f"Error eliminando de conjunto {set_name}: {str(e)}")
            return 0
    
    async def get_set_members(
        self,
        set_name: str,
        tenant_id: Optional[str] = None
    ) -> List[str]:
        """
        Obtiene todos los miembros de un conjunto (set) en Redis.
        
        Args:
            set_name: Nombre del conjunto
            tenant_id: ID del tenant
            
        Returns:
            List[str]: Lista de miembros del conjunto
        """
        tenant_id = tenant_id or get_current_tenant_id() or "system"
        
        key = f"{tenant_id}:set:{set_name}"
        
        redis_client = await get_redis_client()
        if not redis_client:
            logger.warning(f"Redis no disponible, no se pueden obtener miembros de conjunto {set_name}")
            return []
            
        try:
            members = await redis_client.smembers(key)
            return list(members) if members else []
        except Exception as e:
            logger.warning(f"Error obteniendo miembros de conjunto {set_name}: {str(e)}")
            return []
    
    @staticmethod
    async def add_to_set(
        set_name: str,
        value: str,
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> int:
        """
        Versión estática de add_to_set.
        """
        instance = CacheManager.get_instance()
        return await instance.add_to_set(set_name, value, tenant_id, ttl)
    
    @staticmethod
    async def remove_from_set(
        set_name: str,
        value: str,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Versión estática de remove_from_set.
        """
        instance = CacheManager.get_instance()
        return await instance.remove_from_set(set_name, value, tenant_id)
    
    @staticmethod
    async def get_set_members(
        set_name: str,
        tenant_id: Optional[str] = None
    ) -> List[str]:
        """
        Versión estática de get_set_members.
        """
        instance = CacheManager.get_instance()
        return await instance.get_set_members(set_name, tenant_id)

    # Método _generate_hash eliminado - Usar generate_resource_id_hash() de helpers.py en su lugar