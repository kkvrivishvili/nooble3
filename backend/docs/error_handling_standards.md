# Estándares de Manejo de Errores en Nooble3

Este documento define los estándares para el manejo de errores en todos los servicios de la plataforma Nooble3.

## Principios Generales

1. **Consistencia**: Todos los servicios deben manejar los errores de manera uniforme
2. **Trazabilidad**: Los errores deben ser fácilmente rastreables mediante logs estructurados
3. **Información útil**: Los mensajes de error deben ser informativos tanto para los usuarios como para los desarrolladores
4. **Seguridad**: No exponer información sensible en los errores

## Clases de Errores

Todas las excepciones personalizadas deben extender de `ServiceError`:

```python
from common.errors.exceptions import ServiceError, ErrorCode

# Ejemplo de excepción personalizada
class MiExcepcionPersonalizada(ServiceError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.MI_ERROR_PERSONALIZADO,
            details=details
        )
```

## Decoradores de Manejo de Errores

Todos los endpoints de API deben utilizar el decorador unificado de manejo de errores:

```python
from common.errors import handle_errors

@router.post("/mi-endpoint")
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def mi_endpoint():
    # Tu código aquí
    pass
```

### Variantes del Decorador `handle_errors`

El decorador `handle_errors` es parametrizable y admite diferentes configuraciones según el caso de uso:

1. **Para endpoints públicos**:
```python
@handle_errors(error_type="simple", log_traceback=False)
```

2. **Para servicios internos**:
```python
@handle_errors(error_type="service", log_traceback=True)
```

3. **Para funciones de configuración**:
```python
@handle_errors(error_type="config")
```

4. **Con mapeo personalizado de excepciones**:
```python
@handle_errors(
    error_type="service",
    error_map={
        ValueError: ("VALIDATION_ERROR", 422),
        KeyError: ("NOT_FOUND", 404)
    }
)
```

## Logging de Errores

Utiliza siempre el módulo centralizado de logging:

```python
from common.utils.logging import get_logger

logger = get_logger(__name__)

try:
    # Operación que puede fallar
    pass
except Exception as e:
    logger.error(f"Error en operación: {str(e)}", exc_info=True)
    raise ServiceError(message="Mensaje para el usuario", error_code="CODIGO_ERROR")
```

## Manejo de Errores en Servicios Externos

Para APIs externas:

```python
try:
    response = await external_api_call()
except Exception as e:
    logger.error(f"Error llamando a API externa: {str(e)}")
    raise ExternalServiceError(
        message="Error al comunicarse con servicio externo",
        details={"service": "nombre_servicio"}
    )
```

## Respuestas de Error Estandarizadas

Utiliza las funciones de utilidad para crear respuestas consistentes:

```python
from common.errors.responses import create_error_response

# En un endpoint que no usa el decorador
return create_error_response(
    message="Recurso no encontrado",
    error_code="NOT_FOUND",
    status_code=404
)
```

## Códigos de Error

Utiliza los códigos de error predefinidos en `ErrorCode` siempre que sea posible para mantener consistencia.

## Estandarización de Respuestas

Todas las respuestas de error deben seguir este formato:

```json
{
  "success": false,
  "error": "ERROR_CODE",
  "message": "Mensaje de error para el usuario",
  "details": {
    // Información adicional opcional
  }
}
```

## Inicialización del Manejo de Errores

Todos los servicios deben incluir la configuración de manejo de errores en su inicialización:

```python
from common.errors import setup_error_handling

def create_app():
    app = FastAPI()
    # ...
    setup_error_handling(app)
    # ...
    return app
