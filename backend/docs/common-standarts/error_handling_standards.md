# Estándares de Manejo de Errores

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Arquitectura de Errores](#2-arquitectura-de-errores)
3. [Estructura de Códigos de Error](#3-estructura-de-códigos-de-error)
4. [Excepciones Estandarizadas](#4-excepciones-estandarizadas)
5. [Respuestas de Error HTTP](#5-respuestas-de-error-http)
6. [Consistencia entre Servicios](#6-consistencia-entre-servicios)
7. [Gestión de Errores en Comunicación Asíncrona](#7-gestión-de-errores-en-comunicación-asíncrona)
8. [Implementación en Servicios](#8-implementación-en-servicios)

## 1. Introducción

Este documento establece los estándares para el manejo de errores en todos los microservicios de la plataforma Nooble AI. El objetivo es garantizar la consistencia en la gestión, propagación y comunicación de errores entre servicios, facilitando el diagnóstico y la resolución de problemas.

### 1.1 Principios Generales

- **Consistencia**: Formato y códigos uniformes en todos los servicios
- **Trazabilidad**: Información suficiente para seguir errores entre servicios
- **Especificidad**: Errores específicos para casos de uso concretos
- **Extensibilidad**: Capacidad para que cada servicio defina errores propios
- **Seguridad**: Prevención de filtrado de información sensible en errores

## 2. Arquitectura de Errores

La arquitectura se basa en tres componentes principales:

### 2.1 Componentes Centrales

```
backend/
├── common/
│   └── errors/              # Paquete común de errores
│       ├── __init__.py      # Exporta todas las excepciones
│       ├── exceptions.py    # Excepciones base y comunes
│       ├── handlers.py      # Manejadores de errores
│       └── responses.py     # Formateo de respuestas
├── services/
│   ├── service1/
│   │   └── errors/          # Errores específicos del servicio
│   │       └── exceptions.py
│   └── service2/
│       └── errors/
│           └── exceptions.py
```

### 2.2 Flujo de Manejo de Errores

1. Se produce una excepción en código específico de servicio
2. La excepción se convierte a una excepción tipada (`ServiceError` o derivada)
3. El manejador global captura la excepción
4. Se registra la excepción en logs (con nivel apropiado)
5. Se convierte la excepción a una respuesta HTTP con formato estandarizado
6. Se envía la respuesta al cliente con estado HTTP apropiado

## 3. Estructura de Códigos de Error

Los códigos de error siguen la siguiente convención:

### 3.1 Rangos de Códigos

| Rango | Categoría | Propósito |
|-------|-----------|-----------|
| 1000-1999 | General | Errores generales de la plataforma |
| 2000-2999 | Autenticación y Autorización | Errores relacionados con permisos |
| 3000-3999 | Límites y Cuotas | Errores de rate limits y cuotas |
| 4000-4999 | Servicios Externos | Errores de comunicación externa |
| 5000-5999 | LLM | Errores específicos de modelos de lenguaje |
| 6000-6999 | Datos | Errores de manejo de datos y almacenamiento |
| 7000-7999 | Agentes | Errores específicos de agentes |
| 8000-8999 | RAG/Consultas | Errores de procesamiento de consultas |
| 9000-9999 | Embeddings | Errores de generación de embeddings |

### 3.2 Convención de Nombres para ErrorCode

Los nombres de los códigos de error siguen estas reglas:

- Usar mayúsculas y guiones bajos (SNAKE_CASE)
- Formato claro y descriptivo (ej: `RESOURCE_NOT_FOUND`)
- Prefijo específico del servicio para errores personalizados

**Ejemplos comunes:**
- `VALIDATION_ERROR`
- `PERMISSION_DENIED`
- `RESOURCE_NOT_FOUND`

**Ejemplos específicos de servicios:**
- `WFLOW_DEFINITION_INVALID` (Workflow Engine)
- `EMBD_MODEL_UNAVAILABLE` (Embedding Service)
- `TOOL_EXECUTION_TIMEOUT` (Tool Registry)

## 4. Excepciones Estandarizadas

### 4.1 Excepción Base

Todos los servicios utilizan la misma clase base `ServiceError` definida en `backend/common/errors/exceptions.py`:

```python
class ServiceError(Exception):
    """Excepción centralizada para todos los errores de servicio."""
    
    def __init__(
        self, 
        message: str, 
        error_code: ErrorCode = ErrorCode.GENERAL_ERROR,
        status_code: Optional[int] = None, 
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        # Implementación...
```

### 4.2 Excepciones Comunes

Todas las excepciones derivadas deben mantener la misma firma y estilo de inicialización:

```python
class ValidationError(ServiceError):
    """Error de validación."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            details=details
        )
```

### 4.3 Excepciones Específicas de Servicios

Cada servicio debe definir sus excepciones específicas extendiendo `ServiceError` o una de sus subclases comunes.

**Para servicios existentes:**

```python
# En workflow_engine/errors/exceptions.py
from common.errors.exceptions import ServiceError, ErrorCode

class WorkflowDefinitionError(ServiceError):
    """Error en la definición de un workflow."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="WFLOW_DEFINITION_INVALID",
            status_code=400,
            details=details
        )
```

## 5. Respuestas de Error HTTP

### 5.1 Formato Estándar

Todas las respuestas de error deben seguir este formato:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "El recurso solicitado no existe",
    "details": {
      "resource_id": "123",
      "resource_type": "agent"
    },
    "request_id": "uuid-request",
    "timestamp": "2025-06-03T12:34:56Z"
  }
}
```

### 5.2 Campos Obligatorios

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| code | Código identificador del error | "RESOURCE_NOT_FOUND" |
| message | Mensaje descriptivo para humanos | "El recurso solicitado no existe" |
| request_id | Identificador único de solicitud | "3fa85f64-5717-4562-b3fc-2c963f66afa6" |
| timestamp | Momento del error en ISO-8601 | "2025-06-03T12:34:56Z" |

### 5.3 Campos Opcionales

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| details | Detalles adicionales del error | {"resource_id": "123", "resource_type": "agent"} |
| trace_id | ID para correlación entre servicios | "trace-uuid-123" |
| suggestion | Sugerencia para resolver el problema | "Verifique que el ID proporcionado sea correcto" |

### 5.4 Mapeo de Estados HTTP

| Categoría de Error | Estado HTTP | Ejemplo |
|--------------------|-------------|---------|
| Validación | 400 (Bad Request) | Datos de entrada incorrectos |
| Autenticación | 401 (Unauthorized) | Token no proporcionado |
| Autorización | 403 (Forbidden) | Permisos insuficientes |
| No encontrado | 404 (Not Found) | Recurso inexistente |
| Límites | 429 (Too Many Requests) | Rate limit excedido |
| Error interno | 500 (Internal Server Error) | Error no manejado |
| Servicio externo | 502/503 (Bad Gateway/Service Unavailable) | API externa caída |

## 6. Consistencia entre Servicios

### 6.1 Errores Compartidos

Ciertos errores son comunes a todos los servicios y deben tener el mismo comportamiento:

| Error | Código | Estado HTTP | Uso |
|-------|--------|-------------|-----|
| ValidationError | VALIDATION_ERROR | 400 | Datos de entrada inválidos |
| ResourceNotFoundError | RESOURCE_NOT_FOUND | 404 | Recurso no encontrado |
| AuthenticationError | AUTHENTICATION_FAILED | 401 | Problemas de autenticación |
| PermissionError | PERMISSION_DENIED | 403 | Falta de permisos |
| RateLimitError | RATE_LIMITED | 429 | Límite de tasa excedido |

### 6.2 Errores Personalizados

Los servicios pueden definir errores específicos siguiendo estas convenciones:

1. Usar un prefijo de 2-5 letras identificativo del servicio
2. Mantener el resto del nombre descriptivo y en SNAKE_CASE
3. Documentar los errores específicos

**Ejemplos:**

| Servicio | Prefijo | Ejemplo Código | Descripción |
|----------|---------|----------------|-------------|
| Workflow Engine | WFLOW | WFLOW_INVALID_TRANSITION | Transición de estado inválida |
| Query Service | QRYS | QRYS_VECTOR_DB_ERROR | Error en base de datos vectorial |
| Embedding Service | EMBD | EMBD_TOKEN_LIMIT | Límite de tokens excedido |
| Tool Registry | TOOL | TOOL_EXECUTION_FAILED | Fallo en ejecución de herramienta |

## 7. Gestión de Errores en Comunicación Asíncrona

### 7.1 Estructura de Mensajes de Error

Los mensajes de error en colas y eventos asíncronos deben incluir:

```json
{
  "message_id": "msg-uuid",
  "timestamp": "2025-06-03T12:34:56Z",
  "version": "1.0",
  "source": "service-name",
  "destination": "service-name",
  "correlation_id": "corr-uuid",
  "session_id": "session-uuid",
  "error": {
    "code": "ERROR_CODE",
    "message": "Descripción del error",
    "details": {
      "campo_específico": "valor"
    }
  }
}
```

### 7.2 Propagación de Errores

Para la propagación de errores entre servicios:

1. Incluir siempre `correlation_id` para trazabilidad
2. Mantener información contextual relevante en `details`
3. No incluir información sensible o stack traces
4. Usar canales dedicados para notificación de errores

## 8. Implementación en Servicios

### 8.1 Pasos de Integración

Cada servicio debe:

1. Importar las excepciones base de `common.errors`
2. Definir excepciones específicas cuando sea necesario
3. Configurar la captura global de excepciones al inicio
4. Usar manejadores consistentes de FastAPI

### 8.2 Integración con FastAPI

```python
from fastapi import FastAPI, Request
from common.errors.handlers import setup_error_handling

app = FastAPI()

# Configurar manejo de errores global
setup_error_handling(app)

# Rutas y lógica del servicio...
```

### 8.3 Ejemplo de Uso en Servicios

```python
from common.errors import ValidationError, ResourceNotFoundError
from service.errors import CustomServiceError

@app.get("/resources/{resource_id}")
async def get_resource(resource_id: str):
    # Validación de entrada
    if not validate_resource_id(resource_id):
        raise ValidationError(f"ID de recurso inválido: {resource_id}")
    
    # Búsqueda de recursos
    resource = await find_resource(resource_id)
    if not resource:
        raise ResourceNotFoundError(f"Recurso no encontrado con ID: {resource_id}")
    
    # Lógica específica del servicio
    if resource.has_problem():
        raise CustomServiceError(f"Problema específico del servicio", details={"resource": resource.id})
    
    return resource.to_dict()
```
