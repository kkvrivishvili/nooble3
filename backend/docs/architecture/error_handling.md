# Manejo Unificado de Errores

## Visión General

Este documento describe el sistema unificado de manejo de errores implementado en nuestra plataforma. El sistema está diseñado para proporcionar un enfoque consistente y centralizado para el manejo de errores en todos los servicios backend.

## Decorador Unificado `@handle_errors`

Hemos consolidado todos los decoradores anteriores (`handle_errors`, `handle_service_error`, `handle_service_error_simple`, `handle_config_error`) en un único decorador parametrizable: `@handle_errors`.

### Características Principales

- **Unificación**: Un solo decorador para todos los casos de uso
- **Parametrización**: Totalmente configurable mediante parámetros
- **Contexto enriquecido**: Captura automática del contexto de ejecución
- **Logging estructurado**: Registros consistentes con metadatos

### Parámetros del Decorador

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `error_type` | `str` | Tipo de errores a manejar: `'service'` (predeterminado), `'config'` o `'simple'` |
| `error_map` | `Dict` | Mapeo de tipos de excepción a tuplas `(error_code, status_code)` |
| `convert_exceptions` | `bool` | Si es `True`, convierte excepciones en `ServiceError` |
| `log_traceback` | `bool` | Si es `True`, registra el traceback completo en los logs |
| `ignore_exceptions` | `List` | Lista de excepciones que no deben ser capturadas |
| `on_error_response` | `Dict` | Respuesta personalizada opcional para casos de error |

## Casos de Uso

### 1. Errores de Servicio Estándar

```python
@handle_errors(error_map={
    ValueError: ("VALIDATION_ERROR", 422),
    KeyError: ("NOT_FOUND", 404)
})
async def process_data(data):
    # Función que puede lanzar excepciones
    # Cualquier excepción será convertida a ServiceError con código apropiado
```

### 2. Errores de Configuración

```python
@handle_errors(error_type="config")
async def load_settings():
    # Función que maneja configuraciones
    # Las excepciones serán convertidas a ConfigurationError
```

### 3. Manejo Simple de Errores

```python
@handle_errors(error_type="simple", log_traceback=False)
async def simple_operation():
    # Función con manejo básico de errores
    # Sin logging de traceback completo
```

### 4. Personalización Avanzada

```python
@handle_errors(
    error_map={
        DatabaseError: ("DATABASE_ERROR", 503),
        IOError: ("IO_ERROR", 500)
    },
    ignore_exceptions=[AuthenticationError],  # No capturar estos errores
    log_traceback=True,
    convert_exceptions=True
)
async def complex_operation():
    # Operación con manejo personalizado de errores
```

## Compatibilidad con Código Existente

Para mantener la compatibilidad con el código existente, se proporcionan alias para los decoradores anteriores:

```python
# Los siguientes decoradores se mantienen por compatibilidad
# pero eventualmente serán eliminados
handle_service_error = handle_errors
handle_service_error_simple = lambda func: handle_errors(error_type="simple", log_traceback=False)(func)
handle_config_error = lambda func: handle_errors(error_type="config")(func)
```

## Buenas Prácticas

### 1. Mapeado Explícito de Excepciones

Siempre que sea posible, define un `error_map` explícito para mapear tipos de excepciones específicas a códigos de error:

```python
@handle_errors(error_map={
    ValueError: ("VALIDATION_ERROR", 422),
    KeyError: ("NOT_FOUND", 404),
    PermissionError: ("PERMISSION_DENIED", 403)
})
```

### 2. Contexto Enriquecido

El decorador captura automáticamente el contexto (tenant_id, agent_id, etc.), pero puedes enriquecerlo con información adicional:

```python
try:
    # Operación que puede fallar
except Exception as e:
    # Añadir contexto específico
    e.context = {"operation_id": operation_id, "resource": resource_name}
    raise
```

### 3. Logging Consistente

El sistema garantiza logging consistente con metadatos relevantes:

```python
# El error se registrará así:
# ERROR: Error en process_data [tenant_id='t123', function='process_data']: Recurso no encontrado
```

### 4. Gestión de Errores en Endpoints

Para endpoints FastAPI, combina con el manejador global:

```python
# En main.py
from common.errors.handlers import setup_error_handling

app = FastAPI()
setup_error_handling(app)  # Configura manejadores globales
```

## Migración desde el Sistema Anterior

Para migrar desde los decoradores anteriores:

1. **handle_service_error** → `@handle_errors()`
2. **handle_service_error_simple** → `@handle_errors(error_type="simple", log_traceback=False)`
3. **handle_config_error** → `@handle_errors(error_type="config")`

## Conclusión

El nuevo sistema unificado de manejo de errores simplifica la gestión de errores proporcionando un único punto de entrada configurable. Esta aproximación mejora la consistencia, facilita el mantenimiento y reduce la duplicación de código en nuestra plataforma.
