# Fase 1.2: Implementación de Caché en Agent Service

## Índice del documento

1. [Visión General](#visión-general)
2. [Estrategia de Caché para Agent Service](#121-estrategia-de-caché-para-agent-service)
   - [Escenarios para Uso del Patrón Cache-Aside](#escenarios-para-uso-del-patrón-cache-aside)
   - [Jerarquía de Claves y Contexto](#jerarquía-de-claves-y-contexto)
   - [TTLs Recomendados por Tipo de Datos](#ttls-recomendados-por-tipo-de-datos)
3. [Memoria de Conversación con Caché Optimizada](#122-implementación-de-memoria-de-conversación-con-caché-optimizada) 
4. [Gestión del Estado de Ejecución](#123-gestión-del-estado-de-ejecución)
5. [Caché para Workflows Complejos](#124-caché-para-workflows-complejos)
6. [Optimización de Herramientas y Editor Visual](#125-optimización-de-herramientas-y-editor-visual)
7. [Métricas de Rendimiento y Depuración](#126-métricas-de-rendimiento-y-depuración)
8. [Patrones Recomendados y Errores Comunes](#patrones-recomendados-y-errores-comunes)
   - [Patrones Recomendados](#patrones-recomendados)
   - [Errores Comunes a Evitar](#errores-comunes-a-evitar)

## Visión General

Esta fase complementa la implementación del núcleo del Agent Service, profundizando específicamente en la estrategia de caché optimizada para flujos de conversación, configuraciones de agentes y memoria persistente. El objetivo es mejorar el rendimiento, reducir la carga en la base de datos y garantizar una experiencia fluida incluso con alta demanda. La implementación incluye soporte para el editor visual de frontend, workflows complejos y sistemas de logging detallado.

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

## 1.2.4 Caché para Workflows Complejos

La implementación de workflows complejos requiere un sistema de caché especializado que pueda gestionar estados intermedios, transiciones y configuraciones de flujo. El `AgentWorkflowManager` utiliza este sistema para proporcionar una experiencia fluida incluso con flujos de trabajo multi-paso.

```python
async def cache_workflow_state(workflow_id: str, state: Dict[str, Any], tenant_id: str, ctx: Context = None) -> None:
    """Almacena el estado actual de un workflow en caché."""
    await CacheManager.set(
        data_type="workflow_state",
        resource_id=workflow_id,
        value=state,
        tenant_id=tenant_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        conversation_id=ctx.get_conversation_id() if ctx else None,
        ttl=CacheManager.ttl_extended  # 24 horas para workflows de larga duración
    )

async def get_workflow_state(workflow_id: str, tenant_id: str, ctx: Context = None) -> Dict[str, Any]:
    """Recupera el estado de un workflow usando el patrón Cache-Aside."""
    state, metrics = await get_with_cache_aside(
        data_type="workflow_state",
        resource_id=workflow_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_workflow_from_db,
        generate_func=create_default_workflow_state,
        agent_id=ctx.get_agent_id() if ctx else None,
        conversation_id=ctx.get_conversation_id() if ctx else None,
        ttl=CacheManager.ttl_extended
    )
    return state

async def cache_workflow_definition(workflow_id: str, definition: Dict[str, Any], tenant_id: str) -> None:
    """Almacena la definición completa de un workflow en caché."""
    await CacheManager.set(
        data_type="workflow_definition",
        resource_id=workflow_id,
        value=definition,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard  # 1 hora
    )
```

### Estrategia de Caché para Workflows

Los workflows complejos se benefician de una estrategia de caché en múltiples niveles:

1. **Definición del Workflow**: Caché de la estructura completa del workflow (nodos, transiciones, condiciones)
2. **Estado del Workflow**: Caché del estado actual de ejecución, incluyendo nodo actual y variables
3. **Resultados Intermedios**: Caché de resultados de pasos previos para evitar recálculos
4. **Historial de Ejecución**: Caché temporal del historial para análisis y depuración

Este enfoque permite que los workflows complejos se ejecuten de manera eficiente incluso cuando abarcan múltiples interacciones de usuario o llamadas asíncronas a servicios externos.

## 1.2.5 Optimización de Herramientas y Editor Visual

El Agent Service necesita dar soporte a un editor visual en el frontend que permita a los usuarios construir agentes con una interfaz gráfica. La estrategia de caché para esta funcionalidad se centra en la rápida disponibilidad de configuraciones y herramientas.

```python
async def get_agent_configuration_for_editor(agent_id: str, tenant_id: str, ctx: Context = None) -> Dict[str, Any]:
    """Obtiene la configuración completa de un agente optimizada para el editor visual."""
    config, metrics = await get_with_cache_aside(
        data_type="agent_editor_config",
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_agent_editor_config_from_db,
        generate_func=None,
        ttl=CacheManager.ttl_short  # 5 minutos para reflejar cambios rápidamente
    )
    return config

async def get_available_tools_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """Obtiene todas las herramientas disponibles para un tenant, considerando su tier."""
    tools, metrics = await get_with_cache_aside(
        data_type="available_tools",
        resource_id="all",
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_tools_from_tier_config,
        generate_func=None,
        ttl=CacheManager.ttl_standard  # 1 hora
    )
    return tools

async def cache_toolset_configuration(agent_id: str, toolset: Dict[str, Any], tenant_id: str) -> None:
    """Almacena la configuración de herramientas seleccionada desde el editor visual."""
    await CacheManager.set(
        data_type="agent_toolset",
        resource_id=agent_id,
        value=toolset,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard  # 1 hora
    )
```

### Optimizaciones para el Editor Visual

El editor visual requiere respuestas rápidas para proporcionar una experiencia fluida al usuario:

1. **Precargar Componentes**: Caché de componentes del editor (herramientas, plantillas, conectores)
2. **Validación Instantánea**: Caché de reglas de validación para feedback inmediato
3. **Vista Previa en Tiempo Real**: Almacenamiento temporal de configuraciones en progreso
4. **Historial de Versiones**: Caché de versiones previas para funcionalidad de deshacer/rehacer

## 1.2.6 Métricas de Rendimiento y Depuración

Un sistema de métricas robusto es esencial para monitorear el rendimiento de la caché y detectar problemas. El Agent Service implementa un sistema de seguimiento detallado.

```python
async def track_cache_metrics(data_type: str, tenant_id: str, operation: str, hit: bool, latency_ms: float) -> None:
    """Registra métricas de operaciones de caché para análisis de rendimiento."""
    await CacheManager.get_instance().increment_counter(
        counter_type="cache_operation",
        amount=1,
        resource_id=f"{data_type}:{operation}:{hit}",
        tenant_id=tenant_id,
        metadata={
            "data_type": data_type,
            "operation": operation,
            "hit": hit,
            "latency_ms": latency_ms
        }
    )

async def log_cache_event(data_type: str, event_type: str, details: Dict[str, Any], tenant_id: str) -> None:
    """Registra eventos importantes de caché para depuración y auditoría."""
    # Integración con sistema de logging para depuración avanzada
    logger.info(
        f"Cache event: {event_type}",
        extra={
            "tenant_id": tenant_id,
            "data_type": data_type,
            "event_type": event_type,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
    )
```

### Dashboard de Monitoreo de Caché

El sistema incluye un dashboard de monitoreo que visualiza:

1. **Tasa de Aciertos/Fallos**: Distribución por tipo de datos y tenant
2. **Latencia de Operaciones**: Tiempos de respuesta para diferentes fuentes de datos (caché vs DB)
3. **Tamaño de Caché**: Uso de memoria por tipo de datos y tenant
4. **Invalidaciones**: Frecuencia y distribución de invalidaciones de caché

Esta información permite optimizar TTLs, priorizar datos para precarga y detectar patrones de uso ineficientes.

## Patrones Recomendados y Errores Comunes

### Patrones Recomendados

1. **Uso de get_with_cache_aside para lógica completa de caché**
   ```python
   result, metrics = await get_with_cache_aside(
       data_type="agent_config",
       resource_id=agent_id,
       tenant_id=tenant_id,
       fetch_from_db_func=fetch_config_from_db,
       generate_func=None,  # Sin generación automática para configuraciones
       ttl=CacheManager.ttl_standard
   )
   ```

2. **Invalidación explícita cuando los datos cambian**
   ```python
   # Después de actualizar la configuración en la base de datos
   await CacheManager.invalidate(
       tenant_id=tenant_id,
       data_type="agent_config",
       resource_id=agent_id
   )
   ```

3. **Uso de TTLs adecuados por tipo de datos**
   ```python
   # Datos que raramente cambian
   await CacheManager.set(data_type="embedding", ..., ttl=CacheManager.ttl_extended)
   
   # Configuraciones que pueden cambiar
   await CacheManager.set(data_type="agent_config", ..., ttl=CacheManager.ttl_standard)
   
   # Resultados de consultas temporales
   await CacheManager.set(data_type="query_result", ..., ttl=CacheManager.ttl_short)
   ```

4. **Estandarización de metadatos con helper centralizado**
   ```python
   standardized_metadata = standardize_llama_metadata(
       metadata=original_metadata,
       tenant_id=tenant_id,
       agent_id=agent_id,
       conversation_id=conversation_id
   )
   ```

### Errores Comunes a Evitar

1. ❌ **Uso incorrecto de métodos estáticos vs de instancia**
   ```python
   # INCORRECTO: Intentar usar rpush como método estático
   await CacheManager.rpush(list_name, value, tenant_id)  # Error
   
   # CORRECTO: Usar rpush como método de instancia
   await CacheManager.get_instance().rpush(list_name, value, tenant_id)
   ```

2. ❌ **Reimplementación manual del patrón Cache-Aside**
   ```python
   # INCORRECTO: Implementar manualmente el patrón
   value = await CacheManager.get(data_type, resource_id, tenant_id)
   if not value:
       value = await fetch_from_db(resource_id)
       if value:
           await CacheManager.set(data_type, resource_id, value, tenant_id)
   ```

3. ❌ **Omisión del tenant_id en operaciones de caché**
   ```python
   # INCORRECTO: Omitir tenant_id
   await CacheManager.get(data_type, resource_id)  # Sin tenant_id
   ```

4. ❌ **Uso de TTLs hardcodeados en lugar de constantes**
   ```python
   # INCORRECTO: Hardcodear TTL
   await CacheManager.set(data_type, resource_id, value, tenant_id, ttl=3600)
   
   # CORRECTO: Usar constantes estandarizadas
   await CacheManager.set(data_type, resource_id, value, tenant_id, ttl=CacheManager.ttl_standard)
   ```

5. ❌ **Omisión de tracking de métricas**
   ```python
   # INCORRECTO: No realizar seguimiento de métricas importantes
   # Implementar operaciones de caché sin registro de métricas
   
   # CORRECTO: Integrar con el sistema de métricas
   result, metrics = await get_with_cache_aside(...) 
   # metrics contiene valores como cache_hit, latency_ms, etc.
   ```

### Buenas Prácticas

1. ✅ **Tener en cuenta la naturaleza de los datos para TTL**:
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
