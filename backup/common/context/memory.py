"""
Gestión de la memoria de contexto para agentes y conversaciones.
"""

import time
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Set, Union

# Eliminamos la importación circular
# from common.cache import AgentMemory
from common.cache import CacheManager, get_with_cache_aside, generate_resource_id_hash

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Gestiona el contexto de ejecución entre diferentes solicitudes y servicios.
    
    Esta clase es el punto de entrada principal para trabajar con contexto
    en toda la plataforma, integrando:
    - Memoria de agente
    - Propagación de contexto entre servicios
    - Información de usuario/sesión
    - Estado de herramientas
    """
    
    # Registro centralizado de instancias
    _registry = {}
    
    def __init__(
        self,
        tenant_id: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.session_id = session_id
        self._collections = set()
        
    @classmethod
    def get_instance(
        cls,
        tenant_id: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> 'ContextManager':
        """
        Obtiene una instancia única del gestor de contexto.
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            user_id: ID del usuario
            session_id: ID de la sesión
            
        Returns:
            ContextManager: Instancia única
        """
        key = (tenant_id, agent_id, conversation_id, user_id, session_id)
        if key not in cls._registry:
            cls._registry[key] = cls(tenant_id, agent_id, conversation_id, user_id, session_id)
        return cls._registry[key]
    
    async def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de la conversación actual.
        
        Returns:
            List[Dict[str, Any]]: Lista de mensajes
        """
        # Definir identificador único para esta conversación
        conversation_resource_id = f"conversation:{self.conversation_id}"
        
        # Obtener IDs de mensajes
        message_ids = await CacheManager.get(
            data_type="conversation_messages",
            resource_id=conversation_resource_id,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        ) or []
        
        # Obtener contenido de cada mensaje
        messages = []
        for msg_id in message_ids:
            message = await CacheManager.get(
                data_type="agent_message",
                resource_id=msg_id,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id
            )
            if message:
                messages.append(message)
        
        return messages
    
    async def add_message(self, message: Dict[str, Any]) -> str:
        """
        Añade un mensaje a la conversación actual.
        
        Args:
            message: Mensaje a añadir, con campos role, content, etc.
            
        Returns:
            str: ID del mensaje
        """
        # Generar ID único para el mensaje
        message_id = str(uuid.uuid4())
        
        # Guardar el mensaje en caché
        await CacheManager.set(
            data_type="agent_message",
            resource_id=message_id,
            value=message,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        )
        
        # Añadir a la lista de mensajes de la conversación
        conversation_resource_id = f"conversation:{self.conversation_id}"
        messages_list = await CacheManager.get(
            data_type="conversation_messages",
            resource_id=conversation_resource_id,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        ) or []
        
        messages_list.append(message_id)
        
        await CacheManager.set(
            data_type="conversation_messages",
            resource_id=conversation_resource_id,
            value=messages_list,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        )
        
        return message_id
    
    async def register_collection(self, collection_id: str) -> None:
        """
        Registra una colección como usada en esta conversación.
        
        Args:
            collection_id: ID de la colección
        """
        # Añadir a la lista interna
        self._collections.add(collection_id)
        
        # Guardar en caché
        collection_resource_id = f"collection:{collection_id}"
        await CacheManager.set(
            data_type="agent_collection",
            resource_id=collection_resource_id,
            value={"collection_id": collection_id, "last_accessed": time.time()},
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        )
    
    async def get_collections(self) -> Set[str]:
        """
        Obtiene las colecciones registradas para esta conversación.
        
        Returns:
            Set[str]: Conjunto de IDs de colecciones
        """
        # Si ya tenemos colecciones en memoria, devolverlas
        if self._collections:
            return self._collections
        
        # Buscar colecciones en caché
        collections_pattern = f"agent_collection:*"
        collection_keys = await CacheManager.get_keys_by_pattern(
            pattern=collections_pattern,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            conversation_id=self.conversation_id
        )
        
        # Extraer IDs de colecciones
        for key in collection_keys:
            # Formato esperado: agent_collection:collection:{collection_id}
            parts = key.split(':')
            if len(parts) >= 3:
                collection_id = parts[2]
                self._collections.add(collection_id)
        
        return self._collections
    
    def clear(self) -> None:
        """Limpia el contexto actual"""
        self._collections = set()
        
        # Eliminar de registro centralizado
        key = (self.tenant_id, self.agent_id, self.conversation_id, self.user_id, self.session_id)
        if key in self._registry:
            del self._registry[key]