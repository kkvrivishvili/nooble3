# Fase 1: Implementación del Agent Service Core

## Índice del documento

1. [Visión General](#visión-general)
2. [Implementación de LangChainAgentService](#11-implementación-de-langchainagentservice)
   - [1.1.1 Estructura básica de la clase](#111-estructura-básica-de-la-clase)
   - [1.1.2 Método de creación de agentes](#112-método-de-creación-de-agentes)
   - [1.1.3 Método de ejecución de agentes](#113-método-de-ejecución-de-agentes)
3. [Implementación de Métodos Auxiliares](#12-implementación-de-métodos-auxiliares)
   - [1.2.1 Carga de herramientas](#121-carga-de-herramientas)
   - [1.2.2 Creación del ejecutor del agente](#122-creación-del-executor-del-agente)
   - [1.2.3 Gestión de configuración de agentes](#123-gestión-de-configuración-de-agentes)
4. [Implementación del ServiceRegistry](#13-implementación-del-serviceregistry)
5. [Implementación de Herramientas (Tools)](#14-implementación-de-herramientas-tools)
   - [1.4.1 Herramienta base](#141-herramienta-base)
   - [1.4.2 Herramienta RAG](#142-herramienta-rag)
   - [1.4.3 Herramientas externas vía API](#143-herramientas-externas-vía-api)
6. [Implementación del Editor Visual](#15-implementación-del-editor-visual)
   - [1.5.1 API para el frontend](#151-api-para-el-frontend)
   - [1.5.2 Configuración de agentes visuales](#152-configuración-de-agentes-visuales)
7. [Sistema de Workflows Complejos](#16-sistema-de-workflows-complejos)
   - [1.6.1 AgentWorkflowManager](#161-agentworkflowmanager)
   - [1.6.2 Transformación de configuración visual a DAG](#162-transformación-de-configuración-visual-a-dag)
8. [Logging Detallado](#17-logging-detallado)
   - [1.7.1 Sistema de logs con contexto](#171-sistema-de-logs-con-contexto)
   - [1.7.2 Trazabilidad para depuración](#172-trazabilidad-para-depuración)
9. [Componentes Críticos y Consideraciones](#18-componentes-críticos-y-consideraciones)
10. [Tareas Pendientes](#tareas-pendientes)

## Visión General

Esta fase se centra en la implementación del núcleo del Agent Service, que sirve como **orquestador central** para la arquitectura RAG, manejando la interacción con otros servicios y proporcionando una interfaz unificada para los agentes basados en LangChain. El Agent Service NO gestiona directamente los proveedores de LLM o embeddings, sino que delega estas responsabilidades a los servicios especializados (Query Service y Embedding Service).

### Principios Clave

- **Separación de responsabilidades**: Agent Service es un orquestador, no un proveedor de modelos
- **Propagación de contexto**: Mantener tenant_id, agent_id, conversation_id en todas las operaciones
- **Optimización de caché**: Uso correcto de patrones Cache-Aside vs operaciones directas
- **Soporte para editor visual**: Preparado para integrarse con el frontend de configuración
- **Flujos complejos simplificados**: Interfaz simple para flujos de trabajo complejos
- **Logging detallado**: Sistema de logs estructurados para depuración del código

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
        # Nota: En la Fase 8 se implementará la estandarización de metadatos para compatibilidad con LlamaIndex,
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

## 1.3 Implementación del ConversationMemoryManager

El `ConversationMemoryManager` es un componente clave que proporciona la integración entre la memoria de LangChain y nuestro patrón Cache-Aside, permitiendo una gestión eficiente del historial de conversación.

```python
from datetime import datetime
from typing import Dict, Any, Optional, List
import time
import hashlib
import logging

from common.cache import CacheManager, get_with_cache_aside
from common.context.decorators import with_context, Context
from common.errors.handlers import handle_errors
from common.config import get_settings
from common.tracking import track_cache_metrics
from common.cache.helpers import standardize_llama_metadata
from common.db.supabase import get_supabase_client
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage

logger = logging.getLogger(__name__)

class ConversationMemoryManager:
    """Gestor de memoria de conversación con integración Cache-Aside.
    
    Esta clase maneja la persistencia y recuperación de memoria de conversación,
    utilizando el patrón Cache-Aside para optimizar rendimiento.
    """
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        self.settings = get_settings()
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Dict[str, Any]:
        """Recupera memoria de conversación usando Cache-Aside pattern.
        
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
        """Recupera memoria desde Supabase.
        
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
        """Guarda memoria en caché y opcionalmente en BD.
        
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
        
        # Persistir en DB si es necesario (por ejemplo, cada N mensajes)
        memory_config = self.settings.MEMORY_CONFIG
        message_count = memory_dict["metadata"]["message_count"]
        
        if memory_config.get("PERSIST_FREQUENCY") and message_count % memory_config["PERSIST_FREQUENCY"] == 0:
            await self._persist_memory_to_db(tenant_id, conversation_id, memory_dict)
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _persist_memory_to_db(self, tenant_id: str, conversation_id: str, memory_dict: Dict[str, Any]) -> None:
        """Persiste memoria a la base de datos.
        
        Args:
            tenant_id: ID del tenant
            conversation_id: ID de la conversación
            memory_dict: Diccionario con memoria a persistir
        """
        try:
            table_name = self.settings.TABLES["conversation_memories"]
            supabase = get_supabase_client()
            
            # Preparar registro para BD
            record = {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "messages": memory_dict.get("messages", []),
                "metadata": memory_dict.get("metadata", {}),
                "updated_at": datetime.now().isoformat()
            }
            
            # Verificar si existe o es nuevo
            result = (supabase.table(table_name)
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
```

### 1.3.1 Integración con LangChainAgentService

```python
async def _get_conversation_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Any:
    """Obtiene la memoria de conversación como objeto de LangChain.
    
    Args:
        tenant_id: ID del tenant
        conversation_id: ID de la conversación
        ctx: Contexto opcional
        
    Returns:
        Objeto de memoria de LangChain
        
    Raises:
        ServiceError: En caso de error de acceso a memoria
    """
    # Obtener memory_dict del ConversationMemoryManager
    memory_dict = await self.memory_manager.get_memory(tenant_id, conversation_id, ctx)
    
    # Convertir dict a objeto de memoria de LangChain
    if isinstance(memory_dict, dict):
        return self._dict_to_memory_object(memory_dict)
    
    return memory_dict

def _dict_to_memory_object(self, memory_dict: Dict[str, Any]) -> Any:
    """Convierte un diccionario a objeto de memoria de LangChain.
    
    Args:
        memory_dict: Diccionario con mensajes y metadata
        
    Returns:
        Objeto ConversationBufferMemory de LangChain
    """
    memory = ConversationBufferMemory(return_messages=True)
    
    # Validar estructura de mensajes
    if "messages" not in memory_dict or not isinstance(memory_dict["messages"], list):
        logger.warning("Estructura de mensajes inválida, creando memoria vacía")
        return memory
    
    # Reconstruir mensajes con validación
    for msg in memory_dict.get("messages", []):
        if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
            logger.warning(f"Mensaje con formato inválido ignorado: {msg}")
            continue
            
        try:
            if msg["role"] == "human":
                memory.chat_memory.add_message(HumanMessage(content=msg["content"]))
            elif msg["role"] == "ai":
                memory.chat_memory.add_message(AIMessage(content=msg["content"]))
            else:
                logger.warning(f"Rol de mensaje no soportado: {msg['role']}")
        except Exception as e:
            logger.error(f"Error añadiendo mensaje a memoria: {str(e)}")
    
    return memory

async def _save_conversation_memory(self, tenant_id: str, conversation_id: str, memory: Any, ctx: Context = None) -> None:
    """Guarda objeto de memoria de LangChain en el sistema de persistencia.
    
    Args:
        tenant_id: ID del tenant
        conversation_id: ID de la conversación
        memory: Objeto de memoria de LangChain
        ctx: Contexto opcional
    """
    if not hasattr(memory, "chat_memory") or not hasattr(memory.chat_memory, "messages"):
        logger.error("Objeto de memoria inválido, no se puede guardar")
        return
    
    # Convertir objeto de memoria a diccionario
    memory_dict = {
        "messages": [],
        "metadata": {
            "updated_at": datetime.now().isoformat(),
            "source": "langchain_memory"
        }
    }
    
    # Extraer mensajes del objeto de memoria
    for msg in memory.chat_memory.messages:
        if isinstance(msg, HumanMessage):
            memory_dict["messages"].append({"role": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            memory_dict["messages"].append({"role": "ai", "content": msg.content})
    
    # Guardar usando el ConversationMemoryManager
    await self.memory_manager.save_memory(tenant_id, conversation_id, memory_dict, ctx)
```

## 1.4 Implementación de Herramientas Especializadas

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

### 1.4.3 Herramientas Externas vía API

```python
from .base import BaseTool
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import httpx
from common.errors.handlers import handle_errors

class ExternalAPIInput(BaseModel):
    parameters: Dict[str, Any] = Field(description="Parámetros para la API externa")
    
class ExternalAPITool(BaseTool):
    """Herramienta para integración con APIs externas"""
    
    def __init__(self, 
                 service_registry, 
                 ctx: Optional[Context] = None,
                 name: str = "external_api",
                 description: str = "Conecta con una API externa",
                 endpoint: str = None,
                 method: str = "POST",
                 headers: Optional[Dict[str, str]] = None,
                 parameters: Optional[Dict[str, Any]] = None):
        """Inicializa la herramienta con configuración específica para la API"""
        super().__init__(service_registry, ctx)
        self.name = name
        self.description = description
        self.endpoint = endpoint
        self.method = method
        self.headers = headers or {}
        self.parameters = parameters or {}
        
        # Crear args_schema dinámico basado en los parámetros
        self._create_dynamic_schema()
    
    def _create_dynamic_schema(self):
        """Crea un schema dinámico basado en los parámetros configurados"""
        fields = {}
        for param_name, param_config in self.parameters.items():
            # Obtener tipo del parámetro (str, int, etc.)
            param_type = param_config.get("type", "string")
            param_desc = param_config.get("description", f"Parámetro {param_name}")
            param_required = param_config.get("required", False)
            
            # Convertir tipo de parámetro a tipo Python
            type_mapping = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": List,
                "object": Dict
            }
            python_type = type_mapping.get(param_type, str)
            
            # Añadir campo dinámico
            fields[param_name] = (Optional[python_type] if not param_required else python_type, 
                                 Field(description=param_desc))
        
        # Crear clase de modelo dinámico
        self.args_schema = pydantic.create_model(
            f"{self.name.title()}Input",
            **fields
        )
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _run_with_context(self, **kwargs) -> str:
        """Ejecuta la llamada a la API externa con los parámetros proporcionados"""
        if not self.endpoint:
            raise ValueError(f"No se ha configurado endpoint para la herramienta {self.name}")
            
        # Preparar headers con propagación de contexto
        headers = dict(self.headers)
        
        # Añadir headers de contexto
        if self.ctx:
            tenant_id = self.ctx.get_tenant_id()
            headers["x-tenant-id"] = tenant_id
            
            if self.ctx.get_agent_id():
                headers["x-agent-id"] = self.ctx.get_agent_id()
                
            if self.ctx.get_conversation_id():
                headers["x-conversation-id"] = self.ctx.get_conversation_id()
        
        # Preparar datos
        data = kwargs
        
        # Preparar parámetros para traceo
        safe_params = {k: v for k, v in data.items() 
                      if k not in self.parameters.get("sensitive_params", [])}
        
        # Log detallado para debugging
        logger.info(f"Llamando API externa {self.name} en {self.endpoint}", 
                  extra={"context": {"tool": self.name, "params": safe_params}})
        
        try:
            # Realizar petición HTTP
            if self.method.upper() == "GET":
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(self.endpoint, params=data, headers=headers)
            else:  # POST por defecto
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.endpoint, json=data, headers=headers)
            
            # Procesar respuesta
            try:
                result = response.json()
            except Exception:
                # Si no es JSON, usar texto
                result = {"text": response.text}
                
            # Formatear resultado para agente
            return self._format_api_result(result)
                
        except Exception as e:
            error_msg = f"Error llamando API externa {self.name}: {str(e)}"
            logger.error(error_msg, 
                        extra={"context": {"tool": self.name, "endpoint": self.endpoint}})
            return f"Error al consultar la API externa: {str(e)}"
    
    def _format_api_result(self, result: Dict[str, Any]) -> str:
        """Formatea el resultado de la API para consumo del agente"""
        if isinstance(result, dict):
            # Extraer campos relevantes según configuración
            if "message" in result:
                return str(result["message"])
            elif "data" in result:
                return str(result["data"])
            else:
                return str(result)
        else:
            return str(result)
```

## 1.5 Implementación del Editor Visual

### 1.5.1 API para el Frontend

```python
class AgentConfigurationService:
    """Servicio para gestionar configuraciones de agentes desde el frontend"""
    
    def __init__(self, tool_registry, service_registry):
        self.tool_registry = tool_registry
        self.service_registry = service_registry
        
    @handle_errors(error_type="service", log_traceback=True)
    async def get_available_tools(self, tenant_id: str, tier: str = None) -> Dict[str, List[Dict[str, Any]]]:
        """Obtiene lista de herramientas disponibles para el frontend"""
        # Si no se especifica tier, obtenerlo
        if not tier:
            tier = await self._get_tenant_tier(tenant_id)
            
        # Obtener herramientas internas disponibles
        internal_tools = []
        for name, metadata in self.tool_registry.tools.items():
            if self._is_tool_allowed_for_tier(tier, metadata.tier_requirement):
                internal_tools.append({
                    "name": name,
                    "description": metadata.description,
                    "category": metadata.category,
                    "config_schema": self._get_tool_schema(name)
                })
                
        # Obtener herramientas externas disponibles
        external_tools = []
        for name, metadata in self.tool_registry.external_api_tools.items():
            if self._is_tool_allowed_for_tier(tier, metadata.tier_requirement):
                external_tools.append({
                    "name": name,
                    "description": metadata.description,
                    "category": metadata.category,
                    "api_details": {
                        "endpoint": metadata.endpoint,
                        "method": metadata.method,
                        "parameter_schema": metadata.parameters
                    }
                })
                
        return {
            "internal_tools": internal_tools,
            "external_tools": external_tools
        }
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_available_collections(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Obtiene colecciones disponibles para configurar agentes"""
        # Llamar al Query Service para obtener colecciones
        response = await self.service_registry.call_query_service(
            endpoint="collections",
            method="GET",
            tenant_id=tenant_id
        )
        
        if not response.get("success"):
            logger.error(f"Error al obtener colecciones: {response.get('message')}")
            return []
            
        collections = response.get("data", [])
        
        # Formatear para frontend
        return [
            {
                "id": collection.get("collection_id"),
                "name": collection.get("name", "Sin nombre"),
                "description": collection.get("description", ""),
                "document_count": collection.get("document_count", 0),
                "created_at": collection.get("created_at")
            }
            for collection in collections
        ]
```

### 1.5.2 Configuración de Agentes Visuales

```python
@handle_errors(error_type="service", log_traceback=True)
async def create_agent_from_frontend_config(self, 
                                        config: Dict[str, Any], 
                                        tenant_id: str,
                                        ctx: Context) -> str:
    """Crea un agente a partir de configuración del frontend"""
    # Validar configuración mínima
    if not config.get("name"):
        raise ValueError("El nombre del agente es obligatorio")
        
    # Validar límites del tenant
    tier = await self._get_tenant_tier(tenant_id)
    
    # Obtener límites del tier desde la config centralizada
    from common.config.tiers import get_tier_limits
    tier_limits = get_tier_limits(tier, tenant_id)
    
    # Verificar límites específicos para agentes personalizados
    max_agents = tier_limits.get("max_agents", 1)
    max_tools_per_agent = tier_limits.get("max_tools_per_agent", 2)
    
    # Contar agentes existentes
    current_agents_count = await self._count_tenant_agents(tenant_id)
    
    if current_agents_count >= max_agents:
        raise TierLimitExceededError(
            f"Límite de agentes personalizados excedido ({current_agents_count}/{max_agents})",
            tier=tier,
            limit_name="max_agents",
            current_value=current_agents_count,
            limit_value=max_agents
        )
        
    # Validar herramientas - Asegurar que están disponibles para el tier
    tools = config.get("tools", [])
    if len(tools) > max_tools_per_agent:
        raise TierLimitExceededError(
            f"Excedido el límite de herramientas por agente ({len(tools)}/{max_tools_per_agent})"
        )
        
    # Transformar configuración del frontend a formato interno
    internal_config = self._transform_frontend_config(config, tier)
    
    # Crear el agente
    agent_service = LangChainAgentService()
    agent_id = await agent_service.create_agent(internal_config, ctx)
    
    return agent_id
    
def _transform_frontend_config(self, frontend_config: Dict[str, Any], tier: str) -> Dict[str, Any]:
    """Transforma la configuración proveniente del frontend al formato interno"""
    # Estructura base de la configuración interna
    internal_config = {
        "name": frontend_config.get("name"),
        "description": frontend_config.get("description", ""),
        "type": frontend_config.get("type", "conversational"),
        "system_prompt": frontend_config.get("system_prompt", "You are a helpful assistant."),
        "tools": [],
        "tool_config": {},
        "embedding_model": frontend_config.get("embedding_model"),
        "llm_model": frontend_config.get("llm_model"),
        "temperature": frontend_config.get("temperature", 0.7),
        "max_tokens": frontend_config.get("max_tokens", 1000),
        "metadata": {
            "created_from_editor": True,
            "creation_timestamp": datetime.now().isoformat(),
            "tier": tier
        }
    }
    
    # Procesar herramientas seleccionadas
    for tool in frontend_config.get("tools", []):
        # Añadir nombre de la herramienta a la lista
        internal_config["tools"].append(tool["name"])
        
        # Añadir configuración específica de la herramienta
        if "config" in tool:
            internal_config["tool_config"][tool["name"]] = tool["config"]
            
    # Procesar colecciones
    if "collections" in frontend_config:
        internal_config["collections"] = frontend_config["collections"]
        
    # Procesar configuración de memoria
    if "memory_config" in frontend_config:
        internal_config["memory_config"] = frontend_config["memory_config"]
    else:
        # Configuración por defecto
        internal_config["memory_config"] = {
            "max_history": 10,
            "type": "conversation_buffer"
        }
    
    return internal_config
```

## 1.6 Sistema de Workflows Complejos

### 1.6.1 AgentWorkflowManager

```python
class AgentWorkflowManager:
    """Gestor de flujos de trabajo complejos con interfaz simplificada"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        self.workflow_registry = {}
    
    @handle_errors(error_type="service", log_traceback=True)
    async def register_workflow(self, workflow_config: Dict[str, Any], tenant_id: str) -> str:
        """Registra un nuevo flujo de trabajo basado en configuración simple"""
        workflow_id = workflow_config.get("id", str(uuid.uuid4()))
        
        # Transformar configuración simple a DAG interno
        internal_workflow = self._transform_to_internal_workflow(workflow_config)
        
        # Registrar workflow en caché
        await CacheManager.set(
            data_type="agent_workflow",
            resource_id=workflow_id,
            value=internal_workflow,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
        
        # Guardar en base de datos para persistencia
        await self._store_workflow_in_db(workflow_id, tenant_id, internal_workflow)
        
        # Registrar workflow en memoria para acceso rápido
        self.workflow_registry[f"{tenant_id}:{workflow_id}"] = internal_workflow
        
        return workflow_id
    
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_workflow(self, workflow_id: str, input_data: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        """Ejecuta un flujo de trabajo complejo con interfaz simplificada"""
        tenant_id = ctx.get_tenant_id()
        workflow_key = f"{tenant_id}:{workflow_id}"
        
        # Intentar obtener workflow de memoria
        workflow = self.workflow_registry.get(workflow_key)
        
        # Si no está en memoria, intentar obtener de caché
        if not workflow:
            workflow, _ = await get_with_cache_aside(
                data_type="agent_workflow",
                resource_id=workflow_id,
                tenant_id=tenant_id,
                fetch_from_db_func=lambda: self._fetch_workflow_from_db(workflow_id, tenant_id),
                generate_func=None  # No hay generación dinámica
            )
            
            # Guardar en registro en memoria
            if workflow:
                self.workflow_registry[workflow_key] = workflow
                
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} no encontrado")
        
        # Crear espacio de trabajo para la ejecución
        workspace = {
            "input": input_data,
            "output": {},
            "state": {},
            "context": ctx
        }
        
        # Ejecutar cada paso del workflow en secuencia (o en paralelo según config)
        result = await self._execute_workflow_steps(workflow, workspace)
        
        # Formatear resultado final
        return self._format_workflow_result(workflow, result)
```

### 1.6.2 Transformación de Configuración Visual a DAG

```python
def _transform_to_internal_workflow(self, simple_config: Dict[str, Any]) -> Dict[str, Any]:
    """Transforma configuración simple a representación interna compleja"""
    # Implementación que abstrae la complejidad
    internal_workflow = {
        "steps": [],
        "dependencies": {},
        "output_mapping": {}
    }
    
    # Transformar pasos simples a DAG interno
    for step in simple_config.get("steps", []):
        # Añadir paso con todas las propiedades necesarias
        internal_workflow["steps"].append({
            "id": step.get("id", f"step_{len(internal_workflow['steps'])+1}"),
            "action": step.get("action"),
            "config": step.get("config", {}),
            "input_mapping": step.get("input", {}),
            "condition": step.get("condition"),
            "retry_config": step.get("retry", {"max_attempts": 1})  # Configuración de reintentos
        })
        
        # Procesar dependencias
        if "depends_on" in step:
            step_id = step.get("id", f"step_{len(internal_workflow['steps'])}")
            internal_workflow["dependencies"][step_id] = step["depends_on"]
            
    # Procesar mapeo de salida
    if "output" in simple_config:
        internal_workflow["output_mapping"] = simple_config["output"]
        
    return internal_workflow

async def _execute_workflow_steps(self, workflow: Dict[str, Any], workspace: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta los pasos del workflow respetando dependencias"""
    # Seguimiento de pasos completados
    completed_steps = set()
    step_results = {}
    all_steps = {step["id"]: step for step in workflow["steps"]}
    
    # Obtener dependencias inversas
    dependencies = workflow.get("dependencies", {})
    
    # Determinar orden de ejecución
    execution_order = self._compute_execution_order(workflow)
    
    # Ejecutar pasos en orden
    for step_id in execution_order:
        step = all_steps[step_id]
        
        # Verificar que todas las dependencias estén completadas
        if step_id in dependencies:
            deps = dependencies[step_id]
            if not all(dep in completed_steps for dep in deps):
                raise ValueError(f"Dependencias de paso {step_id} no completadas")
                
        # Preparar entradas para este paso
        step_input = self._prepare_step_input(step, workspace, step_results)
        
        # Verificar condición
        if "condition" in step and step["condition"]:
            condition_result = self._evaluate_condition(step["condition"], workspace, step_results)
            if not condition_result:
                # Saltar este paso pero marcarlo como completado
                completed_steps.add(step_id)
                step_results[step_id] = {"skipped": True}
                continue
                
        # Ejecutar paso
        try:
            result = await self._execute_workflow_step(step, step_input, workspace["context"])
            step_results[step_id] = result
            completed_steps.add(step_id)
            
            # Actualizar workspace con resultado
            workspace["state"][step_id] = result
        except Exception as e:
            # Manejar error según configuración de reintentos
            retry_config = step.get("retry_config", {"max_attempts": 1})
            max_attempts = retry_config.get("max_attempts", 1)
            
            if max_attempts > 1:
                # Implementar lógica de reintentos
                pass
            else:
                raise WorkflowStepError(f"Error en paso {step_id}: {str(e)}") from e
                
    # Aplicar mapeo de salida
    output = {}
    for output_key, mapping in workflow.get("output_mapping", {}).items():
        # Formato de mapping: "step_id.result_key"
        if isinstance(mapping, str) and "." in mapping:
            step_id, result_key = mapping.split(".", 1)
            if step_id in step_results:
                result = step_results[step_id]
                if result_key in result:
                    output[output_key] = result[result_key]
        elif isinstance(mapping, dict) and "value" in mapping:
            # Valor estático
            output[output_key] = mapping["value"]
            
    return output
```

## 1.7 Logging Detallado

### 1.7.1 Sistema de Logs con Contexto

```python
# Configuración de logging detallado
import logging
import json
from datetime import datetime
import functools

class DetailedLogFormatter(logging.Formatter):
    """Formateador personalizado para logs estructurados detallados"""
    
    def format(self, record):
        """Formatea el registro con datos contextuales adicionales"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Añadir contexto si existe
        if hasattr(record, "context"):
            log_data["context"] = record.context
            
        # Añadir traceback si existe
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }
            
        return json.dumps(log_data)

# Inicialización de logger con formato detallado
def setup_detailed_logging():
    logger = logging.getLogger("agent_service")
    logger.setLevel(logging.DEBUG)
    
    # Handler para consola con formato detallado
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(DetailedLogFormatter())
    logger.addHandler(console_handler)
    
    # Handler para archivo con formato detallado
    file_handler = logging.FileHandler("agent_service_debug.log")
    file_handler.setFormatter(DetailedLogFormatter())
    logger.addHandler(file_handler)
    
    return logger
```

### 1.7.2 Trazabilidad para Depuración

```python
# Decorator para logging contextual
def with_logging_context(func):
    """Decorator que añade contexto al logging"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extraer contexto
        ctx = kwargs.get("ctx")
        context_data = {}
        
        if ctx:
            # Extraer datos relevantes del contexto para logging
            context_data = {
                "tenant_id": ctx.get_tenant_id(),
                "agent_id": ctx.get_agent_id(),
                "conversation_id": ctx.get_conversation_id()
            }
        
        # Log de inicio con contexto
        logger.info(f"Iniciando {func.__name__}", extra={"context": context_data})
        
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            # Log de éxito
            execution_time = time.time() - start_time
            logger.info(f"Completado {func.__name__} en {execution_time:.3f}s", 
                       extra={"context": {**context_data, "execution_time": execution_time}})
            return result
        except Exception as e:
            # Log detallado de error
            execution_time = time.time() - start_time
            logger.exception(f"Error en {func.__name__}: {str(e)}", 
                            extra={"context": {**context_data, 
                                              "execution_time": execution_time,
                                              "error_type": type(e).__name__}})
            raise
            
    return wrapper
```
```

## Tareas Pendientes

- [ ] Implementar LangChainAgentService completo con manejo de errores tipados
- [ ] Implementar ServiceRegistry con propagación de contexto completa
- [ ] Desarrollar herramientas básicas para el agente (RAG, embedding, etc.)
- [ ] Desarrollar herramientas de API externas configurables
- [ ] Implementar memoria de conversación con Supabase
- [ ] Implementar endpoints FastAPI con decorador @with_context
- [ ] Desarrollar API para editor visual de frontend
- [ ] Implementar sistema de logging detallado con contexto
