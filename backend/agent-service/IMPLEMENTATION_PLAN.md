# Plan de Implementación: Agent Service y Refactorización de Microservicios

## Visión General

Este documento detalla el plan para implementar el servicio de agentes (Agent Service) y refactorizar los servicios existentes en la arquitectura RAG de Nooble3, respetando los patrones y estándares ya establecidos.

**Responsable:** Equipo de Backend  
**Fecha de Inicio:** Mayo 2025  
**Duración Estimada:** 3 semanas  

## Arquitectura Objetivo

```
+------------------+
|  Cliente (Web)   |
+--------+---------+
         |
+--------v---------+
|  Agent Service   | <-- Orquestador Central
+--+------+-----+--+
   |      |     |
   |      |     |
+--v--+ +-v--+ +-v---+
|Query| |Emb.| |Ing. |
|Serv.| |Serv| |Serv.|
+-----+ +----+ +-----+
   |      |       |
   v      v       v
+--------------------+
|     Supabase       |
+--------------------+
```

### Principios Arquitectónicos Clave

- **Especialización de Servicios**:
  - Query Service: Exclusivamente Groq para procesamiento LLM
  - Embedding Service: Exclusivamente OpenAI para generación de embeddings
  - Agent Service: Orquestador que dirige el flujo entre servicios

- **Flujos de Comunicación Permitidos**:
  - ✅ Agent Service → Query Service
  - ✅ Agent Service → Embedding Service
  - ✅ Ingestion Service → Embedding Service
  - ❌ Query Service → Embedding Service (prohibido)

### Arquitectura Extendida para Multi-Agente e Integraciones

- **Sistema Multi-Agente**:
  - Soporte para comunicación y colaboración entre agentes
  - Ruteo inteligente de tareas entre agentes especializados
  - Contexto compartido y propagación de estado entre agentes

- **Extensibilidad de Fuentes de Datos**:
  - Acceso a múltiples colecciones de documentos simultáneamente
  - Selección explícita de colecciones por defecto, con opción de selección dinámica opcional
  - Federación de resultados de múltiples colecciones cuando se activa explícitamente

- **Framework de Integraciones Externas**:
  - Integraciones de comunicación: Email, WhatsApp, Instagram, Telegram
  - Integraciones con APIs externas: CRMs, ERPs, plataformas SaaS
  - Sistema plug-in para añadir nuevas integraciones sin modificar el core

- **Gestión de Contexto Expandida**:
  - Contexto compartido entre agentes colaborativos
  - Historial de conversaciones multi-canal
  - Propagación de contexto a través de integraciones externas

## 1. Fase 1: Implementación del Agent Service (Semana 1)

### 1.1 Actualización de Dependencias
- [ ] Actualizar `requirements.txt` para incluir:
  - LangChain ≥ 0.1.0
  - LangChain-Core ≥ 0.1.0
  - LangChain-Community ≥ 0.0.10
  - Pydantic ≥ 2.0.0

### 1.2 Implementación de LangChainAgentService
- [ ] Completar implementación en `services/langchain_agent_service.py`:
  - [ ] Integración con LCEL (LangChain Expression Language)
  - [ ] Soporte para ReAct como patrón de razonamiento
  - [ ] Carga dinámica de herramientas basada en configuración
  - [ ] Tracking de tokens y métricas
  - [ ] Integración con sistema de contexto expandido
  - [ ] Patrón Cache-Aside para configuraciones
  - [ ] **Soporte para comunicación multi-agente**
  - [ ] **Selección dinámica de colecciones**
  - [ ] **Integración con sistemas externos**

```python
# Ejemplo de implementación con LCEL y soporte multi-agente
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.conversation.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor
from common.context import Context
from common.errors.handlers import handle_errors
from common.cache import CacheManager, get_with_cache_aside
from typing import Dict, List, Any, Optional, Tuple

class LangChainAgentService:
    def __init__(self):
        self.service_registry = None
        self.agent_registry = {}  # Registro de agentes disponibles por tenant
        self.integration_registry = {}  # Registro de integraciones disponibles
        
        # Inicializar lock para control de concurrencia en operaciones del registro
        import asyncio
        self.registry_lock = asyncio.Lock()
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        ValueError: {"code": "invalid_context", "status_code": 400},
        TierLimitExceededError: {"code": "tier_limit_exceeded", "status_code": 402}
    })
    async def register_agent(self, tenant_id: str, agent_id: str, agent_config: Dict[str, Any], ctx: Context = None) -> None:
        """Registra un agente en el tenant
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID del agente
            agent_config: Configuración del agente
            ctx: Contexto con tenant_id
            
        Returns:
            None
        """
        # Validar contexto
        if not ctx or not ctx.get_tenant_id():
            raise ValueError("Contexto con tenant_id requerido")
        
        async with self.registry_lock:
            # Inicializar registro de tenant si no existe
            if tenant_id not in self.agent_registry:
                self.agent_registry[tenant_id] = {}
                
            # Validar límites de tier
            await self._validate_agent_tier_limits(tenant_id, ctx)
            
            # Registrar agente en memoria
            self.agent_registry[tenant_id][agent_id] = agent_config
        
        # Almacenar configuración en caché usando patrón cache-aside estandarizado
        from common.cache import CacheManager
        from common.cache.serialize import serialize_for_cache
        
        # Serializar para almacenamiento en caché
        serialized_config = serialize_for_cache(agent_config)
        
        # Guardar en caché con TTL estándar
        await CacheManager.set(
            data_type="agent_config",
            resource_id=agent_id,
            value=serialized_config,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard  # 1 hora según estándares
        )
        
        # También almacenar en Supabase para persistencia
        from common.db.supabase import get_supabase_client, get_table_name
        
        try:
            # Preparar registro para almacenamiento
            agent_record = {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "config": agent_config,
                "updated_at": datetime.now().isoformat()
            }
            
            # Obtener cliente Supabase
            supabase = get_supabase_client(tenant_id=tenant_id)
            table_name = get_table_name("agent_configs")
            
            # Insertar o actualizar config de agente
            await supabase.table(table_name).upsert(agent_record).execute()
        except Exception as e:
            logger.error(f"Error al guardar configuración de agente en Supabase: {str(e)}")
            # No propagamos el error para que al menos quede en caché
        
        # Informar sobre registro exitoso
        logger.info(f"Agente {agent_id} registrado para tenant {tenant_id}")
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        ValueError: {"code": "invalid_context", "status_code": 400},
        InvalidConfigError: {"code": "invalid_config", "status_code": 400}
    })
    async def create_agent(self, agent_config: AgentConfig, ctx: Context = None) -> str:
        """Crea un agente LCEL con configuración dinámica
        
        Args:
            agent_config: Configuración del agente
            ctx: Contexto con tenant_id
            
        Returns:
            ID del agente creado
            
        Raises:
            InvalidConfigError: Si la configuración es inválida
            ValueError: Si falta el contexto requerido
        """
        # Validar ctx y obtener tenant_id usando el patrón estándar
        if not ctx:
            raise ValueError("Contexto requerido para crear agente")
            
        tenant_id = ctx.get_tenant_id()
            
        # Generar ID del agente si no existe
        agent_id = agent_config.agent_id or str(uuid.uuid4())
        
        # Validar colecciones asignadas al agente
        if agent_config.collection_ids:
            for collection_id in agent_config.collection_ids:
                # Verificar que la colección existe para el tenant
                exists = await self._verify_collection_exists(tenant_id, collection_id)
                if not exists:
                    raise ValueError(f"Colección {collection_id} no existe para el tenant")
        
        # Validar integraciones asignadas al agente
        if agent_config.integrations:
            for integration in agent_config.integrations:
                if integration not in self.integration_registry:
                    raise ValueError(f"Integración {integration} no está disponible")
        
        # Registrar agente en el registro local (para comunicación multi-agente)
        # Usar patrón thread-safe para evitar problemas de concurrencia
        import asyncio
        
        async with self.registry_lock:
            tenant_agents = self.agent_registry.get(tenant_id, {})
            tenant_agents[agent_id] = {
                "config": agent_config,
                "last_updated": datetime.now()
            }
            self.agent_registry[tenant_id] = tenant_agents
            
        # Registrar la operación para auditoría
        logger.info(f"Agente {agent_id} registrado para tenant {tenant_id}")
        await self._register_agent_operation(tenant_id, agent_id, "create", ctx)
        
        # Definir constantes de TTL específicas por tipo de dato
        TTL_AGENT_CONFIG = CacheManager.ttl_standard  # 1 hora
        
        # Guardar en caché usando método estático para operaciones básicas
        await CacheManager.set(
            data_type="agent_config",
            resource_id=agent_id,
            value=agent_config.dict(),
            tenant_id=tenant_id,
            ttl=TTL_AGENT_CONFIG
        )
        
        # Guardar en base de datos para persistencia
        await self._store_agent_config_in_db(tenant_id, agent_id, agent_config)
        
        return agent_id
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _fetch_agent_config_from_db(self, agent_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración de un agente desde la base de datos.
        Función auxiliar para el patrón cache-aside.
        
        Args:
            agent_id: ID del agente a recuperar
            tenant_id: ID del tenant
            
        Returns:
            Configuración del agente o None si no existe
        """
        from common.db.supabase import get_supabase_client, get_table_name
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Obtener cliente Supabase con contexto adecuado
            supabase = get_supabase_client(tenant_id=tenant_id)
            table_name = get_table_name("agent_configs")
            
            # Buscar configuración de agente en la base de datos
            result = await supabase.table(table_name)\
                .select("*")\
                .eq("tenant_id", tenant_id)\
                .eq("agent_id", agent_id)\
                .limit(1).execute()
            
            if result.data and len(result.data) > 0:
                # Actualizar registro en memoria para acceso rápido futuro
                config = result.data[0].get("config", {})
                async with self.registry_lock:
                    if tenant_id not in self.agent_registry:
                        self.agent_registry[tenant_id] = {}
                    self.agent_registry[tenant_id][agent_id] = config
                return config
            return None
        except Exception as e:
            # Registrar error pero no propagarlo
            logger.error(f"Error al buscar agente {agent_id} en Supabase: {str(e)}")
            # Las métricas de error se registran automáticamente en el decorador handle_errors
            return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_agent(self, 
                         input_text: str, 
                         collection_id: Optional[str] = None,
                         use_auto_federation: bool = False,
                         ctx: Context = None) -> AgentResponse:
        """Ejecuta un agente con memoria de conversación persistente
        
        Args:
            input_text: Texto de entrada del usuario
            collection_id: ID de colección específica seleccionada por el usuario (opcional)
            use_auto_federation: Flag para activar la federación automática de colecciones (False por defecto)
            ctx: Contexto con tenant_id, agent_id y conversation_id
            
        Returns:
            Respuesta del agente
        """
        # Validar ctx y obtener IDs
        if not ctx:
            raise ValueError("Contexto requerido para ejecutar agente")
            
        tenant_id = ctx.get_tenant_id()
        agent_id = ctx.get_agent_id()
        conversation_id = ctx.get_conversation_id()
        
        # Obtener configuración del agente (usando cache-aside)
        agent_config, cache_metrics = await get_with_cache_aside(
            data_type="agent_config",
            resource_id=agent_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_agent_config_from_db,
            generate_func=None  # No hay generación dinámica
        )
        
        # Obtener memoria de conversación
        memory = await self._get_conversation_memory(tenant_id, conversation_id)
        
        # Cargar herramientas para el agente según configuración
        tools = await self._load_agent_tools(tenant_id, agent_config, ctx)
        
        # Crear agente LCEL
        agent_executor = await self._create_agent_executor(
            agent_config=agent_config,
            tools=tools,
            memory=memory,
            ctx=ctx
        )
        
        # Ejecutar agente
        try:
            # Verificar si es necesaria la delegación a otro agente
            delegated_agent_id = await self._check_for_delegation(input_text, agent_config, tenant_id, ctx)
            
            if delegated_agent_id and delegated_agent_id != agent_id:
                # Delegar a otro agente especializado
                return await self._delegate_to_agent(delegated_agent_id, input_text, ctx)
            
            # Procesar con el agente actual
            response = await agent_executor.ainvoke({
                "input": input_text,
                "chat_history": memory.chat_memory.messages
            })
            
            # Guardar resultado en memoria de conversación
            memory.chat_memory.add_user_message(input_text)
            memory.chat_memory.add_ai_message(response["output"])
            await self._save_conversation_memory(tenant_id, conversation_id, memory)
            
            # Procesar integraciones si es necesario
            if response.get("integration_calls"):
                integration_results = await self._process_integration_calls(
                    response["integration_calls"],
                    tenant_id,
                    agent_id,
                    ctx
                )
                response["integration_results"] = integration_results
            
            return AgentResponse(
                response=response["output"],
                sources=response.get("sources", []),
                metadata={
                    "tokens_used": response.get("tokens_used", 0),
                    "delegated": False,
                    "tools_used": response.get("tools_used", []),
                    "cache_hit": cache_metrics.get("cache_hit", False),
                    "has_integrations": bool(response.get("integration_calls"))
                }
            )
            
        except Exception as e:
            logger.error(f"Error ejecutando agente: {str(e)}")
            raise AgentExecutionError(f"Error al ejecutar el agente: {str(e)}") from e
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        ValueError: {"code": "invalid_value", "status_code": 400},
        AgentNotFoundError: {"code": "agent_not_found", "status_code": 404}
    })
    async def _delegate_to_agent(self, target_agent_id: str, input_text: str, ctx: Context) -> AgentResponse:
        """Delega una consulta a otro agente especializado
        
        Args:
            target_agent_id: ID del agente al que delegar
            input_text: Texto de entrada original
            ctx: Contexto actual
            
        Returns:
            Respuesta del agente delegado
        """
        # Crear nuevo contexto para el agente delegado usando función estándar
        from common.context import propagate_context
        delegated_ctx = propagate_context(ctx)
        delegated_ctx.set_agent_id(target_agent_id)
        
        # Ejecutar en el agente delegado
        response = await self.execute_agent(input_text, delegated_ctx)
        
        # Marcar como delegado
        response.metadata["delegated"] = True
        response.metadata["original_agent_id"] = ctx.get_agent_id()
        response.metadata["delegated_agent_id"] = target_agent_id
        
        return response
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _check_for_delegation(self, input_text: str, agent_config: AgentConfig, 
                                   tenant_id: str, ctx: Context) -> Optional[str]:
        """Determina si una consulta debe delegarse a otro agente especializado
        
        Args:
            input_text: Texto de entrada del usuario
            agent_config: Configuración del agente actual
            tenant_id: ID del tenant
            ctx: Contexto actual
            
        Returns:
            ID del agente al que delegar, o None si no hay delegación
        """
        # Si el agente no soporta delegación, retornar None
        if not agent_config.enable_delegation:
            return None
        
        # Obtener embedding de la consulta para buscar el agente más adecuado
        embedding = await self.service_registry.get_embedding(
            text=input_text,
            model="text-embedding-3-small",
            ctx=ctx
        )
        
        # Obtener todos los agentes del tenant
        tenant_agents = self.agent_registry.get(tenant_id, {})
        
        # Si solo hay un agente, no delegar
        if len(tenant_agents) <= 1:
            return None
        
        # Calcular similitud con las descripciones de cada agente
        best_agent_id = None
        highest_score = 0.0
        current_agent_id = ctx.get_agent_id()
        
        for agent_id, agent_data in tenant_agents.items():
            # No delegar al mismo agente
            if agent_id == current_agent_id:
                continue
                
            config = agent_data["config"]
            
            # Si el agente no acepta delegaciones, omitir
            if not config.accept_delegations:
                continue
                
            # Calcular similitud entre la consulta y la descripción del agente
            agent_embedding = await self._get_agent_description_embedding(agent_id, config.description, ctx)
            similarity = self._compute_similarity(embedding, agent_embedding)
            
            if similarity > highest_score and similarity > agent_config.delegation_threshold:
                highest_score = similarity
                best_agent_id = agent_id
        
        return best_agent_id
```

### 1.3 Implementación del ServiceRegistry
- [ ] Completar implementación en `services/service_registry.py`:
  - [ ] Método para comunicación con Embedding Service (exclusivamente OpenAI)
  - [ ] Método para comunicación con Query Service (exclusivamente Groq)
  - [ ] Método para comunicación con Ingestion Service
  - [ ] Propagación completa de contexto en headers
  - [ ] Manejo de errores HTTP estandarizado
  - [ ] Formato de respuesta estandarizado

```python
from common.context import Context, propagate_context_to_headers
from common.errors.handlers import handle_errors, HTTPServiceError
from common.models.base import BaseResponse
from common.config import get_service_settings

class ServiceRegistry:
    def __init__(self):
        # Obtener configuración centralizada usando el sistema estándar según memoria [dce7ad63]
        from common.config import get_service_settings
        settings = get_service_settings()
        
        # Obtener URLs de servicios desde la configuración central
        self.embedding_service_url = settings.embedding_service_url
        self.query_service_url = settings.query_service_url
        self.ingestion_service_url = settings.ingestion_service_url
        
        # Obtener otras configuraciones relevantes
        self.retry_count = settings.service_retry_count
        self.timeout = settings.service_timeout
        
        logger.info(f"ServiceRegistry inicializado con configuración central:"
                   f" embedding_url={self.embedding_service_url},"
                   f" query_url={self.query_service_url}")

    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_embedding(self, text: str, model: str = "text-embedding-3-small", ctx: Context = None) -> List[float]:
        """Obtiene embedding desde el Embedding Service (OpenAI)
        
        Args:
            text: Texto para generar embedding
            model: Modelo de embedding (OpenAI)
            ctx: Contexto con tenant_id y otros valores
            
        Returns:
            Embedding como lista de floats
            
        Raises:
            HTTPServiceError: Si hay error de comunicación
        """
        if not ctx:
            raise ValueError("Contexto requerido para obtener embedding")
            
        tenant_id = ctx.get_tenant_id()
        
        url = f"{self.embedding_service_url}/internal/embed"
        
        # Propagar todo el contexto en headers
        headers = propagate_context_to_headers({}, ctx)
        
        # Añadir metadata de origen para tracking
        data = {
            "text": text, 
            "model": model,
            "metadata": {
                "service_origin": "agent_service",
                "agent_id": ctx.get_agent_id(),
                "conversation_id": ctx.get_conversation_id()
            }
        }
        
        response = await self._make_request("POST", url, headers, json=data)
        
        # Validar respuesta estándar
        if not response.get("success"):
            error_info = response.get("error", {})
            raise HTTPServiceError(
                f"Error del Embedding Service: {response.get('message')}",
                service="embedding",
                status_code=error_info.get("status_code", 500),
                details=error_info
            )
            
        return response["data"]["embedding"]
        
    @handle_errors(error_type="service", log_traceback=True)
    async def query_with_sources(self, query: str, collection_id: str, 
                                embedding: List[float] = None, ctx: Context = None) -> Dict:
        """Realiza consulta con embedding pre-generado al Query Service (Groq)
        
        Args:
            query: Consulta textual
            collection_id: ID de colección a consultar
            embedding: Embedding pre-generado (opcional)
            ctx: Contexto con tenant_id y otros valores
            
        Returns:
            Resultados de la consulta con fuentes
        """
        if not ctx:
            raise ValueError("Contexto requerido para consulta con fuentes")
            
        tenant_id = ctx.get_tenant_id()
        
        url = f"{self.query_service_url}/internal/query"
        
        # Propagar todo el contexto en headers
        headers = propagate_context_to_headers({}, ctx)
        
        data = {
            "query": query,
            "collection_id": collection_id,
            "query_embedding": embedding,  # Pre-generado en Agent Service
            "metadata": {
                "service_origin": "agent_service",
                "agent_id": ctx.get_agent_id(),
                "conversation_id": ctx.get_conversation_id()
            }
        }
        
        response = await self._make_request("POST", url, headers, json=data)
        
        # Validar respuesta estándar
        if not response.get("success"):
            error_info = response.get("error", {})
            raise HTTPServiceError(
                f"Error del Query Service: {response.get('message')}",
                service="query",
                status_code=error_info.get("status_code", 500),
                details=error_info
            )
            
        return response["data"]
```

### 1.4 Implementación de Herramientas (Tools)
- [ ] Desarrollar en `tools/` las siguientes herramientas:
  - [ ] `tools/base.py`: Clase base para herramientas con integración de contexto
  - [ ] `tools/rag_tools.py`: Herramientas para consulta RAG
  - [ ] `tools/embedding_tools.py`: Herramientas para embeddings (solo OpenAI)
  - [ ] `tools/general_tools.py`: Herramientas genéricas
  - [ ] `tools/document_tools.py`: Herramientas para gestión documental

```python
# tools/base.py
from langchain.tools import BaseTool as LangChainBaseTool
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, ClassVar
from common.context import Context
from common.errors.handlers import handle_errors

class BaseTool(LangChainBaseTool):
    """Clase base para todas las herramientas con integración de contexto"""
    requires_context: ClassVar[bool] = True
    
    def __init__(self, service_registry, ctx: Optional[Context] = None):
        """Inicializa la herramienta con acceso al registro de servicios y contexto"""
        super().__init__()
        self.service_registry = service_registry
        self.ctx = ctx
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _arun(self, **kwargs) -> str:
        """Implementación asincrónica de la herramienta con manejo de errores estandarizado"""
        if self.requires_context and not self.ctx:
            raise ValueError(f"La herramienta {self.name} requiere contexto")
        return await self._run_with_context(**kwargs)
    
    async def _run_with_context(self, **kwargs) -> str:
        """Método a ser implementado por las clases hijas"""
        raise NotImplementedError()

# tools/rag_tools.py
from .base import BaseTool
from pydantic import BaseModel, Field
from typing import Dict, List, Any
from common.cache import CacheManager

class RAGQueryInput(BaseModel):
    query: str = Field(description="La consulta del usuario")
    collection_id: str = Field(description="ID de la colección a consultar")
    similarity_top_k: int = Field(default=4, description="Número de resultados a retornar")
    
class RAGQueryTool(BaseTool):
    name = "rag_query"
    description = "Consulta documentos relevantes para responder a una pregunta"
    args_schema = RAGQueryInput
    
    async def _run_with_context(self, query: str, collection_id: str, similarity_top_k: int = 4) -> str:
        """Ejecuta consulta RAG con propagación de contexto completa
        
        Args:
            query: Consulta del usuario
            collection_id: ID de la colección a consultar
            similarity_top_k: Número de resultados a retornar
            
        Returns:
            Resultados formateados para el agente
        """
        # Verificar cache para resultados previos (evitar repetición de consultas)
        cache_key = f"{query}:{collection_id}:{similarity_top_k}"
        tenant_id = self.ctx.get_tenant_id()
        agent_id = self.ctx.get_agent_id() if self.ctx else None
        
        # Intentar obtener de caché
        cached_result = await CacheManager.get(
            data_type="rag_result",
            resource_id=cache_key,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id
        )
        
        if cached_result:
            return self._format_result(cached_result)
        
        # Obtener embedding usando el servicio de embeddings (OpenAI via Embedding Service)
        embedding = await self.service_registry.get_embedding(
            text=query,
            model="text-embedding-3-small",
            ctx=self.ctx
        )
        
        # Consultar con embedding pre-generado usando el Query Service
        result = await self.service_registry.query_with_sources(
            query=query,
            collection_id=collection_id,
            embedding=embedding,
            ctx=self.ctx
        )
        
        # Almacenar resultado en caché para futuras consultas
        await CacheManager.set(
            data_type="rag_result",
            resource_id=cache_key,
            value=result,
            tenant_id=tenant_id,
            agent_id=agent_id,
            collection_id=collection_id,
            ttl=CacheManager.ttl_short  # 5 minutos
        )
        
        # Formatear resultado para el agente
        return self._format_result(result)
        
    def _format_result(self, result: Dict[str, Any]) -> str:
        """Formatea el resultado RAG para consumo del agente"""
        formatted = f"Respuesta encontrada: {result['response']}\n\nFuentes:\n"
        
        for i, source in enumerate(result.get('sources', []), 1):
            formatted += f"[{i}] {source.get('text', '')}\n"
            if source.get('document_id'):
                formatted += f"   Documento: {source.get('document_id')}\n"
                
        return formatted
```

### 1.5 Implementación de Memoria de Conversación
- [ ] Implementar en `services/memory.py`:
  - [ ] Integración con Supabase para persistencia
  - [ ] Interfaz compatible con LangChain
  - [ ] Recuperación eficiente de historial de conversaciones

```python
class SupabaseConversationMemory:
    """Implementación de memoria de conversación con Supabase"""
    
    async def save_context(self, tenant_id: str, conversation_id: str, inputs: Dict, outputs: Dict):
        """Guarda una interacción en la memoria"""
        pass
        
    async def load_memory_variables(self, tenant_id: str, conversation_id: str) -> Dict[str, List]:
        """Carga variables de memoria para un contexto de conversación"""
        pass
```

### 1.6 Completar Endpoints de Agentes
- [ ] Implementar en `routes/agents.py`:
  - [ ] Endpoints CRUD para agentes con decorador `@with_context`
  - [ ] Endpoints para ejecución de agentes con contexto completo
  - [ ] Endpoints para gestión de conversaciones con propagación de contexto
  - [ ] Endpoints para listar herramientas disponibles
  - [ ] Manejo de errores con decorador `@handle_errors`
  - [ ] Respuestas estandarizadas con modelo `BaseResponse`

```python
# routes/agents.py
from fastapi import APIRouter, Body, Depends, HTTPException
from typing import List, Dict, Any, Optional

from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.models.base import BaseResponse

from models.agent_models import AgentConfig, AgentResponse
from services import get_agent_service, get_service_registry

router = APIRouter()

@router.post("/agents")
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def create_agent(
    agent_config: AgentConfig = Body(...),
    ctx: Context = None
) -> BaseResponse:
    """Crea un nuevo agente con la configuración proporcionada."""
    # El decorador @with_context ya valida el tenant_id y lo hace disponible
    agent_service = get_agent_service()
    agent_id = await agent_service.create_agent(agent_config=agent_config, ctx=ctx)
    
    return BaseResponse(
        success=True,
        message="Agente creado con éxito",
        data={"agent_id": agent_id}
    )

@router.post("/agents/{agent_id}/execute")
@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="simple", log_traceback=False)
async def execute_agent(
    input_text: str = Body(..., embed=True),
    ctx: Context = None
) -> BaseResponse:
    """Ejecuta un agente con una entrada específica.
    
    El agent_id y conversation_id se toman del contexto (URL).
    """
    # El contexto ya contiene tenant_id, agent_id y conversation_id validados
    agent_service = get_agent_service()
    response = await agent_service.execute_agent(input_text=input_text, ctx=ctx)
    
    return BaseResponse(
        success=True,
        message="Ejecución completada",
        data=response.dict()
    )

@router.get("/agents/tools")
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def list_available_tools(ctx: Context = None) -> BaseResponse:
    """Lista todas las herramientas disponibles para agentes."""
    agent_service = get_agent_service()
    tools = await agent_service.list_available_tools(ctx=ctx)
    
    return BaseResponse(
        success=True,
        message="Herramientas disponibles",
        data={"tools": tools}
    )
```

## 2. Fase 2: Refactorización de Query Service (Semana 2)

### 2.1 Modificación de Modelos
- [ ] Actualizar `InternalQueryRequest` y `InternalSearchRequest` para aceptar embeddings:
  - [ ] Asegurar compatibilidad con el sistema de contexto
  - [ ] Implementar modelo estandarizado de respuesta
  - [ ] Verificar integración exclusiva con Groq para LLM

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from common.models.base import BaseModel as CommonBaseModel

class InternalQueryRequest(CommonBaseModel):
    query: str = Field(..., description="Consulta textual") 
    collection_id: Optional[str] = Field(None, description="ID de la colección a consultar")
    k: int = Field(4, description="Número de resultados a retornar")
    query_embedding: Optional[List[float]] = Field(None, description="Embedding pre-generado (desde Agent Service)")
    response_mode: str = Field("compact", description="Modo de respuesta: compact, tree, etc.")
    similarity_threshold: Optional[float] = Field(None, description="Umbral mínimo de similitud")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales como service_origin")
```

### 2.2 Actualización de `create_query_engine`
- [ ] Modificar para aceptar embeddings pre-generados en `services/query_engine.py`:
  - [ ] Eliminar llamadas directas al Embedding Service
  - [ ] Usar embeddings pre-generados cuando están disponibles
  - [ ] Implementar cache con el patrón Cache-Aside estándar

```python
from common.context import Context
from common.errors.handlers import handle_errors
from common.cache import CacheManager, get_with_cache_aside

@handle_errors(error_type="service", log_traceback=True)
async def create_query_engine(
    collection_id: Optional[str] = None,
    query_embedding: Optional[List[float]] = None,  # Embedding pre-generado
    ctx: Context = None
):
    """Crea un motor de consulta para una colección dada.
    
    Args:
        collection_id: ID de la colección (opcional)
        query_embedding: Embedding pre-generado (opcional)
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Motor de consulta configurado
        
    Raises:
        MissingEmbeddingError: Si se requiere embedding pero no se proporciona
        CollectionNotFoundError: Si la colección no existe
    """
    if not ctx:
        raise ValueError("Contexto requerido para crear query engine")
        
    tenant_id = ctx.get_tenant_id()
    
    # IMPORTANTE: NO generar embeddings directamente
    # Solo usar los embeddings pre-generados proporcionados por el Agent Service
    if not query_embedding and collection_id:
        # Si no hay embedding pero se requiere colección, es un error
        raise ValueError("Se requiere embedding para consultar colección")
    
    # Obtener vector store con posible caché
    vector_store = await get_vector_store_for_collection(tenant_id, collection_id, ctx)
    
    # Resto de la implementación...
```

### 2.3 Actualización de Endpoints Internos
- [ ] Modificar `/internal/query` y `/internal/search` en `routes/internal.py`:
  - [ ] Implementar decorador `@with_context`
  - [ ] Implementar decorador `@handle_errors`
  - [ ] Utilizar respuesta estándar con `BaseResponse`
  - [ ] Extraer metadatos de servicio origen

```python
from fastapi import APIRouter, Body, Depends
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.models.base import BaseResponse

router = APIRouter()

@router.post("/internal/query", response_model=None)
@with_context(tenant=True, collection=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_query(
    request: InternalQueryRequest = Body(...),
    ctx: Context = None
):
    """Endpoint interno para procesar consultas con embeddings pre-generados."""
    tenant_id = ctx.get_tenant_id()
    collection_id = ctx.get_collection_id() or request.collection_id
    
    # Extraer metadata de origen para tracking
    metadata = request.metadata or {}
    service_origin = metadata.get("service_origin", "unknown")
    
    # Crear engine con embedding pre-generado
    query_engine = await create_query_engine(
        collection_id=collection_id,
        query_embedding=request.query_embedding,  # Usar embedding pre-generado
        ctx=ctx
    )
    
    # Realizar consulta
    result = await process_query_with_sources(query_engine, request.query, tenant_id, collection_id)
    
    # Retornar respuesta estándar
    return BaseResponse(
        success=True,
        message="Query procesada con éxito",
        data=result,
        metadata={
            "service_origin": service_origin,
            "embedding_provided": request.query_embedding is not None
        }
    )
```

## 3. Fase 3: Optimización del Embedding Service (Semana 2-3)

### 3.1 Reforzar Tracking de Tokens
- [ ] Mejorar tracking en `provider/openai.py` siguiendo la memoria [0dd04069]:
  - [ ] Implementar detección de fuente de tokens (`token_source: "api"` o `token_source: "estimated"`)
  - [ ] Implementar lógica de fallback robusta para conteo de tokens
  - [ ] Enriquecer metadata con dimensiones, hash del texto y longitud
  - [ ] Validar que el número de tokens sea > 0 antes de registrar

```python
from common.context import Context
from common.errors.handlers import handle_errors
from common.tracking import track_token_usage, OPERATION_EMBEDDING
import hashlib

@handle_errors(error_type="service", log_traceback=True)
async def get_openai_embedding(
    text: str, 
    model: str = "text-embedding-3-small",
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Context = None
) -> Tuple[List[float], Dict[str, Any]]:
    """Genera embeddings usando OpenAI con tracking completo.
    
    Args:
        text: Texto para generar embedding
        model: Modelo de OpenAI a utilizar
        metadata: Metadatos adicionales
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Tupla con (embedding, metadata)
        
    Raises:
        EmbeddingGenerationError: Si hay error al generar el embedding
    """
    if not text or not text.strip():
        raise ValueError("El texto no puede estar vacío")
        
    # Obtener tenant_id del contexto
    tenant_id = ctx.get_tenant_id() if ctx else None
    
    # Preparar metadata enriquecida
    metadata = metadata or {}
    text_hash = hashlib.md5(text.encode()).hexdigest()
    enriched_metadata = {
        "text_hash": text_hash,
        "text_length": len(text),
        "model": model
    }
    
    # Añadir IDs relevantes si están disponibles en el contexto
    if ctx:
        if ctx.get_collection_id():
            enriched_metadata["collection_id"] = ctx.get_collection_id()
        if ctx.get_agent_id():
            enriched_metadata["agent_id"] = ctx.get_agent_id()
        # Añadir otros IDs disponibles
    
    # Añadir metadata del llamador
    enriched_metadata.update(metadata)
    
    # Generar embedding con OpenAI
    try:
        response = await openai_client.embeddings.create(
            input=[text],
            model=model
        )
        
        embedding = response.data[0].embedding
        
        # Extraer tokens de la respuesta de la API
        token_count = 0
        token_source = "estimated"
        
        if hasattr(response, "usage") and response.usage:
            token_count = response.usage.total_tokens
            token_source = "api"
        else:
            # Estimación local de tokens como fallback
            token_count = len(text.split()) * 1.3  # Aproximación simple
        
        # Validar que el número de tokens sea > 0 según memoria [0dd04069]
        if token_count <= 0:
            logger.warning(f"Número de tokens inválido: {token_count}, usando valor predeterminado")
            # Usar estimación basada en longitud como fallback seguro
            token_count = max(1, len(text) // 4)  # Garantizar al menos 1 token
        
        # Enriquecer metadata con dimensiones, token_source y otros campos según memoria [0dd04069]
        enriched_metadata.update({
            "dimensions": len(embedding),
            "token_source": token_source,
            "text_hash": hashlib.md5(text.encode()).hexdigest(),
            "text_length": len(text)
        })
        
        # Registrar tokens usando el sistema de tracking
        if tenant_id:
            await track_token_usage(
                tenant_id=tenant_id,
                operation=OPERATION_EMBEDDING,
                token_count=int(token_count),
                model=model,
                metadata=enriched_metadata
            )
        
        return embedding, enriched_metadata
        
    except Exception as e:
        raise EmbeddingGenerationError(f"Error al generar embedding: {str(e)}") from e
```

### 3.2 Validar que Solo Existan Endpoints Internos
- [ ] Asegurar que `routes/embeddings.py` solo expone endpoints internos según la memoria [46cab1ca]:
  - [ ] `/internal/embed` para uso interno (exclusivamente OpenAI)
  - [ ] `/internal/batch` para procesamiento por lotes
  - [ ] `/health` para verificación de salud
  - [ ] Eliminar cualquier endpoint público accidental

```python
from fastapi import APIRouter, Body, Depends
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.models.base import BaseResponse

router = APIRouter()

@router.post("/internal/embed", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_embed(
    request: InternalEmbeddingRequest = Body(...),
    ctx: Context = None
):
    """Genera embedding para un texto usando OpenAI (exclusivamente para uso interno)"""
    embedding, metadata = await get_openai_embedding(
        text=request.text,
        model=request.model,
        metadata=request.metadata,
        ctx=ctx
    )
    
    return BaseResponse(
        success=True,
        message="Embedding generado con éxito",
        data={"embedding": embedding},
        metadata=metadata
    )
```

### 3.3 Optimizar Caché
- [ ] Implementar patrón Cache-Aside estándar según las memorias [4b42c148] y [6c9efbf8]:
  - [ ] Reemplazar implementaciones propias con `get_with_cache_aside`
  - [ ] Usar métodos estáticos para operaciones básicas
  - [ ] Usar métodos de instancia para operaciones de listas
  - [ ] Implementar el TTL correcto (TTL_EXTENDED, 24 horas) para embeddings

```python
from common.cache import CacheManager, get_with_cache_aside, serialize_for_cache

async def get_embedding_with_cache(text: str, model: str, ctx: Context = None) -> List[float]:
    """Obtiene embedding usando el patrón Cache-Aside estándar"""
    
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para obtener embedding con caché")
        
    tenant_id = ctx.get_tenant_id()
    
    # Generar resource_id consistente
    text_hash = hashlib.md5(text.encode()).hexdigest()
    resource_id = f"{model}:{text_hash}"
    
    # Función para generar el embedding si no existe
    async def generate_embedding(resource_id, tenant_id, **kwargs):
        embedding, _ = await get_openai_embedding(
            text=text,
            model=model,
            metadata={"source": "cache_miss"},
            ctx=ctx
        )
        return embedding
    
    # Implementación del patrón Cache-Aside
    embedding, metrics = await get_with_cache_aside(
        data_type="embedding",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_embedding_from_db,  # Función para buscar en Supabase
        generate_func=generate_embedding,  # Función para generar si no existe
        ttl=CacheManager.ttl_extended,  # 24 horas para embeddings
        agent_id=ctx.get_agent_id() if ctx else None,
        collection_id=ctx.get_collection_id() if ctx else None
    )
    
    return embedding
```

## 4. Fase 4: Pruebas de Integración (Semana 3)

### 4.1 Preparación de Entorno de Pruebas
- [ ] Configurar entorno local para pruebas
- [ ] Crear colecciones y documentos de prueba
- [ ] Crear configuraciones de agentes de prueba

### 4.2 Pruebas de Flujo RAG
- [ ] Probar flujo completo desde usuario hasta respuesta:
  - [ ] Cliente → Agent Service
  - [ ] Agent Service → Embedding Service (obtener embedding)
  - [ ] Agent Service → Query Service (consultar con embedding)
  - [ ] Verificar respuesta y fuentes

### 4.3 Pruebas de Flujo de Ingesta
- [ ] Probar flujo de ingesta completo:
  - [ ] Cliente → Agent Service
  - [ ] Agent Service → Ingestion Service
  - [ ] Ingestion Service → Embedding Service
  - [ ] Verificar documento almacenado y indexado

## 5. Framework de Integraciones Externas

### 5.1 Arquitectura de Integraciones

- [ ] Implementar framework de integraciones en `services/integrations_manager.py`:
  - [ ] Sistema de registro y descubrimiento de integraciones
  - [ ] Interfaz común para todas las integraciones
  - [ ] Gestión del ciclo de vida de las conexiones

```python
from typing import Dict, List, Any, Optional, Type
from abc import ABC, abstractmethod
from common.context import Context
from common.errors.handlers import handle_errors

class BaseIntegration(ABC):
    """Clase base para todas las integraciones externas"""
    name: str = "base_integration"
    display_name: str = "Integración Base"
    description: str = "Clase base para integraciones"
    
    @abstractmethod
    async def initialize(self, tenant_id: str, config: Dict[str, Any]) -> bool:
        """Inicializa la integración con la configuración proporcionada"""
        pass
    
    @abstractmethod
    async def execute_action(self, action: str, params: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        """Ejecuta una acción específica de la integración"""
        pass
    
    @abstractmethod
    async def get_available_actions(self) -> List[Dict[str, Any]]:
        """Retorna las acciones disponibles para esta integración"""
        pass

class EmailIntegration(BaseIntegration):
    """Integración para envío y recepción de emails"""
    name = "email"
    display_name = "Integración de Email"
    description = "Permite enviar y recibir emails desde el agente"
    
    async def initialize(self, tenant_id: str, config: Dict[str, Any]) -> bool:
        """Inicializa la conexión SMTP/IMAP con la configuración proporcionada"""
        # Implementación específica...
        
    async def execute_action(self, action: str, params: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        """Ejecuta acciones como enviar email, leer bandeja de entrada, etc."""
        if action == "send_email":
            return await self._send_email(params, ctx)
        elif action == "read_inbox":
            return await self._read_inbox(params, ctx)
        # Otras acciones...
        
    async def get_available_actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "send_email", "name": "Enviar Email", "parameters": ["to", "subject", "body"]},
            {"id": "read_inbox", "name": "Leer Bandeja de Entrada", "parameters": ["limit", "filter"]}
        ]

class WhatsAppIntegration(BaseIntegration):
    """Integración con WhatsApp Business API"""
    name = "whatsapp"
    display_name = "Integración de WhatsApp"
    description = "Permite enviar y recibir mensajes de WhatsApp"
    
    # Implementación similar a la de email...

class IntegrationsManager:
    """Gestor centralizado de integraciones externas"""
    
    def __init__(self):
        self.integrations: Dict[str, Type[BaseIntegration]] = {}
        self.tenant_integrations: Dict[str, Dict[str, BaseIntegration]] = {}
    
    def register_integration(self, integration_class: Type[BaseIntegration]):
        """Registra una nueva clase de integración"""
        self.integrations[integration_class.name] = integration_class
    
    @handle_errors(error_type="service", log_traceback=True)
    async def initialize_tenant_integration(self, 
                                          tenant_id: str,
                                          integration_name: str,
                                          config: Dict[str, Any]) -> bool:
        """Inicializa una integración específica para un tenant"""
        if integration_name not in self.integrations:
            raise ValueError(f"Integración {integration_name} no registrada")
            
        # Crear instancia de la integración
        integration_class = self.integrations[integration_name]
        integration = integration_class()
        
        # Inicializar con configuración específica del tenant
        success = await integration.initialize(tenant_id, config)
        
        # Almacenar la instancia inicializada
        tenant_configs = self.tenant_integrations.get(tenant_id, {})
        tenant_configs[integration_name] = integration
        self.tenant_integrations[tenant_id] = tenant_configs
        
        return success
    
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_integration_action(self,
                                        tenant_id: str,
                                        integration_name: str,
                                        action: str,
                                        params: Dict[str, Any],
                                        ctx: Context) -> Dict[str, Any]:
        """Ejecuta una acción en la integración especificada"""
        # Validar que la integración existe para el tenant
        tenant_configs = self.tenant_integrations.get(tenant_id, {})
        if integration_name not in tenant_configs:
            raise ValueError(f"Integración {integration_name} no inicializada para el tenant")
            
        integration = tenant_configs[integration_name]
        
        # Ejecutar la acción
        return await integration.execute_action(action, params, ctx)
```

### 5.2 Selección Dinámica de Colecciones

- [ ] Implementar en `services/collection_manager.py`:
  - [ ] Selección dinámica de colecciones basada en la consulta
  - [ ] Federación de resultados de múltiples colecciones
  - [ ] Ponderación automática de relevancia por colección

```python
from typing import Dict, List, Any, Optional
from common.context import Context
from common.errors.handlers import handle_errors

class CollectionManager:
    """Gestor de selección dinámica de colecciones"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        
    @handle_errors(error_type="service", log_traceback=True)
    async def select_relevant_collections(self, 
                                        query: str, 
                                        tenant_id: str,
                                        available_collections: List[str] = None,
                                        ctx: Context = None) -> List[Dict[str, Any]]:
        """Selecciona colecciones relevantes para una consulta
        
        Args:
            query: Consulta del usuario
            tenant_id: ID del tenant
            available_collections: Lista de IDs de colecciones disponibles (opcional)
            ctx: Contexto con tenant_id y otros valores
            
        Returns:
            Lista de colecciones relevantes con score de relevancia
        """
        # Obtener embedding de la consulta
        embedding = await self.service_registry.get_embedding(
            text=query,
            model="text-embedding-3-small",
            ctx=ctx
        )
        
        # Si no se especifican colecciones, obtener todas las del tenant
        if not available_collections:
            available_collections = await self._get_tenant_collections(tenant_id)
        
        relevant_collections = []
        
        # Evaluar relevancia de cada colección
        for collection_id in available_collections:
            # Obtener embedding representativo de la colección
            collection_embedding = await self._get_collection_embedding(tenant_id, collection_id, ctx)
            
            # Calcular similitud con la consulta
            similarity = self._compute_similarity(embedding, collection_embedding)
            
            # Si supera un umbral mínimo, añadir a las relevantes
            if similarity > 0.6:  # Umbral configurable
                relevant_collections.append({
                    "collection_id": collection_id,
                    "relevance_score": similarity
                })
        
        # Ordenar por relevancia descendente
        relevant_collections.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return relevant_collections
    
    @handle_errors(error_type="service", log_traceback=True, error_map={
        ValueError: {"code": "query_error", "status_code": 400},
        HTTPServiceError: {"code": "service_error", "status_code": 503}
    })
    async def query_with_sources(self,
                              query: str,
                              collection_id: str,
                              similarity_top_k: int = 4,
                              embedding: Optional[List[float]] = None,
                              ctx: Context = None) -> Dict[str, Any]:
        """Realiza una consulta RAG utilizando el Query Service (Groq)
        
        Args:
            query: Consulta del usuario
            collection_id: ID de la colección a consultar
            similarity_top_k: Número de resultados a retornar
            embedding: Vector de embedding pre-generado (opcional)
            ctx: Contexto con tenant_id
            
        Returns:
            Resultados formateados con fuentes
        """
        # Validar contexto usando el sistema unificado (memoria face0aba)
        if not ctx or not ctx.get_tenant_id():
            # Usar el método estandarizado validate_tenant_context
            from common.context.vars import validate_tenant_context
            validate_tenant_context(ctx, service_name="agent_service")
        
        tenant_id = ctx.get_tenant_id()
        
        # Verificar si tenemos un embedding pre-generado para reutilizar
        # Si no se proporciona embedding, generarlo a través del Embedding Service (OpenAI)
        if not embedding and collection_id:
            # Incluir metadatos para el tracking adecuado
            metadata = {
                "collection_id": collection_id,
                "operation": "query_with_sources",
                "service_origin": "agent_service"
            }
            
            # Usar servicio de embeddings del ServiceRegistry que ya incluye tracking
            embedding = await self.get_embedding(
                text=query, 
                ctx=ctx, 
                metadata=metadata
            )
            
        # Generar un ID único para la consulta (para caché)
        import hashlib
        # Creamos un hash consistente de los parámetros clave de la consulta
        query_hash = hashlib.md5(f"{query}:{collection_id}:{similarity_top_k}".encode()).hexdigest()
        
        # Implementar el patrón Cache-Aside según las memorias 4b42c148, 6c9efbf8, 1990c4da
        from common.cache import get_with_cache_aside, CacheManager
        
        # Función para generar el resultado de la consulta (usado por cache-aside)
        async def generate_query_result(_):
            # Preparar datos para la solicitud al Query Service
            # Incluimos el embedding pre-generado para evitar regeneración en el Query Service
            data = {
                "query": query,
                "collection_id": collection_id,
                "k": similarity_top_k,
                "query_embedding": embedding,
                "metadata": {
                    "service_origin": "agent_service",
                    "agent_id": ctx.get_agent_id() if ctx else None,
                    "conversation_id": ctx.get_conversation_id() if ctx else None
                }
            }
            
            # Preparar los headers con el contexto
            headers = self._build_context_headers(ctx)
            
            try:
                # Llamar al endpoint interno del Query Service según la arquitectura de la memoria 46cab1ca
                response = await self.http_client.post(
                    url=f"{self.query_service_url}/internal/query",
                    json=data,
                    headers=headers,
                    timeout=10.0  # Timeout para evitar bloqueos prolongados
                )
                response.raise_for_status()
                result_data = response.json()
                
                # Extraer el resultado del formato estandarizado de respuesta
                if result_data.get("success"):
                    return result_data.get("data", {})
                else:
                    # Manejar errores del servicio de consultas
                    error_msg = result_data.get("error", {}).get("message", "Error desconocido")
                    logger.error(f"Error en Query Service: {error_msg}")
                    raise ValueError(f"Error del servicio de consultas: {error_msg}")
            except Exception as e:
                logger.error(f"Error al realizar consulta: {str(e)}")
                raise HTTPServiceError(f"Error del servicio de consultas: {str(e)}") from e
        
        # Usar el patrón cache-aside estandarizado
        result, metrics = await get_with_cache_aside(
            data_type="query_result",
            resource_id=query_hash,
            tenant_id=tenant_id,
            agent_id=ctx.get_agent_id() if ctx else None,
            collection_id=collection_id,
            conversation_id=ctx.get_conversation_id() if ctx else None,
            fetch_from_db_func=None,  # No hay almacenamiento en DB para consultas
            generate_func=generate_query_result,
            ttl=CacheManager.ttl_short  # 5 minutos según estándares de la memoria d31348ad
        )
        
        # Si hay métricas de tracking importantes, registrarlas
        if metrics and "latency" in metrics:
            await self._log_query_metrics(tenant_id, collection_id, metrics)
            
        return result
    
    @handle_errors(error_type="service", log_traceback=False)
    async def _log_query_metrics(self, tenant_id: str, collection_id: str, metrics: Dict[str, Any]) -> None:
        """Registra métricas de consulta para análisis de rendimiento.
        
        Args:
            tenant_id: ID del tenant
            collection_id: ID de la colección consultada
            metrics: Métricas recopiladas durante la consulta
        """
        from common.tracking.metrics import track_performance_metric
        
        try:
            # Registrar latencia de consulta
            if "latency" in metrics:
                await track_performance_metric(
                    metric_type="query_latency",
                    value=metrics["latency"],
                    tenant_id=tenant_id,
                    metadata={
                        "collection_id": collection_id,
                        "service": "agent_service",
                        "cache_hit": metrics.get("cache_hit", False)
                    }
                )
                
            # Registrar uso de tokens si está disponible
            if "tokens_used" in metrics:
                await track_performance_metric(
                    metric_type="tokens_per_query",
                    value=metrics["tokens_used"],
                    tenant_id=tenant_id,
                    metadata={
                        "collection_id": collection_id,
                        "service": "agent_service"
                    }
                )
                
            # Registrar tamaño de respuesta si está disponible
            if "response_size" in metrics:
                await track_performance_metric(
                    metric_type="response_size",
                    value=metrics["response_size"],
                    tenant_id=tenant_id,
                    metadata={
                        "collection_id": collection_id,
                        "service": "agent_service"
                    }
                )
        except Exception as e:
            # No propagamos errores de tracking para evitar impactar el servicio principal
            logger.warning(f"Error al registrar métricas de consulta: {str(e)}")
            # Las métricas no son cruciales para la funcionalidad principal
        
        # Consultar cada colección relevante con manejo de errores robusto
        for collection_info in relevant_collections:
            collection_id = collection_info["collection_id"]
            relevance_score = collection_info["relevance_score"]
            
            # Guardar el peso para ponderación posterior
            collection_weights[collection_id] = relevance_score
            
            try:
                # Consultar usando el Query Service con timeout
                collection_result = await asyncio.wait_for(
                    self.service_registry.query_with_sources(
                        query=query,
                        collection_id=collection_id,
                        embedding=embedding,  # Reutilizar el embedding
                        ctx=ctx
                    ),
                    timeout=5.0  # Timeout de 5 segundos por colección
                )
                
                # Añadir información de origen
                for source in collection_result.get("sources", []):
                    source["collection_id"] = collection_id
                    source["collection_relevance"] = relevance_score
                    results.append(source)
            except Exception as e:
                # Capturar cualquier error y continuar con otras colecciones
                error_msg = f"Error consultando colección {collection_id}: {str(e)}"
                logger.error(error_msg)
                
                # Registrar el error para tracking
                await self._register_collection_error(tenant_id, collection_id, error_msg, ctx)
                
                # Continuar con las siguientes colecciones
        
        # Ordenar resultados por score ponderado (score_doc * relevance_collection)
        for result in results:
            collection_id = result.get("collection_id")
            result["weighted_score"] = result.get("score", 0) * collection_weights.get(collection_id, 1.0)
            
        results.sort(key=lambda x: x.get("weighted_score", 0), reverse=True)
        
        return {
            "sources": results[:10],  # Limitar a los 10 mejores resultados ponderados
            "collections_used": [c["collection_id"] for c in relevant_collections],
            "collections_count": len(relevant_collections)
        }
        
    async def _register_collection_error(self, tenant_id, collection_id, error_msg, ctx=None):
        """Registra un error ocurrido durante la consulta a una colección.
        
        Args:
            tenant_id (str): ID del tenant
            collection_id (str): ID de la colección que falló
            error_msg (str): Mensaje de error
            ctx (Context, optional): Contexto de la operación
            
        Returns:
            None
        """
        try:
            from datetime import datetime
            from common.db.supabase import get_supabase_client, get_table_name
            from common.tracking.metrics import track_error_metric
            
            # Obtener cliente Supabase con contexto adecuado
            supabase = get_supabase_client(tenant_id=tenant_id)
            
            # Crear registro de error para análisis posterior
            error_record = {
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "error_message": error_msg,
                "agent_id": ctx.get_agent_id() if ctx else None,
                "conversation_id": ctx.get_conversation_id() if ctx else None,
                "timestamp": datetime.now().isoformat(),
                "service": "agent_service",
                "operation": "federated_query"
            }
            
            # Insertar en tabla de errores
            table_name = get_table_name("service_errors")
            await supabase.table(table_name).insert(error_record).execute()
            
            # También registrar en métricas para alertas
            await track_error_metric(
                error_type="collection_query_error",
                tenant_id=tenant_id,
                metadata={
                    "collection_id": collection_id,
                    "error": error_msg[:100]  # Primeros 100 caracteres para métricas
                }
            )
        except Exception as e:
            # Evitar que falle el registro de errores
            logger.warning(f"Error al registrar fallo de colección: {str(e)}")
            # No propagamos este error para no interrumpir el flujo principal
```

## 6. Integración Frontend-Backend

### 6.1 Modelo de Request desde Frontend

Para optimizar la comunicación entre el frontend y el Agent Service, implementaremos un modelo de request que permita enviar configuraciones precargadas desde el frontend, evitando consultas redundantes a la base de datos:

```python
class ExecuteAgentRequest(BaseModel):
    # Datos básicos
    input_text: str = Field(..., description="Mensaje del usuario")
    conversation_id: Optional[str] = Field(None, description="ID de conversación existente")
    
    # Configuración del agente
    agent_config: Optional[Dict[str, Any]] = Field(None, description="Configuración completa del agente")
    
    # Configuración de colección
    collection_id: Optional[str] = Field(None, description="ID de colección seleccionada")
    collection_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos completos de la colección")
    
    # Información del tenant y tier
    tenant_tier: Optional[str] = Field(None, description="Tier del tenant (free, pro, business, enterprise)")
    
    # Configuraciones de modelo
    embedding_model: Optional[str] = Field(None, description="Modelo de embedding a utilizar")
    llm_model: Optional[str] = Field(None, description="Modelo LLM a utilizar")
    
    # Opciones de comportamiento
    use_auto_federation: bool = Field(False, description="Activar federación automática")
    use_streaming: bool = Field(False, description="Usar respuestas en streaming")
```

### 6.2 Endpoint para Ejecución de Agentes

Implementaremos un endpoint específico para la ejecución de agentes que pueda recibir configuraciones desde el frontend:

```python
@router.post("/execute")
@with_context(tenant=True, agent=True, validate_tenant=True)
async def execute_agent(
    request: ExecuteAgentRequest,
    ctx: Context = None
):
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido")
    
    tenant_id = ctx.get_tenant_id()
    agent_id = ctx.get_agent_id()
    
    # Usar conversation_id del request si se proporciona
    if request.conversation_id:
        ctx.set_conversation_id(request.conversation_id)
    
    # Inicializar servicio
    agent_service = get_agent_service()
    
    # Si se proporciona agent_config, usarla directamente (evitamos buscar en DB)
    if request.agent_config:
        # Registrar configuración en caché/memoria del servicio
        await agent_service.register_agent_from_frontend(
            tenant_id=tenant_id, 
            agent_id=agent_id, 
            agent_config=request.agent_config,
            ctx=ctx
        )
    
    # Ejecutar agente con parámetros proporcionados por el frontend
    response = await agent_service.execute_agent(
        input_text=request.input_text,
        collection_id=request.collection_id,
        collection_metadata=request.collection_metadata,
        tenant_tier=request.tenant_tier,
        embedding_model=request.embedding_model,
        llm_model=request.llm_model,
        use_auto_federation=request.use_auto_federation,
        use_streaming=request.use_streaming,
        ctx=ctx
    )
    
    return BaseResponse(
        success=True,
        message="Ejecución completada",
        data=response
    )
```

### 6.3 Registro de Configuraciones Frontend

Implementaremos un método específico para registrar configuraciones enviadas desde el frontend:

```python
@handle_errors(error_type="service", log_traceback=True)
async def register_agent_from_frontend(self, 
                                  tenant_id: str, 
                                  agent_id: str, 
                                  agent_config: Dict[str, Any],
                                  ctx: Context = None) -> None:
    """Registra un agente directamente con configuración proporcionada por el frontend
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        agent_config: Configuración completa del agente
        ctx: Contexto de operación
    """
    # Validar configuración con los estándares centralizados
    valid, error_msg = await self._validate_frontend_configs(
        tenant_id=tenant_id,
        tenant_tier=ctx.get_tenant_tier() if ctx else "free",
        agent_config=agent_config
    )
    
    if not valid:
        raise InvalidConfigError(f"Configuración inválida: {error_msg}")
    
    # Registrar en memoria (protegido por lock)
    async with self.registry_lock:
        if tenant_id not in self.agent_registry:
            self.agent_registry[tenant_id] = {}
        self.agent_registry[tenant_id][agent_id] = agent_config
    
    # Almacenar en caché (sin almacenar en Supabase ya que vino del frontend)
    await CacheManager.set(
        data_type="agent_config",
        resource_id=agent_id,
        value=agent_config,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard
    )
    
    logger.info(f"Agente {agent_id} registrado desde frontend para tenant {tenant_id}")
```

### 6.4 Validación de Configuraciones Frontend

Implementaremos un método especializado para validar las configuraciones recibidas del frontend:

```python
async def _validate_frontend_configs(self, tenant_id: str, tenant_tier: str, 
                                 agent_config: Dict[str, Any]) -> Tuple[bool, str]:
    """Valida las configuraciones proporcionadas por el frontend."""
    # Obtener configuraciones centralizadas
    from common.config.tiers import get_tier_limits, get_available_embedding_models, get_available_llm_models
    
    try:
        # Validar tier
        valid_tiers = ["free", "pro", "business", "enterprise"]
        if tenant_tier not in valid_tiers:
            return False, f"Tier inválido: {tenant_tier}"
        
        # Validar límites de tier
        tier_limits = get_tier_limits(tenant_tier, tenant_id)
        
        # Validar modelos permitidos
        if "embedding_model" in agent_config:
            allowed_embedding_models = get_available_embedding_models(tenant_tier, tenant_id)
            if agent_config["embedding_model"] not in allowed_embedding_models:
                return False, f"Modelo de embedding no permitido: {agent_config['embedding_model']}"
        
        if "llm_model" in agent_config:
            allowed_llm_models = get_available_llm_models(tenant_tier, tenant_id)
            if agent_config["llm_model"] not in allowed_llm_models:
                return False, f"Modelo LLM no permitido: {agent_config['llm_model']}"
        
        # Validar número de herramientas
        max_tools = tier_limits.get("max_tools_per_agent", 2)
        if "tools" in agent_config and len(agent_config["tools"]) > max_tools:
            return False, f"Número de herramientas excede el límite del tier: {len(agent_config['tools'])} > {max_tools}"
        
        # Agregar más validaciones según sea necesario...
        
        return True, ""
    except Exception as e:
        return False, f"Error validando configuración: {str(e)}"
```

### 6.5 Modificaciones al Método execute_agent

Actualizaremos el método `execute_agent` existente para soportar los parámetros adicionales del frontend:

```python
# Sección relevante de execute_agent modificada para soportar parámetros del frontend
async def execute_agent(self, 
                     input_text: str, 
                     collection_id: Optional[str] = None,
                     collection_metadata: Optional[Dict[str, Any]] = None,
                     tenant_tier: Optional[str] = None,
                     embedding_model: Optional[str] = None,
                     llm_model: Optional[str] = None,
                     use_auto_federation: bool = False,
                     use_streaming: bool = False,
                     ctx: Context = None) -> AgentResponse:
    # Código existente...
    
    # Verificar el tier si se proporciona desde frontend
    if tenant_tier:
        # Validar tier proporcionado
        from common.config.tiers import get_tier_limits
        tier_limits = get_tier_limits(tenant_tier, tenant_id)
    
    # Usar modelos especificados o por defecto según tier
    effective_embedding_model = embedding_model or agent_config.get("embedding_model", "text-embedding-3-small")
    effective_llm_model = llm_model or agent_config.get("llm_model", "gpt-3.5-turbo")
    
    # Validar modelos contra tier
    # [...implementación de validación...]
    
    # Usar metadatos de colección si se proporcionan
    if collection_metadata and collection_id:
        # Registrar metadatos en caché para uso futuro
        await CacheManager.set(
            data_type="collection_metadata",
            resource_id=collection_id,
            value=collection_metadata,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
```

### 6.6 Propagación de Configuraciones a Servicios Dependientes

Implementaremos la propagación de configuraciones del frontend a los servicios dependientes (Embedding Service y Query Service) para mantener la consistencia en todo el flujo de ejecución:

#### 6.6.1 Propagación al Embedding Service

Actualizaremos el método `get_embedding` del `ServiceRegistry` para propagar los modelos y metadatos del frontend:

```python
@handle_errors(error_type="service", log_traceback=True)
async def get_embedding(self, 
                        text: str, 
                        model: str = "text-embedding-3-small", 
                        metadata: Optional[Dict[str, Any]] = None,
                        ctx: Context = None) -> List[float]:
    """Obtiene embedding desde el Embedding Service (OpenAI)
    
    Args:
        text: Texto para generar embedding
        model: Modelo de embedding (OpenAI)
        metadata: Metadatos adicionales
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Embedding como lista de floats
        
    Raises:
        HTTPServiceError: Si hay error de comunicación
    """
    if not ctx:
        raise ValueError("Contexto requerido para obtener embedding")
        
    tenant_id = ctx.get_tenant_id()
    
    url = f"{self.embedding_service_url}/internal/embed"
    
    # Propagar todo el contexto en headers
    headers = propagate_context_to_headers({}, ctx)
    
    # Enriquecer metadata con información del contexto
    request_metadata = {
        "service_origin": "agent_service",
        "agent_id": ctx.get_agent_id(),
        "conversation_id": ctx.get_conversation_id(),
        "collection_id": ctx.get_collection_id()
    }
    
    # Combinar con metadata proporcionada
    if metadata:
        request_metadata.update(metadata)
    
    # Crear payload con modelo especificado (posiblemente desde frontend)
    data = {
        "text": text, 
        "model": model,
        "metadata": request_metadata
    }
    
    # Llamada al servicio con tracking
    response = await self._make_request("POST", url, headers, json=data)
    
    # Validar respuesta estándar
    if not response.get("success"):
        error_info = response.get("error", {})
        raise HTTPServiceError(
            f"Error del Embedding Service: {response.get('message')}",
            service="embedding",
            status_code=error_info.get("status_code", 500),
            details=error_info
        )
        
    return response["data"]["embedding"]
```

#### 6.6.2 Propagación al Query Service

Actualizaremos el método `query_with_sources` para propagar los modelos y metadatos del frontend:

```python
@handle_errors(error_type="service", log_traceback=True)
async def query_with_sources(self,
                          query: str,
                          collection_id: str,
                          similarity_top_k: int = 4,
                          embedding: Optional[List[float]] = None,
                          llm_model: Optional[str] = None,
                          ctx: Context = None) -> Dict[str, Any]:
    """Realiza una consulta RAG utilizando el Query Service (Groq)
    
    Args:
        query: Consulta textual del usuario
        collection_id: ID de la colección a consultar
        similarity_top_k: Número de resultados a retornar
        embedding: Embedding pre-generado (opcional)
        llm_model: Modelo LLM a utilizar (opcional, desde frontend)
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Resultados formateados con fuentes
    """
    if not ctx:
        raise ValueError("Contexto requerido para consultar con fuentes")
        
    tenant_id = ctx.get_tenant_id()
    
    url = f"{self.query_service_url}/internal/query"
    
    # Propagar todo el contexto en headers
    headers = propagate_context_to_headers({}, ctx)
    
    # Metadata para tracking
    metadata = {
        "service_origin": "agent_service",
        "agent_id": ctx.get_agent_id(),
        "conversation_id": ctx.get_conversation_id(),
    }
    
    # Si tenemos embedding pre-generado, enviarlo para evitar regeneración
    data = {
        "query": query,
        "collection_id": collection_id,
        "k": similarity_top_k,
        "query_embedding": embedding,
        "llm_model": llm_model,  # Propagar modelo LLM desde frontend
        "metadata": metadata
    }
    
    # Llamada al servicio con tracking
    response = await self._make_request("POST", url, headers, json=data)
    
    # Validar respuesta estándar
    if not response.get("success"):
        error_info = response.get("error", {})
        raise HTTPServiceError(
            f"Error del Query Service: {response.get('message')}",
            service="query",
            status_code=error_info.get("status_code", 500),
            details=error_info
        )
    
    return response["data"]
```

#### 6.6.3 Modificaciones a la Herramienta RAGQueryTool

Actualizaremos la herramienta RAG para soportar la propagación de configuraciones:

```python
class RAGQueryTool(BaseTool):
    name = "rag_query"
    description = "Consulta documentos relevantes para responder a una pregunta"
    args_schema = RAGQueryInput
    
    def __init__(self, 
                 service_registry, 
                 ctx: Context = None, 
                 collection_id: Optional[str] = None,
                 collection_metadata: Optional[Dict[str, Any]] = None,
                 embedding_model: Optional[str] = None,
                 llm_model: Optional[str] = None,
                 use_auto_federation: bool = False):
        """Inicializa la herramienta con opciones adicionales del frontend"""
        super().__init__(service_registry, ctx)
        self.collection_id = collection_id
        self.collection_metadata = collection_metadata
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.use_auto_federation = use_auto_federation
    
    async def _run_with_context(self, 
                              query: str, 
                              collection_id: Optional[str] = None, 
                              similarity_top_k: int = 4) -> str:
        """Ejecuta consulta RAG con propagación de parámetros completa"""
        # Priorizar collection_id del argumento, luego de la inicialización, luego default
        effective_collection_id = collection_id or self.collection_id
        if not effective_collection_id:
            raise ValueError("Se requiere collection_id para la herramienta RAG")
        
        # Verificar cache con patrón Cache-Aside estándar
        tenant_id = self.ctx.get_tenant_id()
        
        # Generar hash para cache
        query_hash = hashlib.md5(f"{query}:{effective_collection_id}:{similarity_top_k}".encode()).hexdigest()
        
        # Obtener resultado de cache si existe
        cached_result = await CacheManager.get(
            data_type="rag_result",
            resource_id=query_hash,
            tenant_id=tenant_id,
            agent_id=self.ctx.get_agent_id(),
            collection_id=effective_collection_id
        )
        
        if cached_result:
            return self._format_result(cached_result)
        
        # Obtener embedding con el modelo especificado (podría venir del frontend)
        embedding = await self.service_registry.get_embedding(
            text=query,
            model=self.embedding_model or "text-embedding-3-small",
            ctx=self.ctx
        )
        
        # Consultar con embedding pre-generado
        # Propagar llm_model si se especificó (podría venir del frontend)
        result = await self.service_registry.query_with_sources(
            query=query,
            collection_id=effective_collection_id,
            embedding=embedding,
            llm_model=self.llm_model,  # Propagar modelo LLM si se especificó
            ctx=self.ctx
        )
        
        # Guardar en cache
        await CacheManager.set(
            data_type="rag_result",
            resource_id=query_hash,
            value=result,
            tenant_id=tenant_id,
            agent_id=self.ctx.get_agent_id(),
            collection_id=effective_collection_id,
            ttl=CacheManager.ttl_short
        )
        
        return self._format_result(result)
```

### 6.7 Manejo de Selección de Colecciones y Federación

Implementaremos mecanismos para permitir que el usuario seleccione colecciones específicas mientras se mantiene la opción de federación automática:

#### 6.7.1 Estrategia de Selección de Colecciones

```python
class CollectionStrategy:
    """Estrategia de selección y federación de colecciones"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        
    async def get_effective_collections(self,
                                       query: str,
                                       explicit_collection_id: Optional[str] = None,
                                       use_auto_federation: bool = False,
                                       ctx: Context = None) -> List[Dict[str, Any]]:
        """Determina las colecciones a utilizar basándose en los parámetros y estrategia
        
        Args:
            query: Consulta del usuario
            explicit_collection_id: ID de colección explícitamente seleccionada por el usuario
            use_auto_federation: Activar federación automática
            ctx: Contexto con tenant_id y otros valores
            
        Returns:
            Lista de colecciones a consultar con metadatos relevantes
        """
        tenant_id = ctx.get_tenant_id()
        
        # Caso 1: Colección explícita sin federación
        if explicit_collection_id and not use_auto_federation:
            # Obtener metadatos de la colección especificada
            collection_info = await self._get_collection_info(tenant_id, explicit_collection_id, ctx)
            if not collection_info:
                raise CollectionNotFoundError(f"Colección no encontrada: {explicit_collection_id}")
            
            # Retornar únicamente la colección seleccionada
            return [{
                "collection_id": explicit_collection_id,
                "relevance_score": 1.0,  # Máxima relevancia para colección explícita
                "metadata": collection_info
            }]
        
        # Caso 2: Federación automática, posiblemente con prioridad para una colección explícita
        if use_auto_federation:
            # Obtener todas las colecciones relevantes mediante embedding similarity
            relevant_collections = await self._get_relevant_collections_by_similarity(query, tenant_id, ctx)
            
            # Si hay colección explícita, asegurar que esté incluida y con mayor peso
            if explicit_collection_id:
                collection_found = False
                
                # Verificar si la colección explícita ya está incluida
                for collection in relevant_collections:
                    if collection["collection_id"] == explicit_collection_id:
                        # Aumentar score de relevancia para priorizarla
                        collection["relevance_score"] = max(collection["relevance_score"], 0.95)
                        collection_found = True
                        break
                
                # Si no está incluida, agregarla
                if not collection_found:
                    collection_info = await self._get_collection_info(tenant_id, explicit_collection_id, ctx)
                    if collection_info:
                        relevant_collections.append({
                            "collection_id": explicit_collection_id,
                            "relevance_score": 0.9,  # Alta relevancia pero no máxima
                            "metadata": collection_info,
                            "explicitly_selected": True
                        })
            
            return relevant_collections
        
        # Caso 3: Default - Sin federación y sin colección explícita, usar colección default del tenant
        default_collection = await self._get_default_collection(tenant_id, ctx)
        
        if not default_collection:
            raise NoDefaultCollectionError("No se encontró colección por defecto para el tenant")
            
        return [{
            "collection_id": default_collection["id"],
            "relevance_score": 0.8,  # Relevancia media para colección por defecto
            "metadata": default_collection,
            "is_default": True
        }]
    
    async def _get_collection_info(self, tenant_id: str, collection_id: str, ctx: Context) -> Dict[str, Any]:
        """Obtiene información/metadatos de una colección"""
        # Intenta obtener de caché primero
        collection_info = await CacheManager.get(
            data_type="collection_metadata",
            resource_id=collection_id,
            tenant_id=tenant_id
        )
        
        if collection_info:
            return collection_info
        
        # Si no está en caché, obtener de Supabase
        try:
            from common.db.supabase import get_supabase_client, get_table_name
            
            supabase = get_supabase_client(tenant_id=tenant_id)
            table_name = get_table_name("collections")
            
            result = await supabase.table(table_name)\
                .select("*")\
                .eq("tenant_id", tenant_id)\
                .eq("id", collection_id)\
                .limit(1).execute()
            
            if result.data and len(result.data) > 0:
                collection_data = result.data[0]
                
                # Guardar en caché para futuros accesos
                await CacheManager.set(
                    data_type="collection_metadata",
                    resource_id=collection_id,
                    value=collection_data,
                    tenant_id=tenant_id,
                    ttl=CacheManager.ttl_standard
                )
                
                return collection_data
                
            return None
        except Exception as e:
            logger.error(f"Error al obtener info de colección {collection_id}: {str(e)}")
            return None
```

#### 6.7.2 Integración de Estrategia de Colecciones en el Flujo de Ejecución

```python
# Sección relevante de execute_agent actualizada para integrar la estrategia de colecciones
async def execute_agent(self, 
                     input_text: str, 
                     collection_id: Optional[str] = None,
                     collection_metadata: Optional[Dict[str, Any]] = None,
                     tenant_tier: Optional[str] = None,
                     embedding_model: Optional[str] = None,
                     llm_model: Optional[str] = None,
                     use_auto_federation: bool = False,
                     use_streaming: bool = False,
                     ctx: Context = None) -> AgentResponse:
    # [...código anterior...]
    
    # Determinar colecciones efectivas a utilizar
    collection_strategy = CollectionStrategy(self.service_registry)
    effective_collections = await collection_strategy.get_effective_collections(
        query=input_text,
        explicit_collection_id=collection_id,
        use_auto_federation=use_auto_federation,
        ctx=ctx
    )
    
    # Si se proporcionan metadatos de colección, actualizar la primera colección
    if collection_metadata and collection_id and effective_collections:
        for collection in effective_collections:
            if collection["collection_id"] == collection_id:
                collection["metadata"] = collection_metadata
                # Guardar en caché para uso futuro
                await CacheManager.set(
                    data_type="collection_metadata",
                    resource_id=collection_id,
                    value=collection_metadata,
                    tenant_id=tenant_id,
                    ttl=CacheManager.ttl_standard
                )
                break
    
    # Cargar herramientas considerando las colecciones efectivas
    tools = await self._load_agent_tools(
        tenant_id=tenant_id,
        agent_config=agent_config,
        ctx=ctx,
        collections=effective_collections,  # Pasar todas las colecciones relevantes
        embedding_model=effective_embedding_model,
        llm_model=effective_llm_model,
        use_auto_federation=use_auto_federation
    )
    
    # [...resto del código...]
```

## 7. Estándares y Mejores Prácticas

### 6.1 Patrón Respuesta Estandarizada
- Todas las respuestas deben seguir el formato:

```json
{
  "success": true,
  "message": "Operación completada con éxito",
  "data": { /* datos principales */ },
  "metadata": { /* metadatos adicionales */ },
  "error": null
}
```

### 5.2 Propagación de Contexto
- Todos los endpoints deben usar el decorador `@with_context` según corresponda:

```python
@with_context(tenant=True, agent=True, conversation=True)
async def execute_agent(
    tenant_id: str,
    agent_id: str,
    conversation_id: Optional[str] = None,
    input_text: str = Body(...),
    ctx: Context = None
):
    # El decorador garantiza validación y disponibilidad de IDs
```

### 5.3 Implementación del Patrón Cache-Aside
- Todos los servicios deben usar la función `get_with_cache_aside` para implementar caché:

```python
result, metrics = await get_with_cache_aside(
    data_type="embedding",
    resource_id=f"doc:{doc_id}",
    tenant_id=tenant_id,
    fetch_from_db_func=fetch_embedding_from_db,
    generate_func=generate_embedding_if_needed
)
```

## 6. Calendario de Implementación

| Semana | Enfoque Principal | Tareas Clave |
|--------|-------------------|--------------|
| 1 | Agent Service Core | LangChainAgentService, ServiceRegistry, Herramientas RAG |
| 2 | Refactorización Query Service | Modificación para aceptar embeddings, Integración RAG |
| 2-3 | Optimización Embedding Service | Tracking de tokens, Caché, Endpoints internos |
| 3 | Pruebas e Integración | Pruebas de flujo RAG, Pruebas de ingesta, Optimizaciones finales |

## 7. Documentación Adicional

Para más detalles sobre aspectos específicos, consultar:

- [Patrón Cache-Aside](docs/cache_aside_pattern.md)
- [Tracking de Tokens](docs/token_tracking.md)
- [Arquitectura de Microservicios](docs/microservices_architecture.md)
- [Guía LangChain](docs/langchain_guide.md)

## 8. Métricas de Éxito

- Tiempo de respuesta del Agent Service < 500ms (sin incluir tiempo LLM)
- Tasa de acierto de caché > 80% para embeddings
- Reducción de costos de API > 30% mediante caché y optimizaciones
- Zero downtime durante la migración a la nueva arquitectura
