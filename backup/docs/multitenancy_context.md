# Mejoras en Manejo de Contexto Multitenancy

## Resumen

Este documento describe las mejoras implementadas en el sistema de validación y propagación de contexto multitenancy a través de los servicios backend. El objetivo principal es garantizar una validación consistente del `tenant_id` y prevenir comportamientos inesperados relacionados con el acceso basado en tenants.

## Problema Resuelto

Se identificaron inconsistencias en la validación del contexto de tenant a través de la aplicación:

1. Algunos servicios utilizaban `get_current_tenant_id()` sin validar si el tenant era válido (no nulo, no "default")
2. Existían diferentes implementaciones de validación de tenant esparcidas por el código
3. Falta de mensajes de error estandarizados cuando se intentaba acceder con un tenant inválido
4. Falta de contexto enriquecido en errores relacionados con tenants

## Solución Implementada

### 1. Función Centralizada para Obtener Tenant Validado

La función principal para obtener un tenant_id validado es `get_required_tenant_id()`:

```python
def get_required_tenant_id() -> str:
    """
    Obtiene el ID del tenant actual, exigiendo que exista uno válido.
    
    Esta es la función principal para obtener un tenant_id validado.
    Debe usarse en todos los endpoints y servicios que requieran un tenant
    válido para funcionar correctamente.
    
    Returns:
        str: ID del tenant validado (nunca será "default" ni None)
        
    Raises:
        ServiceError: Si no hay un tenant_id válido en el contexto
    """
    # Implementación que centraliza toda la lógica de validación
    # ...
```

### 2. Relación Entre las Funciones de Contexto

El sistema de manejo de contexto de tenant ahora está centralizado con estas funciones:

* `get_current_tenant_id()`: Se mantiene por compatibilidad, sólo devuelve el valor sin validar. Usar sólo cuando se permita un tenant no válido o "default".
* `get_required_tenant_id()`: **La función principal recomendada**. Obtiene un tenant validado o lanza una excepción.
* `validate_tenant_context()`: Valida un tenant_id específico. Se mantiene por compatibilidad pero internamente usa `get_required_tenant_id()` cuando es posible.

### 3. Uso con el Decorador `@with_context`

El enfoque recomendado es usar el decorador `@with_context` en endpoints y funciones públicas:

```python
from common.context import with_context

@with_context(tenant=True)
async def my_endpoint(request: Request):
    # El contexto de tenant estará disponible automáticamente
    # Usar get_required_tenant_id() para obtener el tenant validado
    tenant_id = get_required_tenant_id()
    # ...
```

### 4. Servicios Actualizados

Los siguientes servicios han sido actualizados para usar el sistema unificado:

* `common/db/tables.py` - Validación en acceso a bases de datos
* `query-service/services/query_engine.py` - Validación en procesamiento de consultas
* `embedding-service/services/embedding_provider.py` - Validación en generación de embeddings
* `ingestion-service/services/queue.py` - Validación en procesamiento de trabajos

## Mejores Prácticas

1. **Validación Recomendada**: Usar `get_required_tenant_id()` en cualquier función que requiera un tenant válido.
2. **Decorador Preferido**: Aplicar `@with_context(tenant=True)` en endpoints de API y puntos de entrada.
3. **Manejo de Errores**: Permitir que las excepciones `ServiceError` con código `TENANT_REQUIRED` se propaguen hasta el middleware de errores.
4. **Enriquecimiento de Contexto**: Al capturar excepciones, incluir siempre el contexto completo en los logs para facilitar depuración.

## Próximos Pasos

1. Actualizar todas las funciones del sistema para usar `get_required_tenant_id()` en lugar de combinaciones de `get_current_tenant_id()` y `validate_tenant_context()`
2. Crear una guía de código para nuevos desarrolladores sobre el uso correcto del sistema de contexto
3. Evaluar agregar validación similar para otros elementos de contexto (agent_id, collection_id, etc.)

# Sistema Unificado de Contexto Multitenancy

## Introducción

Este documento describe el nuevo sistema unificado de gestión de contexto multitenancy implementado en la aplicación. La arquitectura se ha simplificado para utilizar un único enfoque basado en el decorador `@with_context` y la clase `Context`, eliminando la duplicación de código y estandarizando completamente el manejo del contexto de tenant.

## Problema Resuelto

Se identificaron los siguientes problemas en el sistema anterior:

1. Múltiples funciones con comportamientos similares pero ligeramente diferentes (`get_current_tenant_id()`, `get_required_tenant_id()`, `validate_tenant_context()`)
2. Duplicación de lógica de validación en varios archivos
3. Falta de un enfoque único y claramente definido para trabajar con contexto
4. Dificultad para entender qué funciones usar en qué situaciones

## Nueva Solución: Sistema Unificado

### 1. Principio de Diseño: Un Solo Enfoque

El nuevo sistema se basa en un único enfoque para manejar el contexto:

```python
from common.context import with_context

@with_context(tenant=True, validate_tenant=True)
async def my_endpoint(request, ctx):
    # ctx contiene todos los métodos necesarios
    tenant_id = ctx.get_tenant_id()  # Validado automáticamente
    # Resto del código
```

### 2. Componentes Principales

El sistema se compone de dos elementos principales:

#### 2.1 Decorador `@with_context`

```python
@with_context(
    tenant=True,              # Propagar tenant_id
    agent=False,              # Propagar agent_id
    conversation=False,       # Propagar conversation_id
    collection=False,         # Propagar collection_id
    validate_tenant=True      # Validar que tenant_id sea válido
)
```

Este decorador:
1. Propaga automáticamente las variables de contexto especificadas
2. Realiza la validación de tenant_id si se solicita
3. Proporciona un objeto `ctx` a la función decorada con métodos para acceder al contexto

#### 2.2 Clase `Context`

```python
from common.context import Context

# Uso directo como administrador de contexto
with Context(tenant_id="t123", validate_tenant=True) as ctx:
    tenant_id = ctx.get_tenant_id()  # Validado
    # Resto del código
```

Esta clase:
1. Actúa como administrador de contexto (con bloque `with`)
2. Proporciona métodos para acceder y validar los valores del contexto
3. Restaura automáticamente el contexto anterior al salir del bloque

### 3. Uso Recomendado

#### Para Endpoints de API

```python
from common.context import with_context

@with_context(tenant=True)  # validate_tenant=True por defecto
async def get_documents(request, ctx):
    tenant_id = ctx.get_tenant_id()  # Obtiene tenant validado
    # Usar tenant_id...
```

#### Para Endpoints Públicos (sin validación)

```python
@with_context(tenant=True, validate_tenant=False)
async def public_endpoint(request, ctx):
    tenant_id = current_tenant_id.get()  # Puede ser None o "default"
    # Lógica específica...
```

#### Para Funciones Internas

```python
@with_context(tenant=True, agent=True)
async def process_data(ctx, data):
    tenant_id = ctx.get_tenant_id()
    agent_id = ctx.get_agent_id()
    # Procesar datos...
```

### 4. Compatibilidad con Código Existente

El sistema mantiene compatibilidad con el código existente:

- `get_current_tenant_id()` - Disponible, pero no realiza validación
- `get_required_tenant_id()` - Redirige a `Context` con validación
- `validate_tenant_context()` - Redirige a `Context` con validación

Sin embargo, se recomienda migrar gradualmente todo el código a usar el nuevo enfoque unificado.

## Plan de Migración

1. Identificar todos los lugares donde se usan las funciones antiguas
2. Reemplazar con el decorador `@with_context` y el uso del objeto `ctx`
3. Eliminar gradualmente las referencias a las funciones antiguas

## Ventajas del Nuevo Sistema

1. **Simplicidad**: Un único enfoque claro para manejar el contexto
2. **Consistencia**: Comportamiento uniforme en toda la aplicación
3. **Eliminación de duplicación**: Toda la lógica de validación en un solo lugar
4. **Mejora de mantenibilidad**: Cambios futuros solo requieren modificar un punto
5. **Flexibilidad**: Fácil de extender para incluir nuevos tipos de contexto

## Ejemplos de Migración

### Antes:

```python
async def get_documents():
    tenant_id = get_required_tenant_id()
    # Usar tenant_id...
```

### Después:

```python
@with_context(tenant=True)
async def get_documents(ctx):
    tenant_id = ctx.get_tenant_id()
    # Usar tenant_id...
```

## Conclusión

El nuevo sistema unificado simplifica enormemente el manejo del contexto multitenancy, proporcionando un enfoque claro, consistente y fácil de usar. La migración gradual al nuevo sistema mejorará la calidad y mantenibilidad del código, reduciendo la confusión y los errores relacionados con el contexto.

# Gestión de Contexto Multitenancy

## 1. Introducción

Este documento describe la implementación del sistema de gestión de contexto multitenancy en la plataforma. 
La arquitectura está diseñada para proporcionar una forma unificada y centralizada de manejar el contexto de tenant
a través de toda la aplicación.

## 2. Sistema de Contexto Unificado

Hemos implementado un sistema de contexto unificado basado en un único decorador `@with_context` que gestiona
consistentemente todos los aspectos del contexto (tenant, agent, conversation, collection).

### 2.1 Componentes principales

- **Context**: Clase que encapsula y valida el contexto
- **@with_context**: Decorador que propaga y valida el contexto automáticamente

### 2.2 Uso del decorador @with_context

El decorador `@with_context` es la pieza central de nuestro sistema y permite:

```python
@with_context(tenant=True, agent=False, conversation=False, collection=False, validate_tenant=True)
async def my_function(request, ctx):
    # ctx.get_tenant_id() ya realiza la validación automáticamente
    tenant_id = ctx.get_tenant_id()
    
    # También se puede acceder a otros contextos
    agent_id = ctx.get_agent_id()  # Si agent=True
    
    # Resto de la lógica...
```

### 2.3 Métodos del contexto

La clase `Context` proporciona métodos para acceder a las diferentes variables de contexto:

```python
# Siempre validará el tenant si validate_tenant=True en el decorador
tenant_id = ctx.get_tenant_id()

# Otros métodos para acceder al contexto
agent_id = ctx.get_agent_id()
conversation_id = ctx.get_conversation_id()
collection_id = ctx.get_collection_id()
```

## 3. Casos de uso comunes

### 3.1 Endpoints protegidos (requieren tenant válido)

```python
@with_context(tenant=True)  # validate_tenant=True por defecto
async def protected_endpoint(request, ctx):
    # Obtener y validar tenant_id automáticamente
    tenant_id = ctx.get_tenant_id()
    
    # Si llegamos aquí, tenant_id es válido
    return {"data": f"Datos para tenant {tenant_id}"}
```

### 3.2 Endpoints públicos (sin validación)

```python
@with_context(tenant=True, validate_tenant=False)
async def public_endpoint(request, ctx):
    # Obtener tenant_id sin validación
    tenant_id = ctx.get_tenant_id()  # Puede ser None o "default"
    
    if tenant_id and tenant_id != "default":
        # Lógica para tenant específico
        pass
    else:
        # Lógica para acceso público
        pass
```

### 3.3 Servicios internos con validación explícita

```python
@with_context(tenant=True, validate_tenant=True)
async def internal_service(tenant_override=None, ctx=None):
    # Se puede proporcionar un tenant_id explícito que anula el contexto
    tenant_id = tenant_override or ctx.get_tenant_id()
    
    # Si llegamos aquí, tenant_id es válido
    return tenant_id
```

## 4. Gestión de errores 

### 4.1 Errores de contexto

Si `validate_tenant=True` y no hay un tenant válido, se lanzará:

```python
ServiceError(
    message="Se requiere un tenant válido para esta operación",
    error_code=ErrorCode.TENANT_REQUIRED,
    status_code=400
)
```

### 4.2 Captura y manejo de errores

Es recomendable utilizar bloques try/except para manejar errores de contexto:

```python
try:
    tenant_id = ctx.get_tenant_id()
    # Operaciones con el tenant
except ServiceError as e:
    # Manejo específico del error
    logger.error(f"Error de contexto: {e.message}", extra={"tenant_id": e.context.get("tenant_id")})
    raise  # Re-lanzar o manejar apropiadamente
```

## 5. Compatibilidad con código existente

Para mantener compatibilidad con código existente, se mantienen alias para las funciones antiguas que redirigen al nuevo sistema:

- `get_required_tenant_id()` - Redirige a `Context` con validación
- `validate_tenant_context()` - Redirige a `Context` con validación

Sin embargo, **estas funciones están marcadas como obsoletas** y se recomienda migrar al nuevo sistema usando el decorador `@with_context`.

## 6. Migración desde el sistema anterior

### 6.1 Pasos de migración

1. Identificar funciones que usan `get_required_tenant_id()` o `validate_tenant_context()`
2. Reemplazar con el decorador `@with_context(tenant=True)`
3. Usar `ctx.get_tenant_id()` dentro de la función decorada

### 6.2 Ejemplo de migración

Antes:
```python
from common.context.vars import get_required_tenant_id

async def my_function(request):
    tenant_id = get_required_tenant_id()
    # Resto de la lógica...
```

Después:
```python
from common.context import with_context

@with_context(tenant=True)
async def my_function(request, ctx):
    tenant_id = ctx.get_tenant_id()
    # Resto de la lógica...
```

## 7. Buenas prácticas

1. **Centralizar la validación**: Usar siempre el decorador `@with_context` para la validación del tenant
2. **Documentar los requisitos**: Especificar en la documentación qué funciones requieren un tenant válido
3. **Logs contextuales**: Incluir el tenant_id en los logs para facilitar el diagnóstico
4. **Coherencia en validación**: Decidir temprano en el pipeline si se necesita validación

## 8. Implementación técnica

### 8.1 Detalles de implementación

El sistema utiliza `contextvars` de Python para mantener el contexto en ambientes asíncronos:

```python
current_tenant_id = ContextVar('current_tenant_id', default=None)
```

Y el decorador `@with_context` implementa la lógica de propagación:

```python
def with_context(...):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Crear contexto
            ctx = Context(validate_tenant=validate_tenant)
            
            # Añadimos el contexto como parámetro
            kwargs['ctx'] = ctx
            
            # Ejecutar función
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### 8.2 Validación de tenant

La validación actual considera inválidos:
- Tenant ID igual a `None`
- Tenant ID igual a `"default"`
- Tenant ID con formato inválido

## 9. Conclusión

El sistema unificado de contexto simplifica enormemente la gestión del contexto multitenancy, proporcionando un único mecanismo para propagación y validación. 

Al centralizar esta lógica, evitamos duplicaciones y garantizamos un comportamiento consistente en toda la aplicación.
