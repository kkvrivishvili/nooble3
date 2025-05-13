# Fase 1: Implementación del Agent Service Core

## Visión General

Esta fase se centra en la implementación del núcleo del Agent Service, que servirá como orquestador central para la arquitectura RAG, manejando la interacción con otros servicios y proporcionando una interfaz unificada para los agentes.

## 1.1 Implementación de LangChainAgentService

### 1.1.1 Estructura Básica de la Clase

```python
class LangChainAgentService:
    def __init__(self):
        self.service_registry = None
        self.agent_registry = {}  # Registro de agentes disponibles por tenant
        self.integration_registry = {}  # Registro de integraciones disponibles
        self.registry_lock = asyncio.Lock()  # Para acceso thread-safe a registros
        
    async def initialize(self):
        """Inicializa el servicio y carga configuraciones necesarias"""
        # Inicializar ServiceRegistry
        self.service_registry = ServiceRegistry()
        
        # Inicializar registros con valores por defecto
        await self._load_default_agents()
        await self._register_integrations()
        
        logger.info("LangChainAgentService inicializado correctamente")
```

### 1.1.2 Método de Creación de Agentes

```python
@handle_errors(error_type="service", log_traceback=True)
async def create_agent(self, agent_config: AgentConfig, ctx: Context = None) -> str:
    """Crea un agente LCEL con configuración dinámica
    
    Args:
        agent_config: Configuración del agente
        ctx: Contexto con tenant_id
        
    Returns:
        ID del agente creado
    """
    # Validar ctx y obtener tenant_id
    if not ctx:
        raise ValueError("Contexto requerido para crear agente")
        
    tenant_id = ctx.get_tenant_id()
    
    # Validar configuración del agente
    self._validate_agent_config(agent_config, tenant_id)
    
    # Generar ID si no se proporciona
    agent_id = agent_config.get("id", str(uuid.uuid4()))
    
    # Registrar agente en memoria (protegido por lock)
    async with self.registry_lock:
        if tenant_id not in self.agent_registry:
            self.agent_registry[tenant_id] = {}
        self.agent_registry[tenant_id][agent_id] = agent_config
    
    # Almacenar en caché siguiendo el patrón Cache-Aside
    await CacheManager.set(
        data_type="agent_config", 
        resource_id=agent_id,
        value=agent_config,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard
    )
    
    # Guardar en base de datos para persistencia
    await self._store_agent_config_in_db(tenant_id, agent_id, agent_config)
    
    return agent_id
```

### 1.1.3 Método de Ejecución de Agentes

```python
@handle_errors(error_type="service", log_traceback=True)
async def execute_agent(self, 
                     input_text: str, 
                     collection_id: Optional[str] = None,
                     collection_metadata: Optional[Dict[str, Any]] = None,
                     tenant_tier: Optional[str] = None,
                     embedding_model: Optional[str] = None,
                     llm_model: Optional[str] = None,
                     use_auto_federation: bool = False,
                     use_streaming: bool = False,
                     use_async: bool = False,
                     ctx: Context = None) -> AgentResponse:
    """Ejecuta un agente con memoria de conversación persistente
    
    Args:
        input_text: Texto de entrada del usuario
        collection_id: ID de colección específica seleccionada por el usuario (opcional)
        collection_metadata: Metadatos completos de la colección (opcional)
        tenant_tier: Tier del tenant (free, pro, business, enterprise)
        embedding_model: Modelo de embedding a utilizar
        llm_model: Modelo LLM a utilizar
        use_auto_federation: Flag para activar la federación automática (False por defecto)
        use_streaming: Usar respuestas en streaming
        use_async: Flag para ejecutar de forma asíncrona usando el sistema de colas (Fase 7)
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
    
    # Opción para ejecución asíncrona con sistema de colas (Fase 7)
    # Si se solicita ejecución asíncrona, registramos el trabajo y retornamos el job_id
    if use_async:
        work_queue_service = WorkQueueService()
        job_params = {
            "input_text": input_text,
            "collection_id": collection_id,
            "use_auto_federation": use_auto_federation,
            "embedding_model": embedding_model,
            "llm_model": llm_model
        }
        
        job_id = await work_queue_service.register_job(
            tenant_id=tenant_id,
            job_type="agent_execution",
            params=job_params,
            task="execute_agent"
        )
        
        return AgentResponse(
            agent_id=agent_id,
            conversation_id=conversation_id,
            async_job_id=job_id,  # ID del trabajo para seguimiento
            is_async=True
        )
    
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
    
    # Verificar el tier si se proporciona desde frontend
    if tenant_tier:
        # Validar tier proporcionado
        from common.config.tiers import get_tier_limits
        tier_limits = get_tier_limits(tenant_tier, tenant_id)
    else:
        # Obtener tier desde la base de datos o configuración
        tenant_tier = await self._get_tenant_tier(tenant_id)
        
    # Preparar metadatos de la colección
    if collection_id and not collection_metadata:
        # Si se proporciona collection_id pero no metadata, obtener metadata
        collection_metadata = await self._fetch_collection_metadata(
            tenant_id=tenant_id,
            collection_id=collection_id
        )
        
    # Obtener modelo de embedding apropiado
    effective_embedding_model = embedding_model or agent_config.get(
        "embedding_model", 
        "text-embedding-3-small"  # Modelo por defecto
    )
    
    # Obtener modelo LLM apropiado
    effective_llm_model = llm_model or agent_config.get(
        "llm_model",
        "gpt-3.5-turbo"  # Modelo por defecto
    )
        
    # Validar que los modelos seleccionados estén permitidos para el tier
    from common.config.tiers import get_available_embedding_models, get_available_llm_models
    
    allowed_embedding_models = get_available_embedding_models(tenant_tier, tenant_id)
    if effective_embedding_model not in allowed_embedding_models:
        # Usar el primer modelo disponible como fallback
        effective_embedding_model = allowed_embedding_models[0]
        logger.warning(f"Modelo embedding {effective_embedding_model} no permitido para tier {tenant_tier}, usando {allowed_embedding_models[0]}")
        
    allowed_llm_models = get_available_llm_models(tenant_tier, tenant_id)
    if effective_llm_model not in allowed_llm_models:
        # Usar el primer modelo disponible como fallback
        effective_llm_model = allowed_llm_models[0]
        logger.warning(f"Modelo LLM {effective_llm_model} no permitido para tier {tenant_tier}, usando {allowed_llm_models[0]}")
    
    # Determinar colecciones efectivas a utilizar
    collection_strategy = CollectionStrategy(self.service_registry)
    effective_collections = await collection_strategy.get_effective_collections(
        query=input_text,
        explicit_collection_id=collection_id,
        use_auto_federation=use_auto_federation,
        ctx=ctx
    )
    
    # Si se proporcionan metadatos de colección, actualizar
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
    
    # Cargar herramientas para el agente según configuración
    tools = await self._load_agent_tools(
        tenant_id=tenant_id,
        agent_config=agent_config,
        ctx=ctx,
        collections=effective_collections,
        embedding_model=effective_embedding_model,
        llm_model=effective_llm_model,
        use_auto_federation=use_auto_federation
    )
    
    # Crear agente LCEL con parámetros adicionales
    agent_executor = await self._create_agent_executor(
        agent_config=agent_config,
        tools=tools,
        memory=memory,
        llm_model=effective_llm_model,
        streaming=use_streaming,
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
```

## 1.2 Implementación de Métodos Auxiliares

### 1.2.1 Carga de Herramientas

```python
async def _load_agent_tools(self, tenant_id: str, agent_config: Dict[str, Any], 
                         ctx: Context = None, collections: List[Dict[str, Any]] = None,
                         embedding_model: Optional[str] = None,
                         llm_model: Optional[str] = None,
                         use_auto_federation: bool = False) -> List[BaseTool]:
    """Carga herramientas para el agente según configuración
    
    Args:
        tenant_id: ID del tenant
        agent_config: Configuración del agente
        ctx: Contexto con tenant_id, agent_id, etc.
        collections: Lista de colecciones a utilizar
        embedding_model: Modelo de embedding a utilizar
        llm_model: Modelo LLM a utilizar
        use_auto_federation: Flag para activar federación automática (False por defecto)
        
    Returns:
        Lista de herramientas para el agente
    """
    tools = []
    
    # Obtener herramientas de la configuración del agente
    agent_tools = agent_config.get("tools", [])
    
    # Cargar herramientas según configuración
    for tool_name in agent_tools:
        if tool_name == "rag_query":
            # Usar la primera colección si hay múltiples
            collection_id = collections[0]["collection_id"] if collections else None
            collection_metadata = collections[0].get("metadata", {}) if collections else None
            
            # Crear herramienta RAG con todos los parámetros proporcionados
            rag_tool = RAGQueryTool(
                service_registry=self.service_registry,
                ctx=ctx,
                collection_id=collection_id,
                collection_metadata=collection_metadata,
                embedding_model=embedding_model,
                llm_model=llm_model,
                use_auto_federation=use_auto_federation
            )
            tools.append(rag_tool)
            
        elif tool_name == "embedding_tool":
            # Herramienta para generación directa de embeddings
            embedding_tool = EmbeddingTool(
                service_registry=self.service_registry,
                ctx=ctx,
                model=embedding_model
            )
            tools.append(embedding_tool)
            
        # Otras herramientas según configuración...
            
    return tools
```

### 1.2.2 Creación del Executor del Agente

```python
async def _create_agent_executor(self, agent_config: Dict[str, Any], 
                              tools: List[BaseTool], memory: Any,
                              llm_model: Optional[str] = None,
                              streaming: bool = False,
                              context_window_limit: Optional[int] = None,
                              max_output_tokens: Optional[int] = None,
                              ctx: Context = None) -> Any:
    """Crea un executor de agente LCEL con la configuración proporcionada
    
    Args:
        agent_config: Configuración del agente
        tools: Lista de herramientas disponibles
        memory: Memoria de conversación
        llm_model: Modelo LLM a utilizar (opcional)
        streaming: Flag para activar respuestas en streaming
        context_window_limit: Límite de contexto para el modelo
        max_output_tokens: Máximo de tokens de salida
        ctx: Contexto de ejecución
        
    Returns:
        Executor del agente configurado
    """
    # Implementación con LCEL (LangChain Expression Language)
    # Esta sección variará dependiendo de la versión de LangChain y las necesidades específicas
    pass
```

### 1.2.3 Gestión de Configuración de Agentes

```python
async def _fetch_agent_config_from_db(self, agent_id: str, tenant_id: str) -> Dict[str, Any]:
    """Obtiene la configuración de un agente desde la base de datos
    
    Args:
        agent_id: ID del agente
        tenant_id: ID del tenant
        
    Returns:
        Configuración del agente
    """
    # Implementación con supabase...
    pass
    
async def _fetch_collection_metadata(self, tenant_id: str, collection_id: str) -> Dict[str, Any]:
    """Obtiene metadatos de una colección desde la base de datos
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        
    Returns:
        Metadatos de la colección
    """
    # Implementación con supabase...
    pass
    
async def _get_tenant_tier(self, tenant_id: str) -> str:
    """Obtiene el tier de un tenant
    
    Args:
        tenant_id: ID del tenant
        
    Returns:
        Tier del tenant (free, pro, business, enterprise)
    """
    # Implementación con supabase o servicio de autenticación...
    pass
```

## 1.3 Implementación del ServiceRegistry

```python
from common.context import Context, propagate_context_to_headers
from common.errors.handlers import handle_errors, HTTPServiceError
from common.models.base import BaseResponse
from common.config import get_service_settings

class ServiceRegistry:
    def __init__(self):
        # Obtener configuración centralizada usando el sistema estándar
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
        
        # Crear payload con modelo especificado
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

## 1.4 Implementación de Herramientas (Tools)

### 1.4.1 Herramienta Base

```python
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
```

### 1.4.2 Herramienta RAG

```python
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
    
    def __init__(self, 
                 service_registry, 
                 ctx: Context = None, 
                 collection_id: Optional[str] = None,
                 collection_metadata: Optional[Dict[str, Any]] = None,
                 embedding_model: Optional[str] = None,
                 llm_model: Optional[str] = None,
                 use_auto_federation: bool = False):
        """Inicializa la herramienta con opciones adicionales"""
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
        # Priorizar collection_id del argumento, luego de la inicialización
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
        
        # Obtener embedding con el modelo especificado
        embedding = await self.service_registry.get_embedding(
            text=query,
            model=self.embedding_model or "text-embedding-3-small",
            ctx=self.ctx
        )
        
        # Consultar con embedding pre-generado
        result = await self.service_registry.query_with_sources(
            query=query,
            collection_id=effective_collection_id,
            embedding=embedding,
            llm_model=self.llm_model,
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
        
    def _format_result(self, result: Dict[str, Any]) -> str:
        """Formatea el resultado RAG para consumo del agente"""
        formatted = f"Respuesta encontrada: {result['response']}\n\nFuentes:\n"
        
        for i, source in enumerate(result.get('sources', []), 1):
            formatted += f"[{i}] {source.get('text', '')}\n"
            if source.get('document_id'):
                formatted += f"   Documento: {source.get('document_id')}\n"
                
        return formatted
```

## Tareas Pendientes

- [ ] Implementar LangChainAgentService completo con manejo de errores tipados
- [ ] Implementar ServiceRegistry con propagación de contexto completa
- [ ] Desarrollar herramientas básicas para el agente (RAG, embedding, etc.)
- [ ] Implementar memoria de conversación con Supabase
- [ ] Implementar endpoints FastAPI con decorador @with_context
