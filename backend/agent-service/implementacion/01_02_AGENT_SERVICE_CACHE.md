# Fase 1.2: Implementación de Caché en Agent Service

## Visión General

Esta fase complementa la implementación del núcleo del Agent Service, profundizando específicamente en la estrategia de caché optimizada para flujos de conversación, configuraciones de agentes y memoria persistente. El objetivo es mejorar el rendimiento, reducir la carga en la base de datos y garantizar una experiencia fluida incluso con alta demanda.

## 1.2.1 Estrategia de Caché para Agent Service

### Escenarios para Uso del Patrón Cache-Aside

El patrón Cache-Aside debe aplicarse selectivamente según el contexto de uso:

```python
# ✅ CORRECTO: Usar get_with_cache_aside para obtener configuración existente
agent_config, metrics = await get_with_cache_aside(
    data_type="agent_config",
    resource_id=agent_id,
    tenant_id=tenant_id,
    fetch_from_db_func=self._fetch_agent_config_from_db,
    generate_func=None  # No hay generación para config de agentes
)

# ❌ INCORRECTO: Usar get_with_cache_aside para configuración recién proporcionada
# La configuración explícita del frontend no debe obtenerse mediante Cache-Aside
```

### Jerarquía de Claves y Contexto

El sistema de caché para agentes sigue una estructura jerárquica clara:

```
tenant_id
  └── agent_id
       ├── agent_config                  # Configuración del agente
       ├── agent_tools                   # Herramientas disponibles
       └── conversation_id
             ├── conversation_memory     # Estado de la memoria 
             ├── messages                # Lista de mensajes (Redis List)
             └── message_id
                   └── message_data      # Datos de mensajes individuales
```

### TTLs Recomendados por Tipo de Datos

| Tipo de Dato           | TTL            | Descripción                                 |
|------------------------|----------------|---------------------------------------------|
| agent_config           | ttl_standard   | Configuración del agente (1 hora)           |
| conversation_memory    | ttl_extended   | Memoria completa de conversación (24 horas) |
| conversation_message   | ttl_extended   | Mensajes individuales (24 horas)            |
| agent_tools            | ttl_standard   | Herramientas disponibles (1 hora)           |
| agent_execution_state  | ttl_short      | Estado de ejecución actual (5 min)          |
| collection_metadata    | ttl_standard   | Metadatos de colección (1 hora)             |

## 1.2.2 Implementación de Memoria de Conversación con Caché Optimizada

### Clase ConversationMemoryManager

```python
class ConversationMemoryManager:
    """Gestiona la memoria de conversación con caché optimizada."""
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Dict[str, Any]:
        """Obtiene la memoria de una conversación usando el patrón Cache-Aside."""
        # SÍ es apropiado usar Cache-Aside para memoria persistente
        memory, metrics = await get_with_cache_aside(
            data_type="conversation_memory",
            resource_id=conversation_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_memory_from_db,
            generate_func=self._create_empty_memory,
            ttl=CacheManager.ttl_extended  # 24 horas para memoria
        )
        
        # Registrar métricas de caché
        await track_agent_cache_metrics(
            tenant_id=tenant_id,
            agent_id=ctx.get_agent_id() if ctx else None,
            data_type="conversation_memory",
            cache_hit=metrics.get("source") == "cache",
            operation="get_memory",
            latency_ms=metrics.get("latency_ms", 0)
        )
        
        return memory
        
    @handle_errors(error_type="service", log_traceback=True)
    async def add_message(self, 
                        tenant_id: str, 
                        conversation_id: str, 
                        role: str, 
                        content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> str:
        """Añade un mensaje a la conversación con actualización de caché."""
        # Generar ID de mensaje
        message_id = str(uuid.uuid4())
        
        # Crear datos del mensaje
        message_data = {
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # CORRECTO: Almacenar mensaje individual en caché (no es apropiado Cache-Aside aquí)
        await CacheManager.set(
            data_type="conversation_message",
            resource_id=message_id,
            value=message_data,
            tenant_id=tenant_id,
            collection_id=conversation_id,  # Usar collection_id para agrupar por conversación
            ttl=CacheManager.ttl_extended   # 24 horas para mensajes
        )
        
        # IMPORTANTE: Usar métodos de instancia para operaciones de lista
        await CacheManager.get_instance().rpush(
            list_name=f"{tenant_id}:{conversation_id}:messages",
            value=message_data,
            tenant_id=tenant_id  # Pasar tenant_id para segmentación
        )
        
        # Actualizar en base de datos (async)
        await self._store_message_in_db(tenant_id, conversation_id, message_data)
        
        return message_id
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_messages(self, 
                         tenant_id: str, 
                         conversation_id: str,
                         limit: int = 50,
                         skip: int = 0) -> List[Dict[str, Any]]:
        """Recupera mensajes de la conversación desde caché."""
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
                return messages
        except Exception as e:
            logger.warning(f"Error obteniendo mensajes de caché: {str(e)}")
        
        # Si no está en caché, recuperar de la base de datos
        messages = await self._fetch_messages_from_db(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            limit=limit,
            skip=skip
        )
        
        # Reconstruir caché si se obtuvieron mensajes
        if messages:
            # ❌ INCORRECTO: No usar delete así
            # await CacheManager.delete(f"{tenant_id}:{conversation_id}:messages")
            
            # ✅ CORRECTO: Usar método de instancia para operaciones de listas
            await CacheManager.get_instance().delete(
                key=f"{tenant_id}:{conversation_id}:messages",
                tenant_id=tenant_id  # Importante pasar tenant_id
            )
            
            # Añadir mensajes a la lista
            for message in messages:
                await CacheManager.get_instance().rpush(
                    list_name=f"{tenant_id}:{conversation_id}:messages",
                    value=message,
                    tenant_id=tenant_id
                )
        
        return messages
```

## 1.2.3 Gestión del Estado de Ejecución

La gestión del estado de ejecución del agente requiere un enfoque diferente al de la memoria de conversación:

```python
class AgentExecutionStateManager:
    """Gestiona el estado de ejecución de agentes con soporte para caching."""
    
    @handle_errors(error_type="service", log_traceback=True)
    async def save_execution_state(self,
                                 tenant_id: str,
                                 agent_id: str,
                                 execution_id: str,
                                 state: Dict[str, Any]) -> bool:
        """Guarda el estado de ejecución en caché y opcionalmente en BD."""
        # CORRECTO: Usar set directamente, no Cache-Aside (es un estado temporal)
        await CacheManager.set(
            data_type="agent_execution_state",
            resource_id=execution_id,
            value=state,
            tenant_id=tenant_id,
            agent_id=agent_id,  # Incluir agent_id para mejorar jerarquía de caché
            ttl=CacheManager.ttl_short  # TTL corto para estados (5 min)
        )
        
        # Si el estado indica completado o error, persistir en BD
        if state.get("status") in ["completed", "failed", "error"]:
            await self._persist_execution_state(
                tenant_id=tenant_id,
                agent_id=agent_id,
                execution_id=execution_id,
                state=state
            )
        
        return True
        
    @handle_errors(error_type="service", log_traceback=True)
    async def get_execution_state(self,
                                tenant_id: str,
                                execution_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene el estado de ejecución actual de un agente."""
        # CORRECTO: Para estados temporales, usar get directo no Cache-Aside
        return await CacheManager.get(
            data_type="agent_execution_state",
            resource_id=execution_id,
            tenant_id=tenant_id
        )
```

## 1.2.4 Técnicas de Invalidación Eficiente

La invalidación selectiva es crucial para mantener la coherencia del caché:

```python
@handle_errors(error_type="service", log_traceback=True)
async def invalidate_agent_resources(
    tenant_id: str,
    agent_id: str,
    invalidate_conversations: bool = False
) -> Dict[str, int]:
    """
    Invalida recursos relacionados con un agente en múltiples niveles.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        invalidate_conversations: Si se deben invalidar también conversaciones
        
    Returns:
        Dict con conteo de recursos invalidados
    """
    invalidation_count = {
        "agent_config": 0,
        "agent_tools": 0,
        "conversations": 0,
        "messages": 0
    }
    
    # 1. Invalidar configuración del agente
    await CacheManager.delete(
        data_type="agent_config",
        resource_id=agent_id,
        tenant_id=tenant_id
    )
    invalidation_count["agent_config"] = 1
    
    # 2. Invalidar herramientas del agente
    await CacheManager.delete(
        data_type="agent_tools",
        resource_id=agent_id,
        tenant_id=tenant_id
    )
    invalidation_count["agent_tools"] = 1
    
    # 3. Si se solicita, invalidar conversaciones relacionadas
    if invalidate_conversations:
        # Obtener IDs de conversaciones relacionadas
        conversation_ids = await get_agent_conversation_ids(tenant_id, agent_id)
        
        for conversation_id in conversation_ids:
            # Invalidar memoria de conversación
            await CacheManager.delete(
                data_type="conversation_memory",
                resource_id=conversation_id,
                tenant_id=tenant_id
            )
            invalidation_count["conversations"] += 1
            
            # Invalidar lista de mensajes (usando método de instancia)
            deleted = await CacheManager.get_instance().delete(
                key=f"{tenant_id}:{conversation_id}:messages",
                tenant_id=tenant_id
            )
            if deleted:
                invalidation_count["messages"] += 1
    
    return invalidation_count
```

## 1.2.5 Métricas de Caché para Optimización Continua

Para monitorear y optimizar el rendimiento de la caché:

```python
async def track_agent_cache_metrics(
    tenant_id: str,
    agent_id: Optional[str],
    data_type: str,
    cache_hit: bool,
    operation: str,
    latency_ms: float
):
    """Registra métricas de rendimiento de caché para el Agent Service."""
    metric_name = "cache_hit" if cache_hit else "cache_miss"
    
    # Usar el sistema centralizado de métricas
    await track_performance_metric(
        metric_type=f"agent_service_{metric_name}",
        value=1,  # Incrementar contador
        tenant_id=tenant_id,
        metadata={
            "agent_id": agent_id,
            "data_type": data_type,
            "operation": operation,
            "latency_ms": latency_ms
        }
    )
```

## 1.2.6 Actualización de `_get_conversation_memory` en LangChainAgentService

El método original debe refactorizarse para usar apropiadamente Cache-Aside:

```python
async def _get_conversation_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Any:
    """Obtiene la memoria de conversación para un agente.
    
    Args:
        tenant_id: ID del tenant
        conversation_id: ID de la conversación
        ctx: Contexto opcional
        
    Returns:
        Objeto de memoria de conversación
    """
    # CORRECTO: Usar Cache-Aside para memoria persistente
    memory_dict, metrics = await get_with_cache_aside(
        data_type="conversation_memory",
        resource_id=conversation_id,
        tenant_id=tenant_id,
        fetch_from_db_func=self._fetch_conversation_memory_from_db,
        generate_func=self._create_empty_conversation_memory,
        ttl=CacheManager.ttl_extended  # 24 horas para persistencia adecuada
    )
    
    # Convertir diccionario a objeto de memoria si es necesario
    if isinstance(memory_dict, dict):
        return self._dict_to_memory_object(memory_dict)
    
    return memory_dict
```

## 1.2.7 Integración con Sistema de Colas (Fase 7)

Esta implementación de caché está diseñada para integrarse con el sistema de colas de la Fase 7:

```python
# En trabajo encolado, usar el estado en caché para compartir progreso
async def process_agent_job(job_id: str, params: Dict[str, Any], tenant_id: str):
    """Procesa un trabajo de ejecución de agente desde la cola."""
    # Actualizar estado inicial
    await CacheManager.set(
        data_type="agent_execution_state",
        resource_id=job_id,
        value={"status": "processing", "progress": 0},
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_short
    )
    
    try:
        # Procesar trabajo...
        
        # Actualizar progreso periódicamente
        await CacheManager.set(
            data_type="agent_execution_state",
            resource_id=job_id,
            value={"status": "processing", "progress": 50},
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_short
        )
        
        # Estado final
        await CacheManager.set(
            data_type="agent_execution_state",
            resource_id=job_id,
            value={
                "status": "completed",
                "progress": 100,
                "result": result_data,
                "completed_at": datetime.now().isoformat()
            },
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard  # TTL más largo para resultados completados
        )
        
    except Exception as e:
        # Estado de error
        await CacheManager.set(
            data_type="agent_execution_state",
            resource_id=job_id,
            value={"status": "error", "error": str(e)},
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
```

## 1.2.8 Implementación para Caché de Herramientas de Agente

La carga de herramientas puede optimizarse mediante caché:

```python
async def _load_agent_tools(self, tenant_id: str, agent_id: str, tool_names: List[str], ctx: Context = None):
    """Carga herramientas para un agente con soporte de caché."""
    # Clave de caché específica para esta combinación de herramientas
    tool_config_key = hashlib.md5(f"{agent_id}:{','.join(sorted(tool_names))}".encode()).hexdigest()
    
    # Intentar recuperar configuración de herramientas de caché
    # CORRECTO: Usar Cache-Aside para configuraciones de herramientas
    tools_config, metrics = await get_with_cache_aside(
        data_type="agent_tools_config",
        resource_id=tool_config_key,
        tenant_id=tenant_id,
        fetch_from_db_func=lambda: self._fetch_tools_config_from_db(tenant_id, agent_id, tool_names),
        generate_func=None,  # No generamos config, solo la recuperamos
        ttl=CacheManager.ttl_standard
    )
    
    # Inicializar herramientas con la configuración
    tools = []
    for tool_name, config in tools_config.items():
        if tool_name in self.tool_registry:
            tool_class = self.tool_registry[tool_name]
            tools.append(tool_class(config=config, ctx=ctx))
    
    return tools
```

## 1.2.9 Buenas Prácticas y Errores Comunes a Evitar

### Errores Comunes

1. ❌ **No usar `rpush` como método estático de CacheManager**:
   ```python
   # INCORRECTO
   await CacheManager.rpush(list_name, value, tenant_id)
   
   # CORRECTO 
   await CacheManager.get_instance().rpush(list_name, value, tenant_id)
   ```

2. ❌ **No mezclar niveles incorrectos de la jerarquía de caché**:
   ```python
   # INCORRECTO (mezclando tenant_id y agent_id en resource_id)
   await CacheManager.set("config", f"{tenant_id}_{agent_id}", value)
   
   # CORRECTO (usando parámetros separados)
   await CacheManager.set("agent_config", agent_id, value, tenant_id=tenant_id)
   ```

3. ❌ **No usar Cache-Aside para datos que vienen del frontend**:
   ```python
   # INCORRECTO
   config, _ = await get_with_cache_aside("config", id, tenant_id, 
                                       lambda: frontend_provided_config)
   
   # CORRECTO
   await CacheManager.set("config", id, frontend_provided_config, tenant_id)
   ```

### Buenas Prácticas

1. ✅ **Tener en cuenta la naturaleza de los datos para TTL**:
   - Usar `ttl_extended` (24h) para memoria, embeddings y elementos costosos
   - Usar `ttl_standard` (1h) para configuraciones y metadatos
   - Usar `ttl_short` (5min) para estados temporales y resultados de consultas

2. ✅ **Serializar correctamente objetos complejos**:
   ```python
   # Usar helpers de serialización para tipos complejos
   from common.cache.helpers import serialize_for_cache, deserialize_from_cache
   
   serialized_memory = serialize_for_cache(memory_object)
   await CacheManager.set("memory", conversation_id, serialized_memory, tenant_id)
   
   cached_memory = await CacheManager.get("memory", conversation_id, tenant_id)
   memory_object = deserialize_from_cache(cached_memory)
   ```

3. ✅ **Manejar adecuadamente errores de caché**:
   ```python
   try:
       result = await CacheManager.get("key", "id", tenant_id)
   except Exception as e:
       logger.warning(f"Error de caché: {str(e)}")
       # Implementar fallback a base de datos
   ```

## Conclusión

La implementación de caché del Agent Service debe seguir un enfoque estratégico, utilizando el patrón Cache-Aside donde tenga sentido (para datos persistentes que deben recuperarse de BD) y operaciones directas de caché para datos temporales o provenientes del frontend.

Este enfoque:
- Reduce la carga en la base de datos
- Mejora los tiempos de respuesta 
- Optimiza el uso de recursos
- Garantiza coherencia en entornos multi-tenant

Las técnicas descritas aquí se integrarán con los sistemas de colas y WebSockets (Fase 7) para proporcionar una experiencia de usuario fluida y altamente responsiva.

## Tareas Pendientes

- [ ] Implementar `ConversationMemoryManager` completo
- [ ] Crear métricas de monitoreo para caché de agentes
- [ ] Optimizar TTLs basados en patrones de uso reales
- [ ] Implementar pruebas de carga para validar rendimiento
- [ ] Integrar con sistema de observabilidad para monitoreo
