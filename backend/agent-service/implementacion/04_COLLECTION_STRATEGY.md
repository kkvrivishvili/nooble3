# Fase 4: Estrategia de Colecciones

## Visión General

La implementación de una estrategia efectiva para gestionar colecciones es crucial para el Agent Service. Esta fase introduce un mecanismo que permite seleccionar colecciones explícitamente desde el frontend y manejar la federación automática cuando sea necesario, optimizando así la búsqueda y recuperación de información.

## 4.1 CollectionStrategy

### 4.1.1 Implementación de la Clase CollectionStrategy

```python
from typing import List, Dict, Any, Optional, Union
from common.context import Context
from common.errors.handlers import handle_errors
from common.tracking import track_token_usage

class CollectionStrategy:
    """
    Gestiona la estrategia de selección de colecciones basada en la entrada del usuario y el contexto.
    
    Soporta:
    - Selección explícita de colecciones desde el frontend
    - Federación automática cuando está habilitada
    - Preferencias de colecciones basadas en el contexto
    """
    
    def __init__(self, tenant_id: str, ctx: Optional[Context] = None):
        """
        Inicializa la estrategia de colecciones.
        
        Args:
            tenant_id: ID del tenant
            ctx: Contexto opcional con información adicional
        """
        self.tenant_id = tenant_id
        self.ctx = ctx
        self._selected_collections = []
        self._metadata = {}
        self._use_auto_federation = False
    
    @handle_errors(error_type="service", log_traceback=True)
    async def configure(self, 
                      collection_id: Optional[str] = None,
                      collection_metadata: Optional[Dict[str, Any]] = None,
                      use_auto_federation: bool = False) -> "CollectionStrategy":
        """
        Configura la estrategia de colecciones.
        
        Args:
            collection_id: ID de colección explícitamente seleccionada
            collection_metadata: Metadatos adicionales para la colección
            use_auto_federation: Si se debe usar federación automática
            
        Returns:
            La instancia de CollectionStrategy (para encadenamiento)
        """
        # Guardar configuración básica
        # Guardar metadatos (En Fase 8 se estandarizarán para compatibilidad entre LlamaIndex y LangChain)
        self._metadata = collection_metadata or {}
        self._use_auto_federation = use_auto_federation
        
        # Si se proporciona un collection_id explícito, usarlo
        if collection_id:
            try:
                collection = await self._get_collection_by_id(collection_id)
                if collection:
                    self._selected_collections = [collection]
                    return self
                else:
                    # Si la colección no existe o no es accesible, registrar advertencia
                    logger.warning(
                        f"Colección {collection_id} no encontrada o no accesible",
                        extra={
                            "tenant_id": self.tenant_id,
                            "collection_id": collection_id,
                            "service": "collection_strategy",
                            "operation": "configure"
                        }
                    )
            except Exception as e:
                logger.error(
                    f"Error accediendo a la colección {collection_id}",
                    extra={
                        "tenant_id": self.tenant_id,
                        "collection_id": collection_id,
                        "error": str(e),
                        "service": "collection_strategy",
                        "operation": "configure"
                    }
                )
        
        # Si no hay colección explícita y la federación automática está activada
        if use_auto_federation:
            collections = await self._get_federated_collections()
            self._selected_collections = collections
        
        # Si no hay colecciones seleccionadas después del proceso, usar colección por defecto
        if not self._selected_collections:
            default_collection = await self._get_default_collection()
            if default_collection:
                self._selected_collections = [default_collection]
        
        return self
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_collections(self) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de colecciones seleccionadas.
        
        Returns:
            Lista de colecciones seleccionadas
        """
        return self._selected_collections
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_collection_ids(self) -> List[str]:
        """
        Obtiene los IDs de las colecciones seleccionadas.
        
        Returns:
            Lista de IDs de colecciones
        """
        return [c["id"] for c in self._selected_collections]
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_primary_collection_id(self) -> Optional[str]:
        """
        Obtiene el ID de la colección primaria (la primera seleccionada).
        
        Returns:
            ID de la colección primaria o None si no hay colecciones
        """
        if not self._selected_collections:
            return None
        return self._selected_collections[0]["id"]
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _get_collection_by_id(self, collection_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la información de una colección por su ID.
        
        Args:
            collection_id: ID de la colección
            
        Returns:
            Información de la colección o None si no existe
        """
        try:
            # Utilizar el Ingestion Service para obtener la colección
            response = await call_service(
                service_name="ingestion-service",
                endpoint="/internal/collection",
                method="GET",
                params={"collection_id": collection_id},
                headers={"X-Tenant-ID": self.tenant_id},
            )
            
            if response["success"]:
                return response["data"]
            return None
        except Exception as e:
            logger.error(
                f"Error al obtener colección {collection_id}: {str(e)}",
                extra={"tenant_id": self.tenant_id, "collection_id": collection_id}
            )
            return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _get_federated_collections(self) -> List[Dict[str, Any]]:
        """
        Obtiene las colecciones para federación automática.
        
        Returns:
            Lista de colecciones para federación
        """
        try:
            # Obtener colecciones para federación automática desde Ingestion Service
            response = await call_service(
                service_name="ingestion-service",
                endpoint="/internal/collections/federated",
                method="GET",
                params={"tenant_id": self.tenant_id},
                headers={"X-Tenant-ID": self.tenant_id},
            )
            
            if response["success"] and "collections" in response["data"]:
                return response["data"]["collections"]
            return []
        except Exception as e:
            logger.error(
                f"Error al obtener colecciones para federación: {str(e)}",
                extra={"tenant_id": self.tenant_id}
            )
            return []
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _get_default_collection(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene la colección por defecto para el tenant.
        
        Returns:
            Colección por defecto o None si no existe
        """
        try:
            # Obtener colección por defecto desde Ingestion Service
            response = await call_service(
                service_name="ingestion-service",
                endpoint="/internal/collection/default",
                method="GET",
                params={"tenant_id": self.tenant_id},
                headers={"X-Tenant-ID": self.tenant_id},
            )
            
            if response["success"] and "collection" in response["data"]:
                return response["data"]["collection"]
            return None
        except Exception as e:
            logger.error(
                f"Error al obtener colección por defecto: {str(e)}",
                extra={"tenant_id": self.tenant_id}
            )
            return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def track_usage(self, 
                        query_tokens: int = 0,
                        result_tokens: int = 0, 
                        model: Optional[str] = None):
        """
        Registra el uso de tokens para las colecciones seleccionadas.
        
        Args:
            query_tokens: Tokens utilizados en la consulta
            result_tokens: Tokens en los resultados
            model: Modelo utilizado
        """
        # Si no hay colecciones seleccionadas, registrar a nivel de tenant
        if not self._selected_collections:
            if query_tokens > 0:
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=query_tokens,
                    model=model,
                    token_type="embedding",
                    operation="query",
                    metadata=self._metadata
                )
            
            if result_tokens > 0:
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=result_tokens,
                    model=model,
                    token_type="llm",
                    operation="query_result",
                    metadata=self._metadata
                )
            return
        
        # Registrar tokens para cada colección seleccionada
        collection_count = len(self._selected_collections)
        for i, collection in enumerate(self._selected_collections):
            collection_id = collection["id"]
            
            # Distribuir tokens equitativamente entre colecciones
            collection_query_tokens = query_tokens // collection_count
            collection_result_tokens = result_tokens // collection_count
            
            # Ajustar para la última colección (residuo)
            if i == collection_count - 1:
                collection_query_tokens += query_tokens % collection_count
                collection_result_tokens += result_tokens % collection_count
            
            # Registrar tokens de consulta
            if collection_query_tokens > 0:
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=collection_query_tokens,
                    model=model,
                    collection_id=collection_id,
                    token_type="embedding",
                    operation="query",
                    metadata={**self._metadata, "collection_index": i}
                )
            
            # Registrar tokens de resultado
            if collection_result_tokens > 0:
                await track_token_usage(
                    tenant_id=self.tenant_id,
                    tokens=collection_result_tokens,
                    model=model,
                    collection_id=collection_id,
                    token_type="llm",
                    operation="query_result",
                    metadata={**self._metadata, "collection_index": i}
                )
```

## 4.2 Integración con RAGQueryTool

### 4.2.1 Implementación de RAGQueryTool Actualizado

```python
from langchain.tools import BaseTool
from typing import Dict, List, Optional, Any, Type
from common.context import Context, with_context
from common.errors.handlers import handle_errors

class RAGQueryTool(BaseTool):
    """
    Herramienta de LangChain para realizar consultas RAG utilizando el Query Service
    con soporte para selección explícita de colecciones.
    """
    
    name = "rag_query"
    description = "Busca información en las colecciones de documentos relevantes para responder a preguntas."
    
    def __init__(
        self,
        tenant_id: str,
        collection_strategy: Optional[CollectionStrategy] = None,
        embedding_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        ctx: Optional[Context] = None
    ):
        """
        Inicializa la herramienta RAG.
        
        Args:
            tenant_id: ID del tenant
            collection_strategy: Estrategia de colecciones pre-configurada
            embedding_model: Modelo de embedding a utilizar
            llm_model: Modelo LLM a utilizar
            ctx: Contexto con información adicional
        """
        super().__init__()
        self.tenant_id = tenant_id
        self.collection_strategy = collection_strategy
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.ctx = ctx
    
    @handle_errors(error_type="tool", log_traceback=True)
    async def _arun(self, query: str) -> str:
        """
        Ejecuta la consulta RAG de forma asíncrona.
        
        Args:
            query: Consulta a ejecutar
            
        Returns:
            Resultado de la consulta RAG
        """
        # Si no hay estrategia de colección configurada, crear una por defecto
        if not self.collection_strategy:
            self.collection_strategy = CollectionStrategy(self.tenant_id, self.ctx)
            await self.collection_strategy.configure(use_auto_federation=True)
        
        # Obtener IDs de colecciones de la estrategia
        collection_ids = await self.collection_strategy.get_collection_ids()
        
        # Preparar metadatos para la consulta
        metadata = {
            "tool": "rag_query",
            "collection_count": len(collection_ids)
        }
        
        if self.ctx:
            if agent_id := self.ctx.get_agent_id():
                metadata["agent_id"] = agent_id
            if conversation_id := self.ctx.get_conversation_id():
                metadata["conversation_id"] = conversation_id
        
        # Crear petición para el Query Service
        request_data = {
            "query": query,
            "collection_ids": collection_ids,
            "tenant_id": self.tenant_id,
            "metadata": metadata
        }
        
        # Añadir modelos si están especificados
        if self.embedding_model:
            request_data["embedding_model"] = self.embedding_model
        
        if self.llm_model:
            request_data["llm_model"] = self.llm_model
        
        # Llamar al Query Service
        try:
            response = await call_service(
                service_name="query-service",
                endpoint="/internal/rag",
                method="POST",
                json=request_data,
                headers={"X-Tenant-ID": self.tenant_id}
            )
            
            # Registrar uso de tokens
            if "token_usage" in response.get("metadata", {}):
                token_usage = response["metadata"]["token_usage"]
                await self.collection_strategy.track_usage(
                    query_tokens=token_usage.get("query_tokens", 0),
                    result_tokens=token_usage.get("result_tokens", 0),
                    model=self.llm_model or token_usage.get("model")
                )
            
            # Devolver respuesta RAG
            if response["success"]:
                return response["data"]["answer"]
            else:
                error_message = response.get("message", "Error al realizar consulta RAG")
                logger.error(f"Error en RAG query: {error_message}")
                return f"Lo siento, no pude encontrar información relevante. Error: {error_message}"
                
        except Exception as e:
            logger.error(f"Error al llamar al Query Service: {str(e)}")
            return "Lo siento, ocurrió un error al intentar buscar información relevante."
```

## 4.3 Integración con el Agent Service Principal

### 4.3.1 Actualización del método create_tools

```python
@handle_errors(error_type="service", log_traceback=True)
async def create_tools(self,
                      tenant_id: str,
                      collection_id: Optional[str] = None,
                      collection_metadata: Optional[Dict[str, Any]] = None,
                      use_auto_federation: bool = False,
                      embedding_model: Optional[str] = None,
                      llm_model: Optional[str] = None,
                      ctx: Context = None) -> List[BaseTool]:
    """
    Crea las herramientas necesarias para el agente, incluyendo RAG con estrategia de colecciones.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de colección explícita
        collection_metadata: Metadatos adicionales de colección
        use_auto_federation: Si se debe usar federación automática
        embedding_model: Modelo de embedding a utilizar
        llm_model: Modelo LLM a utilizar
        ctx: Contexto con información adicional
        
    Returns:
        Lista de herramientas de LangChain para el agente
    """
    # Crear estrategia de colecciones
    collection_strategy = CollectionStrategy(tenant_id, ctx)
    await collection_strategy.configure(
        collection_id=collection_id,
        collection_metadata=collection_metadata,
        use_auto_federation=use_auto_federation
    )
    
    # Crear herramienta RAG con la estrategia de colecciones
    rag_tool = RAGQueryTool(
        tenant_id=tenant_id,
        collection_strategy=collection_strategy,
        embedding_model=embedding_model,
        llm_model=llm_model,
        ctx=ctx
    )
    
    # Agregar otras herramientas del sistema
    tools = [rag_tool]
    
    # Agregar herramientas adicionales según configuración
    # (aquí se pueden añadir otras herramientas configuradas en la base de datos)
    
    return tools
```

### 4.3.2 Actualización del método execute_agent

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
                       ctx: Context = None) -> AgentResponse:
    """
    Ejecuta un agente con estrategia de colección configurada.
    
    Args:
        input_text: Texto de entrada para el agente
        collection_id: ID de colección explícita
        collection_metadata: Metadatos adicionales de colección
        tenant_tier: Tier del tenant (opcional)
        embedding_model: Modelo de embedding a utilizar
        llm_model: Modelo LLM a utilizar
        use_auto_federation: Si se debe usar federación automática
        use_streaming: Si se debe usar streaming para la respuesta
        ctx: Contexto con información adicional
        
    Returns:
        Respuesta del agente
    """
    if not ctx:
        raise ValueError("Contexto requerido para execute_agent")
    
    tenant_id = ctx.get_tenant_id()
    agent_id = ctx.get_agent_id()
    
    # Verificar si los modelos están permitidos para el tier
    if tenant_tier:
        if embedding_model and embedding_model not in get_available_embedding_models(tenant_tier):
            embedding_model = None  # Usar modelo por defecto
            
        if llm_model and llm_model not in get_available_llm_models(tenant_tier):
            llm_model = None  # Usar modelo por defecto
    
    # Crear herramientas con estrategia de colección
    tools = await self.create_tools(
        tenant_id=tenant_id,
        collection_id=collection_id,
        collection_metadata=collection_metadata,
        use_auto_federation=use_auto_federation,
        embedding_model=embedding_model,
        llm_model=llm_model,
        ctx=ctx
    )
    
    # Recuperar configuración del agente desde memoria o DB
    agent_config = await self.get_agent_config(tenant_id, agent_id, ctx)
    
    # Crear agente con herramientas
    agent = await self.create_agent(
        tenant_id=tenant_id,
        agent_config=agent_config,
        tools=tools,
        llm_model=llm_model,
        ctx=ctx
    )
    
    # Ejecutar agente y procesar respuesta
    start_time = time.time()
    
    try:
        if use_streaming:
            # Implementación de streaming (si es requerida)
            pass
        else:
            result = await agent.arun(input_text)
    except Exception as e:
        logger.error(f"Error executing agent: {str(e)}")
        raise AgentExecutionError(f"Error al ejecutar el agente: {str(e)}")
    
    execution_time = time.time() - start_time
    
    # Construir respuesta
    response = AgentResponse(
        answer=result,
        metadata={
            "execution_time": execution_time,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "models": {
                "embedding": embedding_model,
                "llm": llm_model
            }
        }
    )
    
    return response
```

## 4.4 Actualización de Endpoints para Frontend

### 4.4.1 ExecuteAgentRequest Modificado

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any

class ExecuteAgentRequest(BaseModel):
    """
    Modelo de petición para ejecutar un agente desde el frontend.
    Soporta selección explícita de colección y federación.
    """
    input: str = Field(..., description="Texto de entrada para el agente")
    collection_id: Optional[str] = Field(None, description="ID de colección explícita")
    use_auto_federation: bool = Field(False, description="Si se debe usar federación automática")
    embedding_model: Optional[str] = Field(None, description="Modelo de embedding a utilizar")
    llm_model: Optional[str] = Field(None, description="Modelo LLM a utilizar")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    use_streaming: bool = Field(False, description="Si se debe usar streaming para la respuesta")
```

### 4.4.2 Endpoint de Ejecución de Agente

```python
@router.post("/agent/{agent_id}/execute", response_model=None)
@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="api", log_traceback=True)
async def execute_agent_endpoint(
    agent_id: str,
    request: ExecuteAgentRequest,
    ctx: Context = None
):
    """
    Endpoint para ejecutar un agente con parámetros desde el frontend.
    
    Args:
        agent_id: ID del agente a ejecutar
        request: Parámetros de la petición
        ctx: Contexto con información adicional
    """
    # Verificar contexto
    if not ctx:
        raise ValueError("Contexto requerido para execute_agent_endpoint")
    
    tenant_id = ctx.get_tenant_id()
    
    # Obtener tier del tenant para validar modelos
    tenant_tier = await get_tenant_tier(tenant_id)
    
    # Ejecutar agente con parámetros de la petición
    response = await agent_service.execute_agent(
        input_text=request.input,
        collection_id=request.collection_id,
        collection_metadata=request.metadata,
        tenant_tier=tenant_tier,
        embedding_model=request.embedding_model,
        llm_model=request.llm_model,
        use_auto_federation=request.use_auto_federation,
        use_streaming=request.use_streaming,
        ctx=ctx
    )
    
    # Devolver respuesta
    return {
        "success": True,
        "message": "Agent executed successfully",
        "data": {
            "answer": response.answer,
            "metadata": response.metadata
        }
    }
```

## Tareas Pendientes

- [ ] Implementar la clase CollectionStrategy completa
- [ ] Actualizar RAGQueryTool para usar la estrategia de colecciones
- [ ] Modificar create_tools y execute_agent para integrar la estrategia
- [ ] Implementar el modelo ExecuteAgentRequest actualizado
- [ ] Actualizar el endpoint de ejecución del agente para recibir parámetros del frontend
- [ ] Pruebas de integración con selección explícita y federación automática
