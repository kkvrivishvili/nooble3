# Estándares para Manejo de Contexto Multi-tenant en Nooble3

Este documento define los estándares para el manejo del contexto multi-tenant en todos los servicios de la plataforma Nooble3.

## Introducción

El contexto multi-tenant permite propagar la información del tenant actual, agente, conversación y colección a través de las llamadas asíncronas. Es esencial utilizarlo de manera consistente para garantizar que las operaciones se realicen en el contexto correcto.

## Principios Generales

1. **Consistencia**: Todas las funciones que necesiten contexto deben obtenerlo de la misma manera
2. **Explícito sobre implícito**: Preferir pasar el contexto explícitamente cuando sea posible
3. **Propagación adecuada**: Asegurar que el contexto se propague correctamente en operaciones asíncronas

## Uso del Contexto en Endpoints

Todos los endpoints que requieran contexto deben utilizar el decorador `@with_context`:

```python
from common.context.decorators import with_context
from fastapi import APIRouter, Depends
from common.auth import verify_tenant
from common.models import TenantInfo

router = APIRouter()

@router.post("/mi-endpoint")
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True)
async def mi_endpoint(
    request: SomeRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    # El contexto ya está establecido y se puede acceder mediante get_current_*
    tenant_id = get_current_tenant_id()
    agent_id = get_current_agent_id()
    # ... resto del código
```

## Acceso al Contexto

Para acceder al contexto, utiliza las funciones proporcionadas en `common.context.vars`:

```python
from common.context.vars import (
    get_current_tenant_id,
    get_current_agent_id,
    get_current_conversation_id,
    get_current_collection_id
)

# En funciones
async def mi_funcion():
    tenant_id = get_current_tenant_id()
    # Usar tenant_id
```

## Establecimiento Explícito del Contexto

Para establecer el contexto manualmente en un bloque de código, utiliza el administrador de contexto `Context`:

```python
from common.context.decorators import Context

async def mi_funcion(tenant_id: str):
    # Operaciones sin contexto
    
    async with Context(tenant_id=tenant_id, agent_id="some_agent"):
        # Operaciones con contexto
        result = await function_that_needs_context()
    
    # El contexto anterior se restaura automáticamente
```

## Propagación de Contexto en Operaciones Asíncronas

Para trabajos en segundo plano que necesitan contexto:

```python
from common.context.vars import get_full_context

# Capturar el contexto antes de lanzar la tarea
context = get_full_context()

# Pasar el contexto explícitamente a la tarea
await background_task(data, context=context)

# En la función de tarea:
async def background_task(data, context: dict):
    async with Context(**context):
        # El contexto está disponible aquí
        pass
```

## Cuándo Usar Cada Enfoque

1. **Decorador `@with_context`**: Para endpoints de API y funciones que son punto de entrada desde la web
2. **Administrador de contexto `Context`**: Para bloques específicos de código que necesitan un contexto temporal
3. **Funciones `get_current_*`**: Para obtener valores de contexto en cualquier punto

## Validación de Tenant

Para asegurarse de que hay un tenant válido:

```python
from common.context.vars import get_required_tenant_id

# Esta función lanzará error si no hay tenant o si es "default"
tenant_id = get_required_tenant_id()
```

## Buenas Prácticas

1. **No mezclar enfoques**: Decide un enfoque para cada servicio y úsalo consistentemente
2. **Documentar el contexto requerido**: Incluir en los docstrings qué valores de contexto requiere la función
3. **Verificar el contexto temprano**: Validar la presencia del contexto requerido al principio de una función
4. **Establecer valores por defecto seguros**: Si una función puede funcionar con un valor por defecto, proporciónalo

## Adaptación a Servicios Existentes

Al adaptar código existente:

1. Identificar puntos de entrada (endpoints, workers)
2. Aplicar `@with_context` a estos puntos
3. Reemplazar accesos directos con llamadas a `get_current_*`
4. Verificar la propagación en operaciones asíncronas

## Errores Comunes a Evitar

1. Acceder al contexto sin asegurarse de que esté establecido
2. Olvidar restaurar el contexto anterior después de modificarlo
3. Establecer el contexto manualmente en lugar de usar los decoradores/administradores
4. No propagar el contexto en tareas asíncronas o trabajos en segundo plano
