# Estándar de Gestión de Contexto Multitenancy

**Tags:** `#context_management` `#multitenancy` `#backend`

## 1. Principios Fundamentales

**Tags:** `#principles`

1. **Consistencia**: Mismo manejo de contexto en todos los servicios
2. **Centralización**: Un único sistema para referenciar el contexto
3. **Propagación automática**: Transferencia transparente entre servicios
4. **Validación explícita**: Verificación rigurosa del contexto tenant
5. **Restauración segura**: El contexto original se restaura automáticamente
6. **Integración con logs**: Enriquecimiento de logs con datos de contexto

## 2. Arquitectura del Sistema

**Tags:** `#architecture`

### 2.1 Estructura de Módulos

```
common/context/
├── __init__.py      # Exportación centralizada de componentes
├── decorators.py    # Decorador with_context y clase Context
├── vars.py          # Variables contextuales y funciones básicas
├── validator.py     # Validación de tenant_id
├── propagation.py   # Propagación entre servicios vía HTTP
└── memory.py        # ContextManager para memoria de contexto
```

### 2.2 Componentes Principales

**Tags:** `#components`

1. **Variables Contextuales**: Almacenamiento thread-safe con `contextvars`
2. **Clase Context**: Administrador de contexto unificado
3. **Decorador @with_context**: API recomendada para servicios
4. **ContextManager**: Gestión de memoria conversacional y colecciones
5. **Utilidades de Propagación**: Headers HTTP estandarizados

### 2.3 Importaciones Correctas

**Tags:** `#imports`

```python
# ✅ CORRECTO - Importar desde el módulo principal
from common.context import (
    with_context, Context,
    get_current_tenant_id, get_current_agent_id
)

# ❌ INCORRECTO - No importar desde submódulos internos
from common.context.vars import get_current_tenant_id  # Evitar
```

## 3. Principales Patrones de Uso

**Tags:** `#usage_patterns`

### 3.1 Decorador @with_context (Patrón Principal)

```python
@router.post("/api/agents/{agent_id}/query")
@with_context(tenant=True, agent=True, conversation=True)
async def query_agent(
    agent_id: str, 
    request: QueryRequest,
    ctx: Context
):
    # El contexto ya está disponible y validado
    tenant_id = ctx.get_tenant_id()  # Validado, nunca None o "default"
    agent_id = ctx.get_agent_id()    # Valor de la URL o del contexto
    conversation_id = ctx.get_conversation_id()  # Del contexto
    
    # Uso del contexto validado para la operación...
    result = await process_agent_query(tenant_id, agent_id, conversation_id, request.query)
    return result
```

### 3.2 Clase Context para Bloques de Código

```python
async def process_for_different_tenant(original_tenant_id, target_tenant_id):
    # Código con tenant original...
    
    async with Context(tenant_id=target_tenant_id, validate_tenant=True):
        # Este bloque se ejecuta con el tenant_id=target_tenant_id
        result = await service_that_needs_different_tenant()
    
    # El contexto vuelve automáticamente al tenant original
```

### 3.3 ContextManager para Conversaciones

```python
from common.context.memory import ContextManager

# Obtener o crear gestor de contexto para esta conversación
ctx_manager = ContextManager.get_instance(
    tenant_id="tenant_abc",
    agent_id="agent_123",
    conversation_id="conv_456"
)

# Añadir mensaje a la conversación
message_id = await ctx_manager.add_message({
    "role": "user",
    "content": "¿Cómo puedo configurar mi agente?",
    "timestamp": time.time()
})

# Obtener historial de la conversación
conversation_history = await ctx_manager.get_conversation_history()

# Registrar una colección utilizada
await ctx_manager.register_collection("collection_789")
```

## 4. El Decorador @with_context en Detalle

**Tags:** `#decorator`

### 4.1 Parámetros Disponibles

```python
@with_context(
    tenant=True,              # Propagar tenant_id (True por defecto)
    agent=False,              # Propagar agent_id 
    conversation=False,       # Propagar conversation_id
    collection=False,         # Propagar collection_id
    validate_tenant=True      # Validar tenant_id (True por defecto)
)
```

| Parámetro | Propósito | Valor por defecto |
|-----------|-----------|-------------------|
| `tenant` | Propagar tenant_id | `True` |
| `agent` | Propagar agent_id | `False` |
| `conversation` | Propagar conversation_id | `False` |
| `collection` | Propagar collection_id | `False` |
| `validate_tenant` | Validar que tenant_id sea válido | `True` |

### 4.2 Comportamiento con Validación

- Cuando `validate_tenant=True` (predeterminado):
  - Se verifica que tenant_id no sea None ni "default"
  - Si es inválido, lanza `ServiceError` con código `ERROR_TENANT_REQUIRED` 
  - Acceso seguro a través de `ctx.get_tenant_id()`

- Cuando `validate_tenant=False`:
  - No hay validación automática
  - `ctx.get_tenant_id()` sigue validando y puede lanzar excepciones
  - Se puede acceder sin validación con `get_current_tenant_id()`

### 4.3 Inyección del Parámetro Context

```python
@with_context(tenant=True)
async def my_function(request, ctx: Context):
    # El decorador inyecta automáticamente 'ctx'
    tenant_id = ctx.get_tenant_id()
```

Si la función no tiene el parámetro `ctx`, el decorador lo añade automáticamente.

## 5. Clase Context en Detalle

**Tags:** `#context_class`

### 5.1 Inicialización

```python
# Establecer valores específicos
ctx = Context(
    tenant_id="tenant_abc",
    agent_id="agent_123",
    conversation_id="conv_456",
    collection_id="coll_789",
    validate_tenant=True   # Validar tenant_id al establecerlo
)

# Solo validar el tenant actual sin modificarlo
ctx = Context(validate_tenant=True)
```

### 5.2 Uso como Administrador de Contexto

```python
# Uso síncrono
with Context(tenant_id="tenant_abc") as ctx:
    # Código con tenant_id establecido
    pass  # El contexto original se restaura al salir

# Uso asíncrono
async with Context(tenant_id="tenant_abc") as ctx:
    # Código asíncrono con tenant_id establecido
    await async_function()  # El contexto original se restaura al salir
```

### 5.3 Métodos de Acceso

```python
# Acceso con validación
tenant_id = ctx.get_tenant_id()  # Lanza error si inválido

# Acceso sin garantía (puede ser None)
agent_id = ctx.get_agent_id()
conversation_id = ctx.get_conversation_id()
collection_id = ctx.get_collection_id()
```

## 6. ContextManager para Memoria de Contexto

**Tags:** `#context_manager` `#memory`

### 6.1 Propósito y Responsabilidades

La clase `ContextManager` gestiona:
- Historial de conversaciones
- Registro de mensajes
- Seguimiento de colecciones utilizadas
- Persistencia del contexto entre solicitudes

### 6.2 Patrón Singleton con Registro

```python
# Obtener instancia única por combinación de identificadores
ctx_manager = ContextManager.get_instance(
    tenant_id="tenant_abc",
    agent_id="agent_123",
    conversation_id="conv_456",
    user_id="user_789",      # Opcional
    session_id="session_012" # Opcional
)
```

El método `get_instance()` garantiza que se use la misma instancia para la misma combinación de identificadores.

### 6.3 Gestión de Conversaciones

```python
# Añadir mensaje a la conversación
message_id = await ctx_manager.add_message({
    "role": "user",
    "content": "¿Cómo funciona este producto?",
    "timestamp": time.time()
})

# Recuperar historial completo
messages = await ctx_manager.get_conversation_history()

# El ContextManager usa automáticamente CacheManager
# con los identificadores adecuados (tenant_id, agent_id, etc.)
```

### 6.4 Gestión de Colecciones

```python
# Registrar colección utilizada en esta conversación
await ctx_manager.register_collection("collection_123")

# Obtener todas las colecciones usadas
collections = await ctx_manager.get_collections()

# Las colecciones se almacenan en caché y en memoria
```

### 6.5 Limpieza de Recursos

```python
# Limpiar el contexto actual y liberar recursos
ctx_manager.clear()
```

## 7. Propagación de Contexto

**Tags:** `#context_propagation`

### 7.1 Headers HTTP Estándar

```
X-Tenant-ID: tenant_abc
X-Agent-ID: agent_123
X-Conversation-ID: conv_456
X-Collection-ID: coll_789
```

### 7.2 Funciones de Manipulación de Headers

```python
# Extraer contexto de headers
ctx_data = extract_context_from_headers(request.headers)
# → {"tenant_id": "tenant_abc", "agent_id": "agent_123", ...}

# Añadir contexto actual a headers
headers = add_context_to_headers({"Authorization": "Bearer token"})
# → {"Authorization": "Bearer token", "X-Tenant-ID": "tenant_abc", ...}

# Configurar contexto desde headers (establece variables contextuales)
tokens = setup_context_from_headers(request.headers)
# Restaurar después:
for token, name in reversed(tokens):
    reset_context(token, name)
```

### 7.3 Función de Ejecución con Contexto Específico

```python
# Ejecutar una corrutina con un contexto específico
result = await run_public_context(
    coro=fetch_public_data(),
    tenant_id="public",
    agent_id=None
)
```

## 8. Acceso a Variables de Contexto

**Tags:** `#context_variables`

### 8.1 Acceso Validado (Recomendado)

```python
@with_context(tenant=True)
async def secure_function(ctx: Context):
    # Acceso validado - garantizado que no es None ni "default"
    tenant_id = ctx.get_tenant_id()
```

### 8.2 Acceso Directo (Uso Limitado)

```python
# Acceso directo sin validación - puede ser None o "default"
tenant_id = get_current_tenant_id()
agent_id = get_current_agent_id()
conversation_id = get_current_conversation_id()
collection_id = get_current_collection_id()
```

### 8.3 Establecimiento Manual (Uso Interno)

```python
# Establecer variables de contexto directamente (uso interno)
token = set_current_tenant_id("tenant_abc")
# Restaurar después:
reset_context(token, "tenant_id")
```

## 9. Integración con Sistema de Logging

**Tags:** `#logging`

### 9.1 Prefijo Automático en Logs

```python
from common.context.propagation import get_context_log_prefix, ContextAwareLogger

# Prefix manual
prefix = get_context_log_prefix()  # "[t:tenant_a a:agent_12] "
logger.info(f"{prefix}Mensaje con prefijo")

# Logger automático
ctx_logger = ContextAwareLogger(__name__)
ctx_logger.info("Mensaje")  # "[t:tenant_a a:agent_12] Mensaje"
```

### 9.2 Contexto en Metadatos de Logs

```python
# Añadir información de contexto a logs
context = get_full_context()
logger.info("Operación completada", extra=context)
```

### 9.3 Configuración Global de Logging

```python
# Configurar sistema de logging para incluir contexto
from common.context.propagation import add_context_to_log_record

# Llamar durante inicialización de la aplicación
add_context_to_log_record()
```

## 10. Escenarios Comunes

**Tags:** `#common_scenarios`

### 10.1 Operaciones Específicas de Tenant

```python
@with_context(tenant=True)
async def tenant_specific_operation(tenant_id: str, ctx: Context):
    # El tenant_id del parámetro podría ser diferente del contexto
    # Uso explícito para esta operación:
    validated_tenant = ctx.get_tenant_id()
    
    # Operación específica para este tenant
    result = await db.execute(
        f"SELECT * FROM {validated_tenant}.users LIMIT 10"
    )
```

### 10.2 Endpoints Públicos

```python
@router.get("/public/status")
@with_context(tenant=True, validate_tenant=False)
async def public_endpoint():
    # No requiere tenant válido
    tenant_id = get_current_tenant_id()  # Puede ser None/"default"
    
    # Operación que funciona sin tenant específico
    return {"status": "online", "tenant": tenant_id}
```

### 10.3 Conversaciones de Agente

```python
@router.post("/api/agents/{agent_id}/chat")
@with_context(tenant=True, agent=True, conversation=True)
async def agent_chat(
    agent_id: str,
    request: ChatRequest,
    ctx: Context
):
    # Contexto validado
    tenant_id = ctx.get_tenant_id()
    conversation_id = ctx.get_conversation_id() or request.conversation_id
    
    # Obtener gestor de contexto para esta conversación
    ctx_manager = ContextManager.get_instance(
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id
    )
    
    # Añadir mensaje de usuario
    await ctx_manager.add_message({
        "role": "user",
        "content": request.message,
        "timestamp": time.time()
    })
    
    # Obtener historial para procesamiento
    conversation_history = await ctx_manager.get_conversation_history()
    
    # Procesar respuesta...
    
    # Añadir respuesta del agente
    await ctx_manager.add_message({
        "role": "assistant",
        "content": response,
        "timestamp": time.time()
    })
    
    return {"response": response, "conversation_id": conversation_id}
```

## 11. Buenas Prácticas

**Tags:** `#best_practices`

### 11.1 Orden Correcto de Decoradores

```python
@router.post("/endpoint")      # 1. Decorador de router 
@with_context(tenant=True)     # 2. Decorador de contexto
@handle_errors(error_type="service")  # 3. Decorador de errores
async def my_endpoint(request, ctx: Context):
    # Implementación...
```

### 11.2 Validación Explícita

```python
# Explicitar qué validaciones se aplican
@with_context(
    tenant=True,      # Propagar tenant_id
    validate_tenant=True,  # Validar tenant_id
    agent=True        # Propagar agent_id (sin validación)
)
```

### 11.3 Uso Mínimo Necesario

```python
# Solo propagar lo que realmente se necesita
@with_context(tenant=True)  # Solo tenant si es lo único que se usa
async def simple_function(ctx: Context):
    tenant_id = ctx.get_tenant_id()
    # No propagar agent_id/conversation_id si no se usan
```

### 11.4 Manejo de ContextManager

```python
# Obtener instancia única
ctx_manager = ContextManager.get_instance(
    tenant_id=tenant_id,
    agent_id=agent_id,
    conversation_id=conversation_id
)

try:
    # Operaciones con el gestor de contexto
    await ctx_manager.add_message(message)
    
    # Más operaciones...
finally:
    # Limpiar solo cuando ya no se necesita más
    # Evitar limpiar en endpoints que procesan solicitudes individuales
    # ctx_manager.clear()  # Usar con precaución
```

## 12. Solución de Problemas

**Tags:** `#troubleshooting`

### 12.1 Errores de Validación de Tenant

```
ServiceError: Se requiere un tenant válido para esta operación
```

**Soluciones:**
1. Verificar que la ruta tenga `@with_context(tenant=True)`
2. Para endpoints públicos, usar `validate_tenant=False`
3. Añadir manejo explícito:

```python
try:
    tenant_id = ctx.get_tenant_id()
except ServiceError:
    # Manejar caso de tenant inválido
    return {"error": "Tenant requerido para esta operación"}
```

### 12.2 Pérdida de Contexto

**Síntoma:** Variables de contexto vacías entre llamadas asíncronas

**Soluciones:**
1. Usar el decorador `@with_context` en todos los niveles
2. Propagar contexto manualmente:

```python
# Capturar contexto actual
current_context = get_full_context()

# Propagar a función externa
async with Context(**current_context):
    await external_function()
```

### 12.3 Contexto No Propagado Entre Servicios

**Soluciones:**
1. Usar `call_service` de `common.utils.http`
2. Verificar la inclusión de headers correctos:

```python
headers = add_context_to_headers({})
response = await client.post(url, headers=headers)
```
