"""
Gestión de la memoria de contexto para agentes y conversaciones.
"""

import time
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Set, Union

from common.cache import AgentMemory

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
        self._memory = None
        self._agent_config = None
        self._collections = set()
        self._tools = {}
    
    # Registro de instancias para reutilización basada en claves de contexto
    _registry: Dict[Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]], "ContextManager"] = {}
    
    @classmethod
    def get_or_create(
        cls,
        tenant_id: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> "ContextManager":
        """
        Retorna una instancia única de ContextManager para el conjunto de IDs dado.
        Si no existe, la crea y la registra.
        """
        key = (tenant_id, agent_id, conversation_id, user_id, session_id)
        if key not in cls._registry:
            cls._registry[key] = cls(tenant_id, agent_id, conversation_id, user_id, session_id)
        return cls._registry[key]
    
    @property
    async def memory(self) -> AgentMemory:
        """
        Obtiene el objeto de memoria del agente.
        
        Returns:
            AgentMemory: Objeto para gestionar la memoria del agente
        """
        if not self._memory and self.agent_id:
            self._memory = AgentMemory(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                session_id=self.session_id
            )
            
            # Cargar colecciones desde la memoria
            if self._memory:
                collections = await self._memory.get_collections()
                self._collections.update(collections)
        
        return self._memory
    
    async def get_agent_config(self) -> Dict[str, Any]:
        """
        Obtiene la configuración del agente.
        
        Returns:
            Dict[str, Any]: Configuración completa del agente
        """
        if not self.agent_id:
            return {}
        
        if not self._agent_config:
            # Cargar desde Supabase
            from ..db.supabase import get_supabase_client
            from ..db.tables import get_table_name
            
            supabase = get_supabase_client()
            
            result = await supabase.table(get_table_name("agent_configs")) \
                .select("*") \
                .eq("agent_id", self.agent_id) \
                .eq("tenant_id", self.tenant_id) \
                .execute()
            
            if result.data:
                self._agent_config = result.data[0]
                
                # Registrar colecciones del agente
                if "tools" in self._agent_config:
                    tools = self._agent_config["tools"]
                    if isinstance(tools, list):
                        for tool in tools:
                            if tool.get("type") == "rag" and "metadata" in tool:
                                coll_id = tool["metadata"].get("collection_id")
                                if coll_id:
                                    self._collections.add(coll_id)
                                    
                                    # Registrar en memoria también
                                    memory = await self.memory
                                    if memory:
                                        await memory.register_collection(coll_id)
        
        return self._agent_config or {}
    
    async def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Añade un mensaje del usuario a la conversación.
        
        Args:
            content: Contenido del mensaje
            metadata: Metadatos adicionales
            
        Returns:
            str: ID del mensaje
        """
        message_id = str(uuid.uuid4())
        
        memory = await self.memory
        if memory:
            await memory.add_message({
                "role": "user",
                "content": content,
                "timestamp": time.time(),
                "message_id": message_id,
                "metadata": metadata or {}
            })
        
        return message_id
    
    async def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Añade un mensaje del asistente a la conversación.
        
        Args:
            content: Contenido del mensaje
            metadata: Metadatos adicionales
            
        Returns:
            str: ID del mensaje
        """
        message_id = str(uuid.uuid4())
        
        memory = await self.memory
        if memory:
            await memory.add_message({
                "role": "assistant",
                "content": content,
                "timestamp": time.time(),
                "message_id": message_id,
                "metadata": metadata or {}
            })
        
        return message_id
    
    async def get_context_summary(self) -> Dict[str, Any]:
        """
        Obtiene un resumen del contexto actual para diagnóstico.
        
        Returns:
            Dict[str, Any]: Resumen de contexto
        """
        memory = await self.memory
        history = await memory.get_conversation_history() if memory else []
        
        collections = list(self._collections)
        if not collections and memory:
            collections = await memory.get_collections()
        
        agent_config = await self.get_agent_config()
        
        return {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "collections": collections,
            "agent_type": agent_config.get("agent_type") if agent_config else None,
            "message_count": len(history),
            "tools_configured": len(agent_config.get("tools", [])) if agent_config else 0
        }
    
    async def get_conversation_history(
        self, 
        format_for_llm: bool = False,
        max_messages: Optional[int] = None
    ) -> Union[List[Dict[str, Any]], str]:
        """
        Obtiene el historial de conversación.
        
        Args:
            format_for_llm: Si se debe formatear para entrada a LLM
            max_messages: Número máximo de mensajes a incluir
            
        Returns:
            Union[List[Dict[str, Any]], str]: Historial formateado o lista de mensajes
        """
        memory = await self.memory
        history = await memory.get_conversation_history() if memory else []
        
        if max_messages:
            history = history[-max_messages:]
        
        if format_for_llm:
            formatted = []
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                formatted.append(f"{role.capitalize()}: {content}")
            
            return "\n\n".join(formatted)
        
        return history
    
    async def register_tool_use(self, tool_id: str, input_data: Any, result: Any) -> None:
        """
        Registra el uso de una herramienta durante la conversación.
        
        Args:
            tool_id: ID de la herramienta
            input_data: Datos de entrada
            result: Resultado de la herramienta
        """
        memory = await self.memory
        if memory:
            await memory.update_tool_state(tool_id, {
                "last_used": time.time(),
                "last_input": input_data,
                "last_result": result,
                "usage_count": self._tools.get(tool_id, {}).get("usage_count", 0) + 1
            })
            
            # Actualizar cache local
            if tool_id not in self._tools:
                self._tools[tool_id] = {}
            
            self._tools[tool_id]["usage_count"] = self._tools.get(tool_id, {}).get("usage_count", 0) + 1
    
    async def get_rag_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Obtiene contexto RAG para una consulta.
        
        Args:
            query: Consulta de usuario
            limit: Número máximo de resultados
            
        Returns:
            List[Dict[str, Any]]: Contexto encontrado
        """
        if not self._collections:
            return []
        
        results = []
        try:
            from ..utils.http import call_service
            from ..config.settings import get_settings
            
            settings = get_settings()
            
            for collection_id in self._collections:
                # Llamar al servicio de query con la nueva función estandarizada
                response = await call_service(
                    url=f"{settings.query_service_url}/internal/search",
                    data={
                        "tenant_id": self.tenant_id,
                        "query": query,
                        "collection_id": collection_id,
                        "limit": limit
                    },
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    conversation_id=self.conversation_id,
                    collection_id=collection_id,
                    operation_type="rag_search",
                    use_cache=True,  # Aprovechar caché para consultas recientes
                    cache_ttl=1800  # 30 minutos de TTL para resultados RAG
                )
                
                # Verificar éxito y extraer datos según el formato estandarizado
                if response.get("success", False) and response.get("data") is not None:
                    response_data = response.get("data", {})
                    if "results" in response_data:
                        results.extend(response_data["results"])
        except Exception as e:
            logger.error(f"Error obteniendo contexto RAG: {str(e)}")
        
        # Limitar a los mejores resultados
        if len(results) > limit:
            # Ordenar por relevancia
            results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
            results = results[:limit]
        
        return results