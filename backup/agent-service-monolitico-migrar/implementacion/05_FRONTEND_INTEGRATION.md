# Fase 5: Integración con Frontend

## Visión General

Esta fase se centra en la implementación de los puntos de integración entre el Agent Service y el frontend, incluyendo modelos de datos optimizados, endpoints especializados y flujos de autenticación para una experiencia de usuario fluida y segura.

## 5.1 Modelos de Datos para Integración

### 5.1.1 Modelos de Solicitud para Frontend

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum

class AgentExecutionMode(str, Enum):
    """Modos de ejecución para agentes"""
    STANDARD = "standard"  # Ejecución normal con respuesta completa
    STREAMING = "streaming"  # Ejecución con streaming de respuesta
    ASYNC = "async"  # Ejecución asíncrona usando el sistema de colas (Fase 7)

class ExecuteAgentRequest(BaseModel):
    """
    Modelo de solicitud para ejecutar un agente desde el frontend.
    Permite configuración específica para cada ejecución.
    """
    input: str = Field(..., description="Texto de entrada para el agente")
    collection_id: Optional[str] = Field(None, description="ID de colección específica")
    use_auto_federation: bool = Field(False, description="Si se debe usar federación automática")
    embedding_model: Optional[str] = Field(None, description="Modelo de embedding a utilizar")
    llm_model: Optional[str] = Field(None, description="Modelo LLM a utilizar")
    execution_mode: AgentExecutionMode = Field(
        default=AgentExecutionMode.STANDARD, 
        description="Modo de ejecución (standard o streaming)"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")

class ConfigureAgentRequest(BaseModel):
    """
    Modelo para configurar un agente desde el frontend.
    Incluye configuración completa y personalizable.
    """
    name: str = Field(..., description="Nombre del agente")
    description: Optional[str] = Field(None, description="Descripción del agente")
    system_prompt: str = Field(..., description="Prompt de sistema para el agente")
    tools_config: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Configuración de herramientas"
    )
    default_collection_id: Optional[str] = Field(
        None, 
        description="ID de colección predeterminada"
    )
    default_llm_model: Optional[str] = Field(None, description="Modelo LLM predeterminado")
    default_embedding_model: Optional[str] = Field(
        None, 
        description="Modelo de embedding predeterminado"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
```

### 5.1.2 Modelos de Respuesta para Frontend

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

class AgentExecutionResponse(BaseModel):
    """
    Modelo de respuesta para ejecución de agente, optimizado para frontend.
    Soporta tanto respuestas síncronas como asíncronas a través del sistema de colas (Fase 7).
    """
    # Campos comunes para todas las respuestas
    is_async: bool = Field(False, description="Indica si la ejecución es asíncrona")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp de inicio de ejecución")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
    
    # Campos para respuestas síncronas
    answer: Optional[str] = Field(None, description="Respuesta del agente (sólo para ejecución síncrona)")
    execution_time: Optional[float] = Field(None, description="Tiempo de ejecución en segundos")
    token_usage: Dict[str, int] = Field(
        default_factory=dict, 
        description="Uso de tokens (prompt, completion, total)"
    )
    sources: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Fuentes utilizadas en la respuesta"
    )
    models_used: Dict[str, str] = Field(
        default_factory=dict, 
        description="Modelos utilizados (llm, embedding)"
    )
    collection_ids: List[str] = Field(
        default_factory=list, 
        description="IDs de colecciones consultadas"
    )
    
    # Campos para respuestas asíncronas (Sistema de colas - Fase 7)
    job_id: Optional[str] = Field(None, description="ID del trabajo en el sistema de colas (para ejecución asíncrona)")
    job_status: Optional[str] = Field(None, description="Estado del trabajo asíncrono: queued, processing, completed, failed")
    websocket_url: Optional[str] = Field(None, description="URL de WebSocket para seguimiento en tiempo real del progreso")

class AgentConfigurationResponse(BaseModel):
    """
    Modelo de respuesta para configuración de agente.
    """
    agent_id: str = Field(..., description="ID del agente")
    name: str = Field(..., description="Nombre del agente")
    description: Optional[str] = Field(None, description="Descripción del agente")
    creation_date: datetime = Field(..., description="Fecha de creación")
    last_modified: datetime = Field(..., description="Fecha de última modificación")
    tools_enabled: List[str] = Field(
        default_factory=list, 
        description="Herramientas habilitadas"
    )
    default_collection_id: Optional[str] = Field(
        None, 
        description="ID de colección predeterminada"
    )
    default_models: Dict[str, str] = Field(
        default_factory=dict, 
        description="Modelos predeterminados"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales")
```

## 5.2 Endpoints para Frontend

### 5.2.1 Endpoint Principal para Ejecución de Agentes

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
    Endpoint para ejecutar un agente con configuración desde el frontend.
    
    Args:
        agent_id: ID del agente a ejecutar
        request: Parámetros de configuración
        ctx: Contexto con información adicional
    
    Returns:
        Respuesta de ejecución del agente optimizada para frontend
    """
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para execute_agent_endpoint")
    
    tenant_id = ctx.get_tenant_id()
    conversation_id = ctx.get_conversation_id()
    
    # Obtener tier del tenant para validar modelos
    tenant_tier = await get_tenant_tier(tenant_id)
    
    # Determinar si usar streaming
    use_streaming = request.execution_mode == AgentExecutionMode.STREAMING
    
    # Registrar inicio de ejecución para métricas
    execution_id = str(uuid.uuid4())
    start_time = time.time()
    
    try:
        # Determinar si usar ejecución asíncrona con el sistema de colas (Fase 7)
        use_async = request.execution_mode == AgentExecutionMode.ASYNC
        
        # Si es asíncrono, no se puede usar streaming
        if use_async and use_streaming:
            raise ValueError("No se puede usar streaming y ejecución asíncrona simultáneamente")
        
        # Ejecutar agente con parámetros del frontend
        # Nota: Los metadatos serán estandarizados según la Fase 8 para compatibilidad con LlamaIndex
        agent_response = await agent_service.execute_agent(
            input_text=request.input,
            collection_id=request.collection_id,
            collection_metadata=request.metadata,  # Estos metadatos se estandarizarán internamente,
            tenant_tier=tenant_tier,
            embedding_model=request.embedding_model,
            llm_model=request.llm_model,
            use_auto_federation=request.use_auto_federation,
            use_streaming=use_streaming,
            use_async=use_async,  # Pasar flag para usar sistema de colas (Fase 7)
            ctx=ctx
        )
        
        # Procesar respuesta según tipo (síncrona o asíncrona)
        if hasattr(agent_response, 'is_async') and agent_response.is_async:
            # Respuesta asíncrona del sistema de colas (Fase 7)
            logger.info(
                f"Ejecución asíncrona registrada con job_id={agent_response.async_job_id}",
                extra={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "job_id": agent_response.async_job_id
                }
            )
            
            # Construir URL de WebSocket para seguimiento en tiempo real
            websocket_url = f"/ws/jobs/{agent_response.async_job_id}"
            
            # Registrar inicio de ejecución asíncrona en base de datos
            await store_agent_execution(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                execution_id=execution_id,
                input_text=request.input,
                output_text=None,  # Sin respuesta aún
                execution_time=None,
                token_usage={},
                models={},
                metadata={
                    "async_job_id": agent_response.async_job_id,
                    "job_status": "queued",
                    "collection_ids": [request.collection_id] if request.collection_id else [],
                    "auto_federation": request.use_auto_federation
                }
            )
            
            # Devolver respuesta asíncrona para el frontend
            return AgentExecutionResponse(
                is_async=True,
                job_id=agent_response.async_job_id,
                job_status="queued",
                websocket_url=websocket_url,
                collection_ids=[request.collection_id] if request.collection_id else [],
                models_used={
                    "llm": request.llm_model or "default",
                    "embedding": request.embedding_model or "default"
                }
            )
        else:
            # Respuesta síncrona estándar
            execution_time = time.time() - start_time
            
            # Registrar ejecución en base de datos
            await store_agent_execution(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                execution_id=execution_id,
                input_text=request.input,
                output_text=agent_response.answer,
                execution_time=execution_time,
                token_usage=agent_response.token_usage,
                models=agent_response.models_used,
                metadata={
                    "sources": agent_response.sources,
                    "collection_ids": agent_response.collection_ids,
                    "auto_federation": request.use_auto_federation
                }
            )
            
            return AgentExecutionResponse(
                is_async=False,
                answer=agent_response.answer,
                execution_time=execution_time,
                token_usage=agent_response.token_usage,
                sources=agent_response.sources,
                models_used=agent_response.models_used,
                collection_ids=agent_response.collection_ids
            )
        
    except Exception as e:
        # Registrar error de ejecución
        logger.error(
            f"Error executing agent {agent_id}: {str(e)}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "execution_id": execution_id
            }
        )
        
        # Registrar ejecución fallida en base de datos
        await store_agent_execution(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            execution_id=execution_id,
            input_text=request.input,
            output_text=None,
            execution_time=time.time() - start_time,
            error=str(e),
            metadata={
                "frontend_metadata": request.metadata,
                "error_type": type(e).__name__
            }
        )
        
        raise
```

### 5.2.2 Endpoint de Streaming para Respuestas en Tiempo Real

```python
@router.post("/agent/{agent_id}/execute/stream", response_model=None)
@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="api", log_traceback=True)
async def stream_agent_execution(
    agent_id: str,
    request: ExecuteAgentRequest,
    ctx: Context = None
):
    """
    Endpoint para ejecutar un agente con streaming de respuesta.
    
    Args:
        agent_id: ID del agente a ejecutar
        request: Parámetros de configuración
        ctx: Contexto con información adicional
    
    Returns:
        Respuesta de streaming para el frontend
    """
    # Forzar modo streaming
    request.execution_mode = AgentExecutionMode.STREAMING
    
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para stream_agent_execution")
    
    tenant_id = ctx.get_tenant_id()
    conversation_id = ctx.get_conversation_id()
    
    # Obtener tier del tenant para validar modelos
    tenant_tier = await get_tenant_tier(tenant_id)
    
    # Registrar inicio de ejecución para métricas
    execution_id = str(uuid.uuid4())
    start_time = time.time()
    
    try:
        # Crear respuesta de streaming
        async def event_generator():
            # Configurar streaming
            stream_queue = asyncio.Queue()
            
            # Iniciar ejecución del agente en background
            asyncio.create_task(
                execute_agent_with_streaming(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    input_text=request.input,
                    collection_id=request.collection_id,
                    tenant_tier=tenant_tier,
                    embedding_model=request.embedding_model,
                    llm_model=request.llm_model,
                    use_auto_federation=request.use_auto_federation,
                    stream_queue=stream_queue,
                    ctx=ctx
                )
            )
            
            # Inicializar variables para recopilar la respuesta completa
            complete_answer = []
            metadata = {}
            
            # Procesar tokens del stream
            while True:
                try:
                    # Esperar próximo evento
                    event = await stream_queue.get()
                    
                    # Verificar si es el evento final
                    if event.get("type") == "end":
                        # Guardar metadata final
                        metadata = event.get("metadata", {})
                        break
                        
                    # Procesar tokens de texto
                    if event.get("type") == "token":
                        token = event.get("token", "")
                        complete_answer.append(token)
                        
                        # Enviar token al frontend
                        yield {
                            "event": "token",
                            "data": json.dumps({"token": token})
                        }
                    
                    # Procesar metadatos intermedios (como fuentes)
                    if event.get("type") == "metadata":
                        # Enviar metadatos al frontend
                        yield {
                            "event": "metadata",
                            "data": json.dumps(event.get("data", {}))
                        }
                        
                except Exception as e:
                    logger.error(f"Error en streaming: {str(e)}")
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }
                    break
            
            # Calcular tiempo de ejecución
            execution_time = time.time() - start_time
            
            # Registrar ejecución completa en base de datos
            await store_agent_execution(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                execution_id=execution_id,
                input_text=request.input,
                output_text="".join(complete_answer),
                execution_time=execution_time,
                metadata={
                    **metadata,
                    "frontend_metadata": request.metadata,
                    "streaming": True
                }
            )
            
            # Enviar evento final con metadatos completos
            yield {
                "event": "end",
                "data": json.dumps({
                    "execution_time": execution_time,
                    "execution_id": execution_id,
                    **metadata
                })
            }
        
        # Retornar respuesta de streaming
        return EventSourceResponse(event_generator())
        
    except Exception as e:
        logger.error(
            f"Error setting up streaming for agent {agent_id}: {str(e)}",
            extra={
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id
            }
        )
        
        # Registrar ejecución fallida
        await store_agent_execution(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            execution_id=execution_id,
            input_text=request.input,
            output_text=None,
            execution_time=time.time() - start_time,
            error=str(e),
            metadata={
                "frontend_metadata": request.metadata,
                "error_type": type(e).__name__,
                "streaming": True
            }
        )
        
        raise
```

## 5.3 Implementación de Recepción de Configuraciones

### 5.3.1 Método para Registrar Configuración desde Frontend

```python
@handle_errors(error_type="service", log_traceback=True)
async def register_agent_from_frontend(
    self,
    tenant_id: str,
    agent_id: str,
    agent_config: Dict[str, Any],
    ctx: Context = None
) -> None:
    """
    Registra un agente con configuración recibida directamente del frontend.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente a configurar
        agent_config: Configuración completa del agente
        ctx: Contexto con información adicional
        
    Raises:
        ValidationError: Si la configuración no cumple los requisitos
        DatabaseError: Si hay problemas al guardar en la base de datos
    """
    # Validar la configuración recibida
    validated_config = await self._validate_agent_config(agent_config, tenant_id)
    
    # Añadir metadatos de registro
    validated_config["metadata"] = validated_config.get("metadata", {})
    validated_config["metadata"]["last_updated"] = datetime.now().isoformat()
    validated_config["metadata"]["last_updated_by"] = "frontend"
    
    if ctx and ctx.get_user_id():
        validated_config["metadata"]["updated_by_user"] = ctx.get_user_id()
    
    # Guardar en memoria caché
    await CacheManager.set(
        data_type="agent_config",
        resource_id=agent_id,
        value=validated_config,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_long
    )
    
    # Guardar en base de datos
    await self._store_agent_config_in_db(
        tenant_id=tenant_id,
        agent_id=agent_id,
        config=validated_config
    )
    
    logger.info(
        f"Agente {agent_id} registrado correctamente desde el frontend",
        extra={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "config_size": len(str(validated_config))
        }
    )
```

### 5.3.2 Endpoint para Gestión de Configuraciones

```python
@router.post("/agent/{agent_id}/configure", response_model=None)
@with_context(tenant=True, agent=True)
@handle_errors(error_type="api", log_traceback=True)
async def configure_agent_endpoint(
    agent_id: str,
    request: ConfigureAgentRequest,
    ctx: Context = None
):
    """
    Endpoint para configurar un agente desde el frontend.
    
    Args:
        agent_id: ID del agente a configurar
        request: Configuración del agente
        ctx: Contexto con información adicional
        
    Returns:
        Respuesta con confirmación de configuración
    """
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para configure_agent_endpoint")
    
    tenant_id = ctx.get_tenant_id()
    
    # Preparar configuración completa del agente
    agent_config = {
        "name": request.name,
        "description": request.description,
        "system_prompt": request.system_prompt,
        "tools_config": request.tools_config,
        "default_collection_id": request.default_collection_id,
        "default_llm_model": request.default_llm_model,
        "default_embedding_model": request.default_embedding_model,
        "metadata": request.metadata or {}
    }
    
    # Registrar configuración
    await agent_service.register_agent_from_frontend(
        tenant_id=tenant_id,
        agent_id=agent_id,
        agent_config=agent_config,
        ctx=ctx
    )
    
    # Obtener configuración actualizada para respuesta
    updated_config = await agent_service.get_agent_config(tenant_id, agent_id, ctx)
    
    # Preparar respuesta para frontend
    response = AgentConfigurationResponse(
        agent_id=agent_id,
        name=updated_config.get("name", ""),
        description=updated_config.get("description"),
        creation_date=datetime.fromisoformat(
            updated_config.get("metadata", {}).get("created_at", datetime.now().isoformat())
        ),
        last_modified=datetime.fromisoformat(
            updated_config.get("metadata", {}).get("last_updated", datetime.now().isoformat())
        ),
        tools_enabled=list(updated_config.get("tools_config", {}).keys()),
        default_collection_id=updated_config.get("default_collection_id"),
        default_models={
            "llm": updated_config.get("default_llm_model", ""),
            "embedding": updated_config.get("default_embedding_model", "")
        },
        metadata=updated_config.get("metadata", {})
    )
    
    return {
        "success": True,
        "message": f"Agente {agent_id} configurado correctamente",
        "data": response.dict()
    }
```

## 5.4 Integración con Frontend UI

### 5.4.1 Componentes de UI Recomendados

Para que el frontend pueda interactuar eficientemente con los endpoints del Agent Service, se recomiendan los siguientes componentes de UI:

1. **Componente de chat**: Para mostrar conversaciones con el agente, con soporte para streaming de respuestas.

2. **Selector de colecciones**: Para permitir a los usuarios seleccionar colecciones específicas o habilitar la federación automática.

3. **Selector de modelos**: Para permitir a los usuarios seleccionar modelos LLM y de embedding según su tier.

4. **Panel de configuración de agentes**: Para crear y modificar configuraciones de agentes.

### 5.4.2 Integración con Sistema de Autenticación

```javascript
// Ejemplo de código frontend para integración con autenticación

async function executeAgent(agentId, input, options = {}) {
  // Obtener token de autenticación
  const authToken = await getAuthToken();
  
  // Preparar petición
  const requestBody = {
    input: input,
    collection_id: options.collectionId || null,
    use_auto_federation: options.useAutoFederation || false,
    embedding_model: options.embeddingModel || null,
    llm_model: options.llmModel || null,
    execution_mode: options.streaming ? "streaming" : "standard",
    metadata: options.metadata || {}
  };
  
  // Determinar endpoint según modo
  const endpoint = options.streaming
    ? `/api/agent/${agentId}/execute/stream`
    : `/api/agent/${agentId}/execute`;
  
  // Ejecutar solicitud
  if (options.streaming) {
    // Configurar EventSource para streaming
    const eventSource = new EventSource(`${endpoint}?data=${encodeURIComponent(JSON.stringify(requestBody))}`);
    
    // Configurar manejadores de eventos
    eventSource.addEventListener("token", (event) => {
      const data = JSON.parse(event.data);
      options.onToken?.(data.token);
    });
    
    eventSource.addEventListener("metadata", (event) => {
      const data = JSON.parse(event.data);
      options.onMetadata?.(data);
    });
    
    eventSource.addEventListener("end", (event) => {
      const data = JSON.parse(event.data);
      options.onComplete?.(data);
      eventSource.close();
    });
    
    eventSource.addEventListener("error", (event) => {
      options.onError?.(event);
      eventSource.close();
    });
    
    return eventSource;
  } else {
    // Solicitud estándar
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${authToken}`
      },
      body: JSON.stringify(requestBody)
    });
    
    return await response.json();
  }
}
```

## Tareas Pendientes

- [ ] Implementar modelos de datos ExecuteAgentRequest y AgentExecutionResponse
- [ ] Desarrollar endpoint `/agent/{agent_id}/execute` para ejecución desde frontend
- [ ] Implementar streaming con EventSourceResponse para respuestas en tiempo real
- [ ] Crear método register_agent_from_frontend para recibir configuraciones
- [ ] Implementar endpoint `/agent/{agent_id}/configure` para gestión de configuraciones
- [ ] Desarrollar componentes de UI recomendados para frontend
- [ ] Integrar con sistema de autenticación existente
