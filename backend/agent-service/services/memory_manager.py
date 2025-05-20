"""
Gestor de memoria de conversación para el Agent Service.

Implementa el patrón Cache-Aside para optimizar el acceso a la memoria de conversación.
"""

import logging
import time
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List

from common.cache import CacheManager, get_with_cache_aside
from common.context.decorators import with_context, Context
from common.errors.handlers import handle_errors
from common.config import get_settings
from common.tracking import track_cache_metrics, track_token_usage
from common.cache.helpers import standardize_llama_metadata, serialize_for_cache
from common.langchain import standardize_langchain_metadata
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

logger = logging.getLogger(__name__)

class ConversationMemoryManager:
    # Constante para identificar el tipo de dato
    MEMORY_DATA_TYPE = "conversation_memory"
    """
    Gestor de memoria de conversación con integración Cache-Aside.
    
    Esta clase maneja la persistencia y recuperación de memoria de conversación,
    utilizando el patrón Cache-Aside para optimizar rendimiento.
    """
    
    def __init__(self, service_registry):
        """Inicializa el gestor de memoria con acceso al registro de servicios."""
        self.service_registry = service_registry
        self.settings = get_settings()
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Dict[str, Any]:
        """
        Recupera memoria de conversación usando Cache-Aside pattern.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            ctx: Contexto opcional con metadata adicional
            
        Returns:
            Diccionario con memoria de conversación
            
        Raises:
            ValueError: Si no se proporciona tenant_id válido
            ServiceError: Si hay errores en el acceso a la caché o BD
        """
        memory_dict, metrics = await get_with_cache_aside(
            data_type="conversation_memory",
            resource_id=conversation_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_memory_from_db,
            generate_func=self._create_empty_memory,
            agent_id=ctx.get_agent_id() if ctx else None,
            conversation_id=conversation_id,
            ttl=CacheManager.ttl_extended  # 24 horas para persistencia
        )
        
        # Registrar métricas de caché para análisis de rendimiento
        await track_cache_metrics(
            data_type="conversation_memory", 
            tenant_id=tenant_id, 
            operation="get", 
            hit=metrics.get("cache_hit", False), 
            latency_ms=metrics.get("latency_ms", 0)
        )
        
        # Monitorear tamaño de objetos en caché
        if memory_dict:
            memory_size = len(str(memory_dict))  # Estimación simple del tamaño
            await self._track_cache_size("conversation_memory", tenant_id, memory_size)
        
        # Estandarizar metadatos si existen
        if "metadata" in memory_dict:
            standardized_metadata = standardize_llama_metadata(
                metadata=memory_dict.get("metadata", {}),
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                agent_id=ctx.get_agent_id() if ctx else None
            )
            memory_dict["metadata"] = standardized_metadata
        
        return memory_dict
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _fetch_memory_from_db(self, conversation_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera memoria desde Supabase.
        
        Args:
            conversation_id: ID de la conversación
            tenant_id: ID del tenant
            
        Returns:
            Diccionario con memoria o None si no existe
        """
        try:
            table_name = self.settings.TABLES["conversation_memories"]
            supabase = get_supabase_client()
            
            result = (supabase.table(table_name)
                     .select("*")
                     .eq("tenant_id", tenant_id)
                     .eq("conversation_id", conversation_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            return None
        except Exception as e:
            logger.error(f"Error recuperando memoria de BD: {str(e)}")
            return None
    
    def _create_empty_memory(self) -> Dict[str, Any]:
        """Crea estructura vacía de memoria."""
        return {
            "messages": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "message_count": 0,
                "last_updated": datetime.now().isoformat()
            }
        }
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def save_memory(self, tenant_id: str, conversation_id: str, memory_dict: Dict[str, Any], ctx: Context = None) -> None:
        """
        Guarda memoria en caché y opcionalmente en BD.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            memory_dict: Diccionario con memoria a guardar
            ctx: Contexto opcional
            
        Raises:
            ValueError: Si no se proporciona tenant_id válido
            ServiceError: Si hay errores en el acceso a la caché o BD
        """
        # Actualizar metadata
        if "metadata" not in memory_dict:
            memory_dict["metadata"] = {}
            
        memory_dict["metadata"]["last_updated"] = datetime.now().isoformat()
        memory_dict["metadata"]["message_count"] = len(memory_dict.get("messages", []))
        
        # Estandarizar metadatos
        standardized_metadata = standardize_llama_metadata(
            metadata=memory_dict["metadata"],
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            agent_id=ctx.get_agent_id() if ctx else None
        )
        memory_dict["metadata"] = standardized_metadata
        
        # Guardar en caché (siempre)
        start_time = time.time()
        await CacheManager.set(
            data_type="conversation_memory",
            resource_id=conversation_id,
            value=memory_dict,
            tenant_id=tenant_id,
            agent_id=ctx.get_agent_id() if ctx else None,
            conversation_id=conversation_id,
            ttl=CacheManager.ttl_extended
        )
        
        # Registrar métricas
        latency_ms = (time.time() - start_time) * 1000
        await track_cache_metrics(
            data_type="conversation_memory", 
            tenant_id=tenant_id, 
            operation="set", 
            hit=True, 
            latency_ms=latency_ms
        )
        
        # Monitorear tamaño de objetos en caché
        memory_size = len(str(memory_dict))  # Estimación simple del tamaño
        await self._track_cache_size("conversation_memory", tenant_id, memory_size)
        
        # Persistir en DB si es necesario (por ejemplo, cada N mensajes)
        memory_config = getattr(self.settings, "MEMORY_CONFIG", {})
        message_count = memory_dict["metadata"]["message_count"]
        
        persist_frequency = memory_config.get("PERSIST_FREQUENCY", 5)  # Valor por defecto: cada 5 mensajes
        if message_count % persist_frequency == 0:
            await self._persist_memory_to_db(tenant_id, conversation_id, memory_dict, ctx)
    
    async def _track_cache_size(self, data_type: str, tenant_id: str, size_bytes: int):
        """Monitorea el tamaño de objetos en caché y genera alertas si es necesario.
        
        Args:
            data_type: Tipo de datos
            tenant_id: ID del tenant
            size_bytes: Tamaño estimado en bytes
        """
        try:
            # Threshold para generar alertas (500KB)
            size_threshold = 500 * 1024
            
            if size_bytes > size_threshold:
                logger.warning(
                    f"Large object in cache: {data_type} for tenant {tenant_id}",
                    extra={
                        "tenant_id": tenant_id,
                        "data_type": data_type,
                        "size_bytes": size_bytes,
                        "threshold_bytes": size_threshold
                    }
                )
            
            # Registrar métrica de tamaño para análisis de rendimiento
            await track_performance_metric(
                metric_type="cache_object_size",
                value=size_bytes,
                tenant_id=tenant_id,
                metadata={
                    "data_type": data_type,
                    "size_kb": round(size_bytes / 1024, 2)
                }
            )
            
            # Log para monitoreo si el tamaño supera umbrales
            if size_bytes > 1024 * 1024:  # 1MB
                logger.warning(
                    f"Large cache object detected: {size_bytes/1024/1024:.2f}MB",
                    extra={
                        "tenant_id": tenant_id,
                        "data_type": data_type,
                        "size_mb": size_bytes/1024/1024
                    }
                )
        except Exception as e:
            # No interrumpir el flujo principal si falla el tracking
            logger.error(f"Error tracking cache size: {str(e)}")
            
    @handle_errors(error_type="service", log_traceback=True)
    async def _persist_memory_to_db(self, tenant_id: str, conversation_id: str, memory_dict: Dict[str, Any], ctx: Context = None):
        """
        Persiste la memoria en la base de datos.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            memory_dict: Diccionario con memoria a persistir
            ctx: Contexto opcional
        """
        try:
            start_time = time.time()
            
            # Usar formato estandarizado para nombres de tablas
            table_name = get_table_name("conversation_memories")
            supabase = get_supabase_client()
            
            # Buscar si ya existe
            result = await supabase.table(table_name)\
                .select("id")\
                .eq("tenant_id", tenant_id)\
                .eq("conversation_id", conversation_id)\
                .execute()
                
            # Preparar datos para inserción/actualización
            memory_data = {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "memory": memory_dict,
                "updated_at": datetime.now().isoformat(),
                "agent_id": ctx.get_agent_id() if ctx else memory_dict.get("metadata", {}).get("agent_id")
            }
            
            # Crear o actualizar
            if result.data and len(result.data) > 0:
                # Actualizar registro existente
                await supabase.table(table_name)\
                    .update(memory_data)\
                    .eq("tenant_id", tenant_id)\
                    .eq("conversation_id", conversation_id)\
                    .execute()
            else:
                # Crear nuevo registro
                memory_data["id"] = str(uuid.uuid4())
                memory_data["created_at"] = datetime.now().isoformat()
                await supabase.table(table_name).insert(memory_data).execute()
                
            # Registrar métricas
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Memory persisted to DB: {conversation_id}",
                extra={
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "execution_time": latency_ms,
                    "message_count": memory_dict.get("metadata", {}).get("message_count", 0)
                }
            )
        except Exception as e:
            logger.error(f"Error persistiendo memoria en BD: {str(e)}")
            # No lanzar la excepción para no interrumpir el flujo principal
            
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def add_message(self, tenant_id: str, conversation_id: str, role: str, content: str, 
                      metadata: Optional[Dict[str, Any]] = None, ctx: Context = None) -> str:
        """
        Añade un mensaje a la conversación con almacenamiento optimizado en caché.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            role: Rol del mensaje (user, assistant, system)
            content: Contenido del mensaje
            metadata: Metadatos adicionales del mensaje
            ctx: Contexto opcional
            
        Returns:
            str: ID del mensaje creado
            
        Raises:
            ValueError: Si no se proporciona tenant_id válido
            ServiceError: Si hay errores en el acceso a la caché o BD
        """
        # Generar ID de mensaje
        message_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Crear datos del mensaje
        message_data = {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": timestamp,
            "metadata": metadata or {}
        }
        
        # Estandarizar metadatos
        standardized_metadata = standardize_langchain_metadata(
            metadata=message_data["metadata"],
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            agent_id=ctx.get_agent_id() if ctx else None,
            ctx=ctx
        )
        message_data["metadata"] = standardized_metadata
        
        # Almacenar mensaje individual en caché (SET regular)
        start_time = time.time()
        await CacheManager.set(
            data_type="conversation_message",
            resource_id=message_id,
            value=message_data,
            tenant_id=tenant_id,
            conversation_id=conversation_id,  # Para agrupación jerárquica
            ttl=CacheManager.ttl_extended  # 24 horas para mensajes
        )
        
        # IMPORTANTE: Usar métodos de instancia para operaciones de lista
        await CacheManager.get_instance().rpush(
            list_name=f"{tenant_id}:{conversation_id}:messages",
            value=message_data,
            tenant_id=tenant_id  # Pasar tenant_id para segmentación
        )
        
        # Registrar métricas
        latency_ms = (time.time() - start_time) * 1000
        await track_cache_metrics(
            data_type="conversation_message", 
            tenant_id=tenant_id, 
            operation="add", 
            hit=True, 
            latency_ms=latency_ms
        )
        
        # Actualizar en base de datos (async)
        await self._store_message_in_db(tenant_id, conversation_id, message_data)
        
        return message_id
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _store_message_in_db(self, tenant_id: str, conversation_id: str, message_data: Dict[str, Any]) -> None:
        """
        Almacena un mensaje individual en la base de datos.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            message_data: Datos del mensaje
        """
        try:
            table_name = self.settings.TABLES["conversation_messages"]
            supabase = await get_supabase_client()
            
            # Preparar registro para BD
            record = {
                "id": message_data["id"],
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "role": message_data["role"],
                "content": message_data["content"],
                "created_at": message_data["created_at"],
                "metadata": message_data["metadata"]
            }
            
            # Insertar mensaje
            await supabase.table(table_name).insert(record).execute()
            
            logger.debug(f"Mensaje almacenado en BD: {message_data['id']}", 
                       extra={"tenant_id": tenant_id, "conversation_id": conversation_id})
        except Exception as e:
            # Log del error pero no interrumpir el flujo
            logger.warning(f"Error almacenando mensaje en BD: {str(e)}", 
                        extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "error": str(e)})
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_messages(self, tenant_id: str, conversation_id: str, limit: int = 50, 
                       skip: int = 0, ctx: Context = None) -> List[Dict[str, Any]]:
        """
        Recupera mensajes de la conversación desde caché con fallback a BD.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            limit: Número máximo de mensajes a obtener
            skip: Número de mensajes a omitir (para paginación)
            ctx: Contexto opcional
            
        Returns:
            Lista de mensajes ordenados cronológicamente
            
        Raises:
            ValueError: Si no se proporciona tenant_id válido
            ServiceError: Si hay errores en el acceso a la caché o BD
        """
        start_time = time.time()
        cache_hit = False
        
        # Intentar obtener de la lista en Redis (usar método de instancia)
        try:
            # Calcular índices para LRANGE (end=-1 significa hasta el final)
            start = skip
            end = (skip + limit - 1) if limit > 0 else -1
            
            # CORRECTO: Operación con listas mediante get_instance()
            messages = await CacheManager.get_instance().lrange(
                list_name=f"{tenant_id}:{conversation_id}:messages",
                start=start,
                end=end,
                tenant_id=tenant_id  # Pasar tenant_id para segmentación
            )
            
            if messages:
                cache_hit = True
                
                # Registrar métricas
                latency_ms = (time.time() - start_time) * 1000
                await track_cache_metrics(
                    data_type="conversation_messages", 
                    tenant_id=tenant_id, 
                    operation="get", 
                    hit=True, 
                    latency_ms=latency_ms
                )
                
                return messages
        except Exception as e:
            logger.warning(f"Error obteniendo mensajes de caché: {str(e)}",
                        extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "error": str(e)})
        
        # Si no está en caché, recuperar de la base de datos
        messages = await self._fetch_messages_from_db(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            limit=limit,
            skip=skip
        )
        
        # Reconstruir caché si se obtuvieron mensajes
        if messages:
            await self._rebuild_message_cache(tenant_id, conversation_id, messages)
        
        # Registrar métricas
        latency_ms = (time.time() - start_time) * 1000
        await track_cache_metrics(
            data_type="conversation_messages", 
            tenant_id=tenant_id, 
            operation="get", 
            hit=cache_hit, 
            latency_ms=latency_ms
        )
        
        return messages
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _fetch_messages_from_db(self, tenant_id: str, conversation_id: str, 
                                  limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Recupera mensajes desde la base de datos.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            limit: Número máximo de mensajes a obtener
            skip: Número de mensajes a omitir (para paginación)
            
        Returns:
            Lista de mensajes ordenados cronológicamente
        """
        try:
            table_name = self.settings.TABLES["conversation_messages"]
            supabase = await get_supabase_client()
            
            result = await supabase.table(table_name)\
                .select("*")\
                .eq("tenant_id", tenant_id)\
                .eq("conversation_id", conversation_id)\
                .order("created_at")\
                .range(skip, skip + limit - 1)\
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error recuperando mensajes de BD: {str(e)}",
                       extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "error": str(e)})
            return []
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _rebuild_message_cache(self, tenant_id: str, conversation_id: str, 
                                 messages: List[Dict[str, Any]]) -> None:
        """
        Reconstruye la caché de mensajes a partir de datos de la BD.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            messages: Lista de mensajes a almacenar en caché
        """
        try:
            # Limpiar lista existente (si hay)
            await CacheManager.get_instance().delete(
                key=f"{tenant_id}:{conversation_id}:messages",
                tenant_id=tenant_id
            )
            
            # Añadir cada mensaje a la lista y también individualmente
            for message in messages:
                # Almacenar mensaje individual en caché
                await CacheManager.set(
                    data_type="conversation_message",
                    resource_id=message["id"],
                    value=message,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    ttl=CacheManager.ttl_extended
                )
                
                # Añadir a la lista
                await CacheManager.get_instance().rpush(
                    list_name=f"{tenant_id}:{conversation_id}:messages",
                    value=message,
                    tenant_id=tenant_id
                )
            
            logger.debug(f"Caché de mensajes reconstruida: {conversation_id}",
                        extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "count": len(messages)})
        except Exception as e:
            logger.warning(f"Error reconstruyendo caché de mensajes: {str(e)}",
                         extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "error": str(e)})
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _persist_memory_to_db(self, tenant_id: str, conversation_id: str, memory_dict: Dict[str, Any]) -> None:
        """
        Persiste memoria a la base de datos.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            memory_dict: Diccionario con memoria a persistir
        """
        try:
            table_name = self.settings.TABLES["conversation_memories"]
            supabase = await get_supabase_client()
            
            # Preparar registro para BD
            record = {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "messages": memory_dict.get("messages", []),
                "metadata": memory_dict.get("metadata", {}),
                "updated_at": datetime.now().isoformat()
            }
            
            # Verificar si existe o es nuevo
            result = (await supabase.table(table_name)
                     .select("conversation_id")
                     .eq("tenant_id", tenant_id)
                     .eq("conversation_id", conversation_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                # Actualizar existente
                await supabase.table(table_name)\
                    .update(record)\
                    .eq("tenant_id", tenant_id)\
                    .eq("conversation_id", conversation_id)\
                    .execute()
            else:
                # Insertar nuevo
                record["created_at"] = datetime.now().isoformat()
                await supabase.table(table_name).insert(record).execute()
                
            logger.info(f"Memoria persistida en BD: {conversation_id}", 
                       extra={"tenant_id": tenant_id, "conversation_id": conversation_id})
                       
        except Exception as e:
            # Log del error pero no re-levantar la excepción para no interrumpir el flujo
            logger.error(f"Error persistiendo memoria en BD: {str(e)}", 
                        extra={"tenant_id": tenant_id, "conversation_id": conversation_id, "error": str(e)})
