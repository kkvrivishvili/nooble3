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

### 1. Función Centralizada de Validación

Se implementó una función centralizada en `common/context/vars.py`:

```python
def validate_tenant_context(tenant_id: str) -> str:
    """
    Valida que el tenant_id del contexto sea válido y no sea el valor por defecto.
    
    Args:
        tenant_id: ID del tenant a validar
        
    Returns:
        str: El tenant_id validado
        
    Raises:
        ServiceError: Si el tenant_id no es válido o es el valor por defecto
    """
    if not tenant_id or tenant_id == "default":
        # Crear un contexto de error enriquecido siguiendo los estándares
        error_context = {
            "tenant_id": tenant_id,
            "context": get_full_context(),
            "service": "unknown"
        }
        
        # Intentar obtener el nombre del servicio para enriquecer el contexto
        try:
            from ..config.settings import get_settings
            settings = get_settings()
            error_context["service"] = getattr(settings, "service_name", "unknown")
        except (ImportError, AttributeError):
            pass
            
        logger.error("Intento de acceso con tenant_id inválido o default", extra=error_context)
        
        from ..errors.exceptions import ServiceError, ErrorCode
        raise ServiceError(
            message="Se requiere un tenant válido para esta operación",
            error_code=ErrorCode.TENANT_REQUIRED.value,
            status_code=403,
            context=error_context
        )
        
    return tenant_id
```

### 2. Modificación de la Función `get_required_tenant_id()`

```python
def get_required_tenant_id() -> str:
    """
    Obtiene el ID del tenant actual, exigiendo que exista uno válido.
    
    Returns:
        str: ID del tenant
        
    Raises:
        ServiceError: Si no hay un tenant_id válido en el contexto
    """
    tenant_id = get_current_tenant_id()
    
    # Usar la función validate_tenant_context para verificar de manera consistente
    return validate_tenant_context(tenant_id)
```

### 3. Servicios Actualizados

#### Base de Datos (tables.py)
- Se actualizaron las funciones que interactúan con la base de datos para validar el tenant_id antes de acceder a recursos específicos de tenant.

#### Query Engine (query_engine.py)
- Se validó el tenant_id antes de procesar consultas para asegurar que solo tenants válidos puedan acceder a las colecciones.

#### Embeddings (embedding_provider.py)
- Se mejoró la validación de tenant_id en el proveedor de embeddings para evitar la generación de embeddings sin un tenant válido.

#### Cola de Ingesta (queue.py)
- Se implementó la validación de tenant_id antes de procesar trabajos de ingesta.

## Mejores Prácticas

1. **Validación Explícita**: Siempre validar tenant_id explícitamente usando `validate_tenant_context()` o `get_required_tenant_id()`.

2. **Manejo de Errores Consistente**:
   - Usar `ServiceError` con códigos de error apropiados
   - Incluir contexto enriquecido con información del tenant y servicio
   - Asegurar un nivel de logging apropiado (error para fallas de validación)

3. **Documentación Clara**:
   - Documentar todas las funciones con docstrings completos
   - Especificar claramente la posibilidad de `ServiceError` para indicar problemas de tenant

4. **Tipado**:
   - Utilizar tipado para hacer explícito cuando se requiere un tenant vs cuando es opcional

## Impacto

- **Seguridad Mejorada**: Validación consistente del acceso basado en tenant
- **Mejor Depuración**: Errores más claros y contexto enriquecido
- **Mantenibilidad**: Función centralizada para facilitar cambios futuros
- **Experiencia del Usuario**: Errores más claros para problemas de autorización

## Siguientes Pasos

1. Continuar auditando el código para identificar cualquier uso de `get_current_tenant_id()` sin la validación adecuada
2. Considerar agregar tests automáticos para validar el comportamiento correcto
3. Evaluar agregar validación similar para otros elementos de contexto (agent_id, collection_id, etc.)
