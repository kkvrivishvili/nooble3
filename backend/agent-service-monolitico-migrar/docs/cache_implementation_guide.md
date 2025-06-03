# Guía de Implementación del Sistema de Caché en el Agent Service

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Arquitectura del Sistema de Caché](#arquitectura-del-sistema-de-caché)
3. [El Patrón Cache-Aside](#el-patrón-cache-aside)
4. [Implementación en Agent Service](#implementación-en-agent-service)
5. [Tipos de Datos y TTLs](#tipos-de-datos-y-ttls)
6. [Métricas y Monitoreo](#métricas-y-monitoreo)
7. [Invalidación de Caché](#invalidación-de-caché)
8. [Mejores Prácticas](#mejores-prácticas)
9. [Errores Comunes a Evitar](#errores-comunes-a-evitar)
10. [Referencias](#referencias)

## Introducción

El sistema de caché centralizado en el proyecto Nooble3 permite optimizar el rendimiento de los servicios backend, reduciendo la carga sobre la base de datos y mejorando los tiempos de respuesta. El Agent Service, al ser el orquestador central del sistema, hace un uso intensivo de este sistema para gestionar configuraciones de agentes, memoria de conversaciones y estados de ejecución.

Esta guía describe en detalle cómo funciona el sistema de caché centralizado y proporciona lineamientos específicos para su implementación en el Agent Service.

## Arquitectura del Sistema de Caché

El sistema de caché implementa una arquitectura de múltiples niveles, gestionada a través de la clase `CacheManager` en `common/cache/manager.py`:

### Componentes Principales

1. **Caché en Memoria**: 
   - Almacenamiento en memoria para acceso ultra-rápido
   - Implementado como diccionarios Python `_memory_cache` y `_memory_expiry`
   - Limitado por tamaño con política de limpieza automática

2. **Caché en Redis**:
   - Almacenamiento persistente distribuido mediante Redis
   - Soporte para TTL (Time-To-Live) configurable
   - Patrones de claves jerárquicas para multitenancy

3. **Jerarquía de Claves**:
   - Formato: `tenant_id:data_type:[agent:agent_id]:[conv:conversation_id]:[coll:collection_id]:resource_id`
   - Búsqueda en cascada desde lo más específico a lo más general
   - Garantiza aislamiento entre tenants y contextos

4. **Sistema de Serialización**:
   - Funciones especializadas por tipo de dato (`serialize_for_cache`, `deserialize_from_cache`)
   - Conversión automática de objetos complejos (embeddings, vector stores)
   - Detección y manejo de errores de serialización

### Tipos de Acceso a Caché

El sistema de caché proporciona dos tipos de acceso:

#### 1. Métodos Estáticos de CacheManager

Para operaciones básicas (get, set, delete, invalidate):

```python
await CacheManager.get(data_type, resource_id, tenant_id=tenant_id)
await CacheManager.set(data_type, resource_id, value, tenant_id=tenant_id)
await CacheManager.delete(data_type, resource_id, tenant_id=tenant_id)
await CacheManager.invalidate(tenant_id, data_type, resource_id=resource_id)
```

#### 2. Métodos de Instancia de CacheManager

Para operaciones avanzadas como listas:

```python
cache_manager = CacheManager.get_instance()
await cache_manager.rpush(list_name, value, tenant_id)
await cache_manager.lpop(list_name, tenant_id)
await cache_manager.lrange(list_name, start, end, tenant_id)
```

## El Patrón Cache-Aside

El patrón Cache-Aside es la estrategia central para interactuar con la caché. Está implementado como una función unificada `get_with_cache_aside` en `common/cache/helpers.py` que debe usarse consistentemente en todos los servicios.

### Flujo del Patrón

1. **Verificar Caché**: Primero se busca el dato en caché (memoria + Redis)
2. **Buscar en DB**: Si no está en caché, se obtiene de la base de datos
3. **Generar Dato**: Si no está en la DB y se proporciona una función generadora, se crea el dato
4. **Almacenar en Caché**: Se guarda el resultado en caché con el TTL apropiado
5. **Retornar Resultado**: Se devuelve el dato con métricas de rendimiento

### Implementación Unificada

```python
result, metrics = await get_with_cache_aside(
    data_type="agent_config",                 # Tipo de datos
    resource_id=agent_id,                     # ID del recurso
    tenant_id=tenant_id,                      # ID del tenant
    fetch_from_db_func=fetch_agent_from_db,   # Función para obtener de DB
    generate_func=None,                       # Función para generar (opcional)
    agent_id=agent_id,                        # Contexto adicional
    conversation_id=None,                     # Contexto adicional
    collection_id=None,                       # Contexto adicional
    ttl=TTL_STANDARD                          # TTL personalizado (opcional)
)
```

### Métricas Proporcionadas

El patrón retorna información detallada sobre la operación:

```python
metrics = {
    "source": "cache",              # Fuente del dato (cache, supabase, generation)
    "cache_hit": True,              # Si se encontró en caché
    "cache_check_time_ms": 5.2,     # Tiempo para verificar caché
    "db_check_time_ms": 0,          # Tiempo para verificar DB (si aplica)
    "generation_time_ms": 0,        # Tiempo para generar (si aplica)
    "total_time_ms": 5.2,           # Tiempo total de la operación
    "data_type": "agent_config",    # Tipo de datos procesado
    "resource_id": "agent123"       # ID del recurso
}
```

## Implementación en Agent Service

El Agent Service gestiona varios tipos de datos en caché, cada uno con patrones y TTLs específicos:

### Recursos Principales a Cachear

1. **Configuraciones de Agentes**:
   - Tipo: `agent_config`
   - ID: Identificador único del agente
   - TTL: TTL_STANDARD (1 hora)

2. **Herramientas de Agentes**:
   - Tipo: `agent_tools`
   - ID: Identificador del agente o de la herramienta
   - TTL: TTL_STANDARD (1 hora)

3. **Memoria de Conversación**:
   - Tipo: `conversation_memory`
   - ID: Identificador de la conversación
   - TTL: TTL_EXTENDED (24 horas)

4. **Mensajes de Conversación**:
   - Tipo: `conversation_message`
   - ID: Identificador del mensaje
   - TTL: TTL_EXTENDED (24 horas)

5. **Estado de Ejecución**:
   - Tipo: `agent_execution_state`
   - ID: Combinación de identificadores de agente, conversación y ejecución
   - TTL: TTL_SHORT (5 minutos)

### Ejemplo de Implementación para Agentes

```python
# Obtener configuración de un agente
async def get_agent_config(agent_id: str, tenant_id: str) -> Dict[str, Any]:
    """Obtiene la configuración de un agente usando el patrón Cache-Aside."""
    
    # Función para obtener el agente de la base de datos
    async def fetch_agent_from_db(resource_id: str, tenant_id: str, **kwargs) -> Dict:
        supabase = get_supabase_client()
        result = await supabase.table("agents") \
            .select("*") \
            .eq("id", resource_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    
    # Usar el patrón Cache-Aside centralizado
    agent_config, metrics = await get_with_cache_aside(
        data_type="agent_config",
        resource_id=agent_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_agent_from_db,
        ttl=TTL_STANDARD
    )
    
    # Registrar métricas (opcional)
    logger.debug(f"Agent config cache metrics: {metrics}")
    
    return agent_config
```

### Ejemplo para Memoria de Conversación

```python
# Obtener memoria de conversación
async def get_conversation_memory(tenant_id: str, conversation_id: str, agent_id: str = None) -> Dict:
    """Obtiene la memoria de conversación con el patrón Cache-Aside."""
    
    # Función para obtener memoria de la base de datos
    async def fetch_memory_from_db(resource_id: str, tenant_id: str, **kwargs) -> Dict:
        # Implementación de consulta a Supabase
        # ...
    
    # Función para crear memoria vacía si no existe
    async def create_empty_memory(resource_id: str, tenant_id: str, **kwargs) -> Dict:
        return {
            "messages": [],
            "metadata": {
                "tenant_id": tenant_id,
                "conversation_id": resource_id,
                "agent_id": kwargs.get("agent_id"),
                "created_at": time.time()
            }
        }
    
    # Usar el patrón Cache-Aside
    memory, metrics = await get_with_cache_aside(
        data_type="conversation_memory",
        resource_id=conversation_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_memory_from_db,
        generate_func=create_empty_memory,
        agent_id=agent_id,
        conversation_id=conversation_id,
        ttl=TTL_EXTENDED
    )
    
    return memory
```

## Tipos de Datos y TTLs

El Agent Service define TTLs específicos para cada tipo de dato en `config/constants.py`:

```python
# Mapeo de TTLs específicos del Agent Service
AGENT_SERVICE_TTL_MAPPING = {
    "agent": TTL_STANDARD,                    # 1 hora
    "agent_config": TTL_STANDARD,             # 1 hora
    "agent_tools": TTL_STANDARD,              # 1 hora
    "conversation": TTL_EXTENDED,             # 24 horas
    "conversation_memory": TTL_EXTENDED,      # 24 horas
    "conversation_message": TTL_EXTENDED,     # 24 horas
    "conversation_messages_list": TTL_EXTENDED, # 24 horas
    "agent_execution_state": TTL_SHORT,       # 5 minutos
    "collection_metadata": TTL_STANDARD,      # 1 hora
}
```

### Función para Determinar TTL

```python
def get_ttl_for_data_type(data_type: str) -> int:
    """
    Obtiene el TTL apropiado según el tipo de datos.
    Primero busca en el mapeo específico del servicio, luego en el global.
    """
    # Verificar en mapeo específico
    if data_type in AGENT_SERVICE_TTL_MAPPING:
        return AGENT_SERVICE_TTL_MAPPING[data_type]
    
    # Verificar en mapeo global
    if data_type in DEFAULT_TTL_MAPPING:
        return DEFAULT_TTL_MAPPING[data_type]
    
    # Valor por defecto
    return TTL_STANDARD
```

## Métricas y Monitoreo

El Agent Service debe registrar métricas detalladas sobre el uso de caché para:

1. **Tasa de Aciertos/Fallos**:
   - Por tipo de datos y tenant
   - Identificación de patrones de uso

2. **Latencia**:
   - Tiempos de respuesta de caché vs. base de datos
   - Detección de cuellos de botella

3. **Tamaño de Objetos**:
   - Monitoreo de uso de memoria
   - Identificación de objetos grandes

### Implementación de Métricas

```python
# Registrar métricas de caché
async def track_agent_cache_metrics(
    tenant_id: str,
    data_type: str,
    operation: str,
    cache_hit: bool,
    latency_ms: float,
    agent_id: Optional[str] = None
):
    """Registra métricas específicas del Agent Service para caché."""
    metric_type = METRIC_CACHE_HIT if cache_hit else METRIC_CACHE_MISS
    
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type=metric_type,
        value=1,
        agent_id=agent_id,
        metadata={
            "operation": operation,
            "latency_ms": latency_ms,
            "service": "agent"
        }
    )
    
    # Registrar latencia también
    await track_cache_metrics(
        data_type=data_type,
        tenant_id=tenant_id,
        metric_type=METRIC_LATENCY,
        value=latency_ms,
        agent_id=agent_id,
        metadata={
            "operation": operation,
            "service": "agent"
        }
    )
```

## Invalidación de Caché

El Agent Service debe implementar estrategias de invalidación en cascada para mantener la consistencia de datos:

### Invalidación de Agentes

Cuando se actualiza un agente, deben invalidarse:
- La configuración del agente
- Las herramientas asociadas
- El estado de ejecución
- Opcionalmente, las conversaciones relacionadas

```python
async def invalidate_agent_cache_cascade(
    tenant_id: str,
    agent_id: str,
    invalidate_conversations: bool = False
) -> Dict[str, int]:
    """Invalida en cascada todas las cachés relacionadas con un agente."""
    
    invalidation_results = {
        "agent": 0,
        "agent_config": 0,
        "agent_tools": 0,
        "conversations": 0
    }
    
    # 1. Invalidar configuración del agente
    agent_keys = await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="agent",
        resource_id=agent_id
    )
    invalidation_results["agent"] = agent_keys
    
    # 2. Invalidar configuración de herramientas
    config_keys = await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="agent_config",
        resource_id=agent_id
    )
    invalidation_results["agent_config"] = config_keys
    
    # 3. Invalidar herramientas
    tools_keys = await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="agent_tools",
        resource_id=agent_id
    )
    invalidation_results["agent_tools"] = tools_keys
    
    # 4. Si se solicita, invalidar conversaciones relacionadas
    if invalidate_conversations:
        # Obtener conversaciones relacionadas desde BD
        supabase = get_supabase_client()
        result = await supabase.table("conversations") \
            .select("id") \
            .eq("agent_id", agent_id) \
            .eq("tenant_id", tenant_id) \
            .execute()
        
        if result.data:
            for conv in result.data:
                await invalidate_conversation_cache(
                    tenant_id=tenant_id,
                    conversation_id=conv["id"],
                    agent_id=agent_id
                )
                invalidation_results["conversations"] += 1
    
    # Registrar métrica de invalidación coordinada
    await track_cache_metrics(
        data_type="agent_cascade",
        tenant_id=tenant_id,
        metric_type=METRIC_CACHE_INVALIDATION_COORDINATED,
        value=sum(invalidation_results.values()),
        agent_id=agent_id,
        metadata=invalidation_results
    )
    
    return invalidation_results
```

### Invalidación de Conversaciones

```python
async def invalidate_conversation_cache(
    tenant_id: str,
    conversation_id: str,
    agent_id: Optional[str] = None
) -> int:
    """Invalida la caché relacionada con una conversación."""
    
    # Invalidar memoria de conversación
    memory_keys = await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="conversation_memory",
        resource_id=conversation_id,
        agent_id=agent_id
    )
    
    # Invalidar mensajes de la conversación
    message_keys = await CacheManager.invalidate(
        tenant_id=tenant_id,
        data_type="conversation_message",
        resource_id="*",  # Wildcard para todos los mensajes
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Registrar métrica
    total_keys = memory_keys + message_keys
    await track_cache_metrics(
        data_type="conversation",
        tenant_id=tenant_id,
        metric_type=METRIC_CACHE_INVALIDATION,
        value=total_keys,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    return total_keys
```

## Mejores Prácticas

### 1. Uso del Patrón Cache-Aside

- **Siempre usar `get_with_cache_aside`** para operaciones que pueden requerir fallback a base de datos
- Proporcionar funciones asíncronas bien definidas para `fetch_from_db_func` y `generate_func`
- Manejar adecuadamente las métricas retornadas para monitoreo y depuración

### 2. Gestión de Claves

- Utilizar constantes predefinidas para tipos de datos (`CACHE_TYPE_AGENT`, `CACHE_TYPE_CONVERSATION_MEMORY`)
- Generar resource_ids consistentes para el mismo recurso (usar `generate_resource_id_hash` para objetos complejos)
- Proporcionar siempre el contexto relevante (tenant_id, agent_id, conversation_id)

### 3. Estrategias de TTL

- Usar constantes de TTL desde `common/core/constants.py` (TTL_SHORT, TTL_STANDARD, TTL_EXTENDED)
- Aplicar TTLs apropiados según la volatilidad del dato
- Considerar factores como frecuencia de acceso y costo de regeneración

### 4. Uso de Memoria en Caché

- Implementar mecanismo de estimación de tamaño para objetos grandes
- Monitorear y alertar sobre objetos que exceden umbrales de tamaño
- Aplicar políticas de expiración más agresivas para datos voluminosos

## Errores Comunes a Evitar

1. **Reimplementación Manual del Patrón Cache-Aside**:
   ```python
   # ❌ INCORRECTO: Reimplementación manual
   value = await CacheManager.get(data_type, resource_id, tenant_id)
   if not value:
       value = await fetch_from_db(resource_id, tenant_id)
       if value:
           await CacheManager.set(data_type, resource_id, value, tenant_id)
   
   # ✅ CORRECTO: Uso del patrón centralizado
   value, metrics = await get_with_cache_aside(
       data_type=data_type,
       resource_id=resource_id,
       tenant_id=tenant_id,
       fetch_from_db_func=fetch_from_db
   )
   ```

2. **Uso Incorrecto de Métodos Estáticos vs. Instancia**:
   ```python
   # ❌ INCORRECTO: Llamar método de instancia como estático
   await CacheManager.rpush(list_name, value, tenant_id)  # Error: no existe como método estático
   
   # ✅ CORRECTO: Uso de métodos de instancia para listas
   await CacheManager.get_instance().rpush(list_name, value, tenant_id)
   ```

3. **Omisión de Tenant ID**:
   ```python
   # ❌ INCORRECTO: Omitir tenant_id
   await CacheManager.get(data_type, resource_id)  # Puede causar fugas de datos entre tenants
   
   # ✅ CORRECTO: Proporcionar siempre tenant_id
   await CacheManager.get(data_type, resource_id, tenant_id=tenant_id)
   ```

4. **Serialización Manual de Objetos Complejos**:
   ```python
   # ❌ INCORRECTO: Serialización manual de embeddings
   embedding_json = json.dumps(embedding.tolist())
   await CacheManager.set("embedding", key, embedding_json, tenant_id)
   
   # ✅ CORRECTO: Usar serializadores especializados
   await CacheManager.set("embedding", key, embedding, tenant_id)  # Usa serializer interno
   ```

5. **TTL Hardcodeados**:
   ```python
   # ❌ INCORRECTO: TTL hardcodeado
   await CacheManager.set(data_type, resource_id, value, tenant_id, ttl=3600)
   
   # ✅ CORRECTO: Usar constantes de TTL
   from common.core.constants import TTL_STANDARD
   await CacheManager.set(data_type, resource_id, value, tenant_id, ttl=TTL_STANDARD)
   
   # ✅ MEJOR: Usar función específica por tipo
   ttl = get_ttl_for_data_type(data_type)
   await CacheManager.set(data_type, resource_id, value, tenant_id, ttl=ttl)
   ```

## Referencias

1. **Documentación centralizada**:
   - `common/cache/README.md` - Documentación general del sistema de caché
   - `CACHE_IMPLEMENTATION_GUIDE.md` - Guía oficial de implementación

2. **Constantes y configuraciones**:
   - `common/core/constants.py` - Definiciones de TTL y mapeos por defecto
   - `config/constants.py` - Constantes y TTLs específicas del Agent Service

3. **Herramientas centralizadas**:
   - `common/cache/manager.py` - Implementación principal del `CacheManager`
   - `common/cache/helpers.py` - Funciones auxiliares como `get_with_cache_aside`
