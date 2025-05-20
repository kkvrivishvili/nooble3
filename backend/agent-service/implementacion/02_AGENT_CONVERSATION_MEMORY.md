# Sistema de Memoria y Caché para Conversaciones en Agent Service

## Introducción

Este documento detalla la arquitectura e implementación del sistema de memoria para conversaciones entre usuarios y agentes, diseñado con un enfoque de alto rendimiento, escalabilidad y consistencia. La implementación sigue los patrones y estándares establecidos en el proyecto Nooble3, con especial énfasis en el patrón Cache-Aside y la optimización de acceso a datos.

## Arquitectura General

### Componentes Principales

1. **ConversationMemoryManager**: Servicio central encargado de la gestión de memoria de conversaciones
2. **CacheManager**: Servicio de caché multinivel con soporte para operaciones básicas y de lista
3. **LangChainAgentService**: Servicio que implementa los agentes y utiliza la memoria para su ejecución
4. **Supabase**: Almacenamiento persistente para conversaciones y mensajes

### Diagrama de Flujo

```
Usuario → LangChainAgentService → ConversationMemoryManager → CacheManager → Redis
                                                             ↓
                                                          Supabase
```

## Implementación de Memoria y Caché

### 1. Estructura de Datos en Caché

#### 1.1. Memoria Global de Conversación

```
Clave: {tenant_id}:{conversation_id}:memory
Valor: {
    "messages": [...],  // Mensajes para compatibilidad con LangChain
    "metadata": {...}   // Metadatos de la conversación
}
TTL: ttl_standard (1 hora)
```

#### 1.2. Mensajes Individuales

```
Clave: {tenant_id}:{conversation_id}:message:{message_id}
Valor: {
    "id": "uuid",
    "role": "user|assistant|system",
    "content": "texto del mensaje",
    "created_at": "timestamp ISO",
    "metadata": {...}
}
TTL: ttl_extended (24 horas)
```

#### 1.3. Lista de Mensajes

```
Clave: {tenant_id}:{conversation_id}:messages
Tipo: Lista (REDIS)
Elementos: [mensaje1, mensaje2, ...]
TTL: ttl_extended (24 horas)
```

### 2. Operaciones Principales

#### 2.1. Obtener Memoria de Conversación

```python
async def get_memory(self, tenant_id: str, conversation_id: str, ctx: Context = None) -> Dict[str, Any]:
    # Intentar obtener de caché primero
    memory_data = await CacheManager.get(
        data_type="conversation_memory", 
        resource_id=conversation_id,
        tenant_id=tenant_id
    )
    
    # Si no está en caché, obtener de BD
    if not memory_data:
        memory_data = await self._fetch_memory_from_db(tenant_id, conversation_id)
        
        # Almacenar en caché para solicitudes futuras
        if memory_data:
            await CacheManager.set(
                data_type="conversation_memory",
                resource_id=conversation_id,
                value=memory_data,
                tenant_id=tenant_id,
                ttl=CacheManager.ttl_standard
            )
    
    return memory_data or {"messages": [], "metadata": {}}
```

#### 2.2. Guardar Memoria de Conversación

```python
async def save_memory(self, tenant_id: str, conversation_id: str, 
                     memory_dict: Dict[str, Any], ctx: Context = None) -> None:
    # Estandarizar metadatos
    standardized_metadata = standardize_langchain_metadata(
        metadata=memory_dict.get("metadata", {}),
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        ctx=ctx
    )
    memory_dict["metadata"] = standardized_metadata
    
    # Actualizar la caché
    await CacheManager.set(
        data_type="conversation_memory",
        resource_id=conversation_id,
        value=memory_dict,
        tenant_id=tenant_id,
        ttl=CacheManager.ttl_standard
    )
    
    # Persistir a la base de datos (async)
    await self._persist_memory_to_db(tenant_id, conversation_id, memory_dict)
```

#### 2.3. Agregar Mensaje Individual

```python
async def add_message(self, tenant_id: str, conversation_id: str, role: str, 
                    content: str, metadata: Dict[str, Any], ctx: Context = None) -> str:
    # Generar ID único para el mensaje
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
    
    # 1. Almacenar mensaje individual en caché
    await CacheManager.set(
        data_type="conversation_message",
        resource_id=message_id,
        value=message_data,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        ttl=CacheManager.ttl_extended
    )
    
    # 2. Agregar mensaje a la lista usando método de instancia
    await CacheManager.get_instance().rpush(
        list_name=f"{tenant_id}:{conversation_id}:messages",
        value=message_data,
        tenant_id=tenant_id
    )
    
    # 3. Persistir en base de datos (async)
    await self._store_message_in_db(tenant_id, conversation_id, message_data)
    
    return message_id
```

#### 2.4. Obtener Mensajes de Conversación

```python
async def get_messages(self, tenant_id: str, conversation_id: str, 
                      limit: int = 50, skip: int = 0, ctx: Context = None) -> List[Dict[str, Any]]:
    # Intentar obtener de la lista en Redis
    try:
        # Calcular índices para LRANGE
        start = skip
        end = (skip + limit - 1) if limit > 0 else -1
        
        # Operación con listas mediante get_instance()
        messages = await CacheManager.get_instance().lrange(
            list_name=f"{tenant_id}:{conversation_id}:messages",
            start=start,
            end=end,
            tenant_id=tenant_id
        )
        
        if messages:
            return messages
    except Exception:
        # Fallar silenciosamente e intentar con BD
        pass
    
    # Si no está en caché, recuperar de base de datos
    messages = await self._fetch_messages_from_db(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        limit=limit,
        skip=skip
    )
    
    # Reconstruir caché si se obtuvieron mensajes
    if messages:
        await self._rebuild_message_cache(tenant_id, conversation_id, messages)
        
    return messages
```

## Patrones de Uso

### 1. Patrón Cache-Aside

El patrón Cache-Aside es implementado consistentemente para todas las operaciones de memoria:

1. **Lectura**:
   - Intentar obtener de caché primero
   - Si no existe, obtener de base de datos
   - Si se obtiene de BD, guardar en caché
   - Devolver resultado

2. **Escritura**:
   - Escribir a caché
   - Escribir a base de datos (asíncrono)

### 2. Métodos Estáticos vs. Métodos de Instancia

Siguiendo los estándares del proyecto:

```python
# ✅ CORRECTO: Operaciones básicas con métodos estáticos
await CacheManager.get(data_type, resource_id, tenant_id=tenant_id)
await CacheManager.set(data_type, resource_id, value, tenant_id=tenant_id)

# ✅ CORRECTO: Operaciones de listas con métodos de instancia
await CacheManager.get_instance().rpush(list_name, value, tenant_id)
await CacheManager.get_instance().lrange(list_name, start, end, tenant_id)
```

### 3. Estructura de Claves

La estructura de claves sigue una jerarquía consistente para facilitar el mantenimiento y el rendimiento:

```
{tenant_id}:{conversation_id}:memory
{tenant_id}:{conversation_id}:messages
{tenant_id}:{conversation_id}:message:{message_id}
```

Esto permite:
- Búsquedas eficientes
- Operaciones por grupos (flush, scan)
- Aplicación de TTLs específicos por tipo

## TTLs y Políticas de Expiración

1. **Memoria Global de Conversación**: `ttl_standard` (1 hora)
   - Balance entre rendimiento y frescura de datos
   - Las conversaciones activas se mantienen en caché
   - Las inactivas expirarán gradualmente

2. **Mensajes Individuales y Listas**: `ttl_extended` (24 horas)
   - Permanecen más tiempo en caché para conversaciones frecuentes
   - Optimiza acceso a conversaciones completas
   - Reduce carga en base de datos para conversaciones populares

## Integración con LangChain

### Sincronización Bidireccional

1. **LangChain → Nuestro Sistema**:
   ```python
   # Sincronizar estado de memoria de LangChain a nuestro sistema
   memory_dict = agent.memory.dict()
   await memory_manager.save_memory(tenant_id, conversation_id, memory_dict, ctx)
   ```

2. **Nuestro Sistema → LangChain**:
   ```python
   # Cargar mensajes desde nuestro sistema a LangChain
   conversation_messages = await memory_manager.get_messages(tenant_id, conversation_id)
   
   langchain_memory = ConversationBufferMemory(
       return_messages=True,
       memory_key="chat_history"
   )
   
   for msg in conversation_messages:
       if msg["role"] == "user":
           langchain_memory.chat_memory.add_user_message(msg["content"])
       elif msg["role"] == "assistant":
           langchain_memory.chat_memory.add_ai_message(msg["content"])
   ```

## Modelos de Datos

### Mensaje de Conversación

```python
{
    "id": str,               # UUID del mensaje
    "role": str,             # "user", "assistant" o "system"
    "content": str,          # Contenido del mensaje
    "created_at": str,       # Timestamp ISO
    "metadata": {
        "agent_id": str,     # ID del agente
        "tenant_id": str,    # ID del tenant
        "timestamp": str,    # Timestamp de creación
        "execution_time": float,  # Tiempo de ejecución (para assistant)
        "user_message_id": str,   # Referencia al mensaje del usuario (para assistant)
        # Otros metadatos específicos
    }
}
```

### Memoria de Conversación

```python
{
    "messages": [
        # Lista de mensajes para compatibilidad con LangChain
    ],
    "metadata": {
        "agent_id": str,      # ID del agente
        "tenant_id": str,     # ID del tenant
        "conversation_id": str,  # ID de la conversación
        "updated_at": str,    # Timestamp de última actualización
        # Otros metadatos específicos
    }
}
```

## Métricas y Monitoreo

### Métricas Registradas

1. **Cache Hit/Miss**:
   - Aciertos y fallos en operaciones de caché
   - Tiempos de latencia
   - Distribución por tenant, tipo de operación, etc.

2. **Volumen de Mensajes**:
   - Mensajes por conversación
   - Distribución por tenant
   - Distribución por rol (user/assistant/system)

### Implementación de Métricas

```python
# Registrar métricas de caché
await track_cache_metrics(
    data_type="conversation_messages", 
    tenant_id=tenant_id, 
    operation="get", 
    hit=cache_hit, 
    latency_ms=latency_ms
)
```

## Tablas de Base de Datos

### Tabla de Mensajes

```sql
CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    metadata JSONB,
    
    CONSTRAINT fk_conversation
        FOREIGN KEY(tenant_id, conversation_id) 
        REFERENCES conversation_memories(tenant_id, conversation_id)
);

CREATE INDEX idx_conversation_messages_tenant_conversation
ON conversation_messages(tenant_id, conversation_id);
```

### Tabla de Memoria de Conversación

```sql
CREATE TABLE conversation_memories (
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    messages JSONB,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (tenant_id, conversation_id)
);

CREATE INDEX idx_conversation_memories_tenant
ON conversation_memories(tenant_id);
```

## Buenas Prácticas y Recomendaciones

1. **Almacenamiento Eficiente**:
   - Usar estructuras de datos optimizadas
   - Limitar el tamaño de metadatos
   - Establecer TTLs adecuados

2. **Seguridad**:
   - Validar siempre tenant_id
   - Utilizar el decorador @with_context
   - Asegurar que los mensajes solo son accesibles por su tenant

3. **Escalabilidad**:
   - Usar operaciones asíncronas para BD
   - Aprovechar batch operations cuando sea posible
   - Limitar tamaños máximos de respuesta

4. **Mantenimiento**:
   - Monitorear regularmente el uso de caché
   - Implementar limpieza periódica de datos antiguos
   - Verificar ratio hit/miss para optimizar TTLs

## Ejemplos de Uso

### Ejemplo 1: Ejecución de Agente con Memoria

```python
async def execute_agent(agent_id, chat_request, ctx):
    # 1. Obtener memoria existente
    conversation_memory = await memory_manager.get_memory(
        tenant_id=tenant_id,
        conversation_id=conversation_id
    )
    
    # 2. Cargar mensajes para LangChain
    messages = await memory_manager.get_messages(
        tenant_id=tenant_id,
        conversation_id=conversation_id
    )
    
    # 3. Configurar memoria de LangChain
    langchain_memory = ConversationBufferMemory(return_messages=True)
    for msg in messages:
        # Cargar mensajes previos...
    
    # 4. Guardar mensaje del usuario
    user_message_id = await memory_manager.add_message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role="user",
        content=chat_request.message,
        metadata={...}
    )
    
    # 5. Ejecutar agente...
    
    # 6. Guardar respuesta del asistente
    assistant_message_id = await memory_manager.add_message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role="assistant",
        content=response,
        metadata={...}
    )
    
    # 7. Actualizar memoria global
    await memory_manager.save_memory(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        memory_dict=agent.memory.dict()
    )
    
    # 8. Devolver respuesta
    return AgentResponse(...)
```

### Ejemplo 2: Reconstrucción de Caché

```python
async def rebuild_cache_for_tenant(tenant_id):
    # Obtener todas las conversaciones activas
    conversations = await fetch_active_conversations(tenant_id)
    
    for conversation in conversations:
        # Obtener mensajes de BD
        messages = await fetch_messages_from_db(tenant_id, conversation.id)
        
        # Reconstruir caché de mensajes
        await _rebuild_message_cache(tenant_id, conversation.id, messages)
        
        # Crear memoria global
        memory = {
            "messages": messages,
            "metadata": {
                "conversation_id": conversation.id,
                "tenant_id": tenant_id,
                "updated_at": datetime.now().isoformat()
            }
        }
        
        # Guardar en caché
        await CacheManager.set(
            data_type="conversation_memory",
            resource_id=conversation.id,
            value=memory,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
```

## Conclusión

El sistema de memoria y caché para conversaciones implementa una arquitectura de alto rendimiento basada en patrones establecidos (Cache-Aside, Repository) y buenas prácticas de caching. El uso de operaciones asíncronas, validación de tenants, y métodos especializados para distintos tipos de operaciones garantiza un sistema escalable, mantenible y eficiente.

La implementación proporciona una base sólida para futuras mejoras como sharding de datos, optimizaciones de rendimiento, o características avanzadas como resúmenes de conversaciones o análisis de sentimiento.
