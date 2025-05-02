# Estándar de Manejo de Errores

**Tags:** `#error_handling` `#standards` `#backend` `#fastapi` `#exceptions` `#logging` `#security`

## 1. Principios Fundamentales

**Tags:** `#principles` `#core_concepts`

Siguiendo los principios establecidos:

1. **Consistencia**: Todos los servicios deben manejar los errores de manera uniforme
2. **Trazabilidad**: Los errores deben ser fácilmente rastreables mediante logs estructurados
3. **Información útil**: Los mensajes de error deben ser informativos tanto para los usuarios como para los desarrolladores
4. **Seguridad**: No exponer información sensible en los errores
5. **Single Point of Implementation**: Un único decorador parametrizable para todos los escenarios

## 3. Arquitectura e Implementación

**Tags:** `#architecture` `#implementation` `#structure`

### 3.1 Estructura de Archivos

```
common/errors/
├── __init__.py      # Exporta todas las excepciones y funciones
├── exceptions.py    # Define ServiceError, ErrorCode y excepciones específicas
├── handlers.py      # Implementa @handle_errors y setup_error_handling
└── responses.py     # Utilidades para respuestas estandarizadas
```

### 3.2 Importaciones Correctas

**Tags:** `#imports` `#best_practices`

```python
# ✅ CORRECTO - Importar desde el módulo principal
from common.errors import (
    ServiceError, ErrorCode, handle_errors, 
    setup_error_handling, create_error_response
)

# ❌ INCORRECTO - No importar desde submódulos internos
from common.errors.exceptions import ServiceError  # Evitar
```

### 3.3 Inicialización en Servicios

**Tags:** `#initialization` `#app_setup` `#fastapi`

```python
from fastapi import FastAPI
from common.errors import setup_error_handling

def create_app():
    app = FastAPI()
    
    # Configurar manejadores de error globales
    setup_error_handling(app)
    
    # Resto de la configuración...
    return app
```

La función `setup_error_handling` registra manejadores para:
- `ServiceError` y sus subclases
- `HTTPException` y `StarletteHTTPException`
- `RequestValidationError` y `ValidationError` de Pydantic
- `Exception` (captura genérica para errores no manejados)

También añade un middleware para logging de peticiones y respuestas.

## 4. Decorador Parametrizable `@handle_errors`

**Tags:** `#decorator` `#error_handling` `#parameters`

### 4.1 Patrones Estandarizados de Uso

**Tags:** `#patterns` `#examples` `#usage`

```python
# 1. Para endpoints básicos/públicos
@router.post("/endpoint")
@with_context(tenant=True)
@handle_errors(error_type="simple", log_traceback=False)
async def endpoint_basico():
    # Implementación...

# 2. Para servicios internos/críticos
@router.post("/internal/servicio")
@with_context(tenant=True)
@handle_errors(
    error_type="service", 
    log_traceback=True, 
    error_map={
        ValueError: ("VALIDATION_ERROR", 422),
        KeyError: ("NOT_FOUND", 404)
    }
)
async def servicio_interno():
    # Implementación...

# 3. Para funciones de configuración
@handle_errors(error_type="config")
async def cargar_configuracion():
    # Implementación...
```

### 4.2 Parámetros del Decorador

**Tags:** `#parameters` `#configuration` `#api`

```python
@handle_errors(
    error_type="service",              # "service", "config" o "simple"
    error_map={ValueError: ("VALIDATION_ERROR", 422)},  # Mapeo personalizado
    convert_exceptions=True,           # Convertir excepciones a ServiceError
    log_traceback=True,                # Loggear traceback completo
    ignore_exceptions=[KeyboardInterrupt]  # Excepciones a ignorar
)
```

| Parámetro | Descripción | Valores |
|-----------|-------------|---------|
| `error_type` | Tipo de manejo de errores | "service", "config", "simple" |
| `error_map` | Mapeo de excepciones a códigos y status | `{ExcType: (error_code, status_code)}` |
| `convert_exceptions` | Convertir excepciones a `ServiceError` | `True`, `False` |
| `log_traceback` | Incluir traceback completo en logs | `True`, `False` |
| `ignore_exceptions` | Excepciones que no se deben capturar | `[ExcType1, ExcType2]` |

### 4.3 Comportamiento según `error_type`

**Tags:** `#behavior` `#error_types` `#configuration`

El decorador se comporta diferente según el valor de `error_type`:

- **"service"**: Para servicios core, registra logs detallados y proporciona contexto completo
- **"config"**: Para funciones de configuración, maneja específicamente errores como `KeyError` (configuración faltante) y `ValueError` (configuración inválida)
- **"simple"**: Para endpoints públicos, con menos detalles en los logs y sin trazas sensibles

## 5. Jerarquía de Excepciones

**Tags:** `#exceptions` `#hierarchy` `#class_structure`

### 5.1 Clase Base `ServiceError`

**Tags:** `#base_class` `#core_exception`

Todas las excepciones personalizadas extienden de `ServiceError`:

```python
from common.errors import ServiceError, ErrorCode

class ServiceError(Exception):
    """
    Excepción centralizada para todos los errores de servicio.
    
    Attributes:
        message: Mensaje descriptivo del error
        error_code: Código estandarizado de error
        status_code: Código HTTP (ej: 404)
        details: Información adicional sobre el error
        context: Información de contexto (tenant_id, etc.)
    """
```

### 5.2 Uso de Excepciones Tipadas

**Tags:** `#typed_exceptions` `#best_practices` `#specific_exceptions`

Siguiendo el enfoque descrito en la documentación original, siempre se debe usar la excepción más específica disponible:

```python
# ❌ EVITAR
raise ServiceError("Documento no encontrado")

# ✅ CORRECTO
from common.errors import ResourceNotFoundError
raise ResourceNotFoundError(
    message="Documento no encontrado", 
    details={"document_id": doc_id}
)
```

### 5.3 Catálogo Completo de Excepciones Disponibles

**Tags:** `#exceptions_catalog` `#reference` `#all_exceptions`

El sistema ofrece excepciones específicas para cada tipo de error, organizadas por categoría:

**Errores generales**:
- `ServiceError` - Base de todas las excepciones
- `ValidationError` - Datos inválidos
- `ResourceNotFoundError` - Recurso no encontrado

**Autenticación y autorización**:
- `AuthenticationError` - Error de autenticación
- `PermissionError` - Sin permisos para la operación
- `AuthorizationError` - Error de autorización

**Límites y cuotas**:
- `RateLimitError` - Error general de límite de tasa
- `RateLimitExceeded` - Límite de tasa excedido
- `QuotaExceededError` - Cuota excedida

**Servicios externos**:
- `ServiceUnavailableError` - Servicio no disponible
- `ExternalApiError` - Error en API externa
- `CommunicationError` - Error de comunicación
- `TimeoutError` - Tiempo de espera agotado

**Infraestructura**:
- `DatabaseError` - Error de base de datos
- `CacheError` - Error de caché
- `ConfigurationError` - Error de configuración

**LLM y generación**:
- `LlmGenerationError` - Error generando texto con LLM
- `ModelNotAvailableError` - Modelo no disponible
- `EmbeddingError` - Error con embeddings

**Documentos y colecciones**:
- `DocumentProcessingError` - Error procesando documento
- `CollectionError` - Error con colección
- `ConversationError` - Error con conversación
- `TextTooLargeError` - Texto demasiado grande

**Agentes**:
- `AgentNotFoundError` - Agente no encontrado
- `AgentInactiveError` - Agente inactivo
- `AgentExecutionError` - Error en ejecución de agente
- `AgentSetupError` - Error en configuración de agente
- `AgentToolError` - Error en herramienta de agente
- `AgentLimitExceededError` - Límite de agentes alcanzado
- `InvalidAgentIdError` - ID de agente inválido
- `AgentAlreadyExistsError` - Agente ya existe
- `AgentQuotaExceededError` - Cuota de agentes excedida

**Consultas RAG**:
- `QueryProcessingError` - Error procesando consulta
- `CollectionNotFoundError` - Colección no encontrada
- `RetrievalError` - Error en recuperación
- `GenerationError` - Error en generación de respuesta
- `InvalidQueryParamsError` - Parámetros de consulta inválidos

**Embeddings**:
- `EmbeddingGenerationError` - Error generando embeddings
- `EmbeddingModelError` - Error en modelo de embeddings
- `BatchTooLargeError` - Lote demasiado grande
- `InvalidEmbeddingParamsError` - Parámetros inválidos

### 5.4 Códigos de Error Estandarizados

**Tags:** `#error_codes` `#enum` `#categorization`

El sistema utiliza `ErrorCode` (un enum) para definir códigos de error organizados por categoría:

```python
from common.errors import ErrorCode

# Organización de errores por categorías numéricas:
# - 1xxx: Errores generales 
ErrorCode.GENERAL_ERROR        # "GENERAL_ERROR" (interno: 1000)
ErrorCode.NOT_FOUND            # "NOT_FOUND" (interno: 1001)
ErrorCode.VALIDATION_ERROR     # "VALIDATION_ERROR" (interno: 1002)

# - 2xxx: Errores de autenticación/autorización
ErrorCode.PERMISSION_DENIED    # "PERMISSION_DENIED" (interno: 2000)
ErrorCode.AUTHENTICATION_FAILED # "AUTHENTICATION_FAILED" (interno: 2001)

# - 3xxx: Errores de límites/cuotas
ErrorCode.QUOTA_EXCEEDED       # "QUOTA_EXCEEDED" (interno: 3000)
ErrorCode.RATE_LIMITED         # "RATE_LIMITED" (interno: 3001)
ErrorCode.RATE_LIMIT_EXCEEDED  # "RATE_LIMIT_EXCEEDED" (interno: 3002)

# - 4xxx: Errores de servicios externos
# - 5xxx: Errores específicos de LLM
# - 6xxx: Errores de gestión de datos
# - 7xxx: Errores específicos de agentes
# - 8xxx: Errores específicos de consultas (RAG)
# - 9xxx: Errores específicos de embeddings
```

## 6. Formato de Respuesta de Error

**Tags:** `#response_format` `#json_structure` `#api_response`

### 6.1 Estructura Estándar

**Tags:** `#json_format` `#standard_response` `#structure`

Según lo establecido en la documentación original, todas las respuestas de error siguen esta estructura exacta:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "error_number": 1234,
    "message": "Mensaje descriptivo para el usuario",
    "details": {
      "campo_relevante": "valor"
    },
    "context": {
      "tenant_id": "t123",
      "agent_id": "a456"
    }
  }
}
```

Donde:
- `success`: Siempre `false` para errores
- `error.code`: Código estandarizado (ej: "NOT_FOUND")
- `error.error_number`: Código numérico interno (ej: 1001)
- `error.message`: Mensaje legible para humanos
- `error.details`: Información específica del error
- `error.context`: Contexto relevante (tenant_id, etc.)

### 6.2 Creación Manual de Respuestas de Error

**Tags:** `#manual_response` `#utility_function` `#helper`

Cuando necesites crear manualmente una respuesta de error (sin lanzar excepción):

```python
from common.errors import create_error_response

return create_error_response(
    message="Recurso no encontrado",
    error_code="NOT_FOUND",
    status_code=404,  # Opcional, se infiere del error_code si no se proporciona
    details={"resource_id": resource_id}
)
```

## 7. Integración con Sistema de Contexto

**Tags:** `#context_integration` `#multitenancy` `#context_propagation`

### 7.1 Contexto Automático en Errores

**Tags:** `#auto_context` `#exception_context`

`ServiceError` captura automáticamente el contexto actual:

```python
from ..context.vars import get_full_context
self.context = get_full_context()
```

### 7.2 Información Segura en Respuestas

**Tags:** `#security` `#safe_context` `#data_privacy`

Solo un subconjunto seguro del contexto se incluye en las respuestas HTTP:

```python
safe_context = {
    k: v for k, v in self.context.items()
    if k in ["tenant_id", "agent_id", "collection_id", "conversation_id", "request_id"]
}
```

### 7.3 Orden Correcto de Decoradores

**Tags:** `#decorators_order` `#best_practices` `#implementation`

Siguiendo los estándares establecidos, mantener este orden de decoradores:

```python
@router.method("/ruta")        # 1. Router (FastAPI)
@with_context(tenant=True)     # 2. Contexto
@handle_errors(error_type=...) # 3. Manejo de errores
async def mi_funcion():
    # Implementación
```

## 8. Logging Enriquecido

**Tags:** `#logging` `#structured_logs` `#observability`

### 8.1 Contexto Automático en Logs

**Tags:** `#log_context` `#automatic_enrichment`

El decorador `@handle_errors` añade automáticamente este contexto a los logs:

```python
context.update({
    "function": function_name,  # Nombre de la función
    "module": func.__module__,   # Módulo donde se encuentra
    "args": str(safe_args),      # Argumentos (solo tipos, no valores)
    "kwargs": str(safe_kwargs)   # Kwargs (solo tipos, no valores)
})
```

### 8.2 Niveles Correctos de Logging

**Tags:** `#log_levels` `#severity` `#log_hierarchy`

De acuerdo con los estándares mencionados en la documentación:

```python
# Errores críticos que impiden la operación
logger.error(f"Error en base de datos: {str(e)}", extra=context)

# Condiciones excepcionales que no impiden la operación
logger.warning(f"Datos incompletos: {missing_fields}", extra=context)

# Eventos normales pero significativos
logger.info(f"Operación completada: {op_name}", extra=context)

# Información detallada para debugging
logger.debug(f"Estado intermedio: {state}", extra=context)
```

### 8.3 Metadatos Estructurados

**Tags:** `#log_metadata` `#structured_data` `#extra_context`

Siempre utilizar el parámetro `extra` para pasar el contexto:

```python
logger.error(
    f"Error al procesar documento: {str(e)}", 
    extra={
        "tenant_id": tenant_id,
        "document_id": document_id,
        "operation": "process_document"
    }
)
```

## 9. Seguridad y Sanitización

**Tags:** `#security` `#data_protection` `#sanitization`

### 9.1 Principios de Seguridad

**Tags:** `#security_principles` `#data_privacy` `#sensitive_info`

- **No exponer información interna**: Stacktraces, rutas de archivos, detalles de infraestructura
- **No incluir datos sensibles**: Credenciales, tokens, información personal identificable
- **Mensajes públicos genéricos**: Específicos en logs, genéricos en respuestas

### 9.2 Sanitización de Contenido

**Tags:** `#content_sanitization` `#data_cleaning` `#redaction`

```python
from common.errors.responses import sanitize_content

# Sanitizar contenido potencialmente sensible antes de loggear
sanitized_content = sanitize_content(raw_content)
logger.debug(f"Respuesta recibida: {sanitized_content}")
```

La función `sanitize_content`:
- Elimina credenciales con regex: `api_key="xxx"` → `api_key="[REDACTED]"`
- Elimina caracteres de control (excepto saltos de línea y tabs)
- Trunca contenido muy largo (>100,000 caracteres)

## 10. Errores en Comunicaciones Inter-Servicios

**Tags:** `#service_communication` `#inter_service` `#api_calls`

### 10.1 Llamadas a Servicios Internos

**Tags:** `#internal_services` `#service_calls` `#error_handling`

Según los estándares de "Comunicación entre Servicios":

```python
from common.utils.http import call_service
from common.errors import ExternalApiError

try:
    response = await call_service(
        url=f"{settings.service_url}/endpoint",
        data=payload,
        tenant_id=tenant_id
    )
    
    if not response.get("success", False):
        error_details = response.get("error", {})
        raise ExternalApiError(
            message=f"Error en servicio: {error_details.get('message', 'Error desconocido')}",
            details={"service": "service-name", "error": error_details}
        )
except Exception as e:
    # El decorador @handle_errors capturará y manejará esta excepción
    raise ExternalApiError(
        message=f"Error de comunicación con servicio: {str(e)}",
        details={"service": "service-name"}
    )
```

### 10.2 Errores en APIs Externas

**Tags:** `#external_api` `#third_party` `#error_handling`

```python
from common.errors import ExternalApiError, sanitize_content

try:
    # Llamada a API externa
    async with httpx.AsyncClient() as client:
        response = await client.post(external_api_url, json=payload, timeout=30.0)
        
    if response.status_code != 200:
        raise ExternalApiError(
            message=f"Error en API externa: {response.status_code}",
            details={
                "status_code": response.status_code,
                "service": "nombre-servicio",
                "response": sanitize_content(response.text)
            }
        )
except httpx.RequestError as e:
    raise ExternalApiError(
        message=f"Error de conexión con API externa: {str(e)}",
        details={"service": "nombre-servicio"}
    )
```

## 11. Buenas Prácticas Adicionales

**Tags:** `#best_practices` `#guidelines` `#recommendations`

### 11.1 Mensajes de Error Claros y Útiles

**Tags:** `#error_messages` `#clarity` `#user_experience`

- **Descriptivos**: Explicar qué sucedió, no solo que hubo un error
- **Accionables**: Cuando sea posible, sugerir cómo resolver el problema
- **Sin jerga técnica**: Para errores públicos, usar lenguaje comprensible
- **Consistentes**: Mantener el mismo estilo y formato en toda la aplicación

### 11.2 No Duplicar Manejo de Errores

**Tags:** `#dry_principle` `#code_reuse` `#maintainability`

- **Delegar en el decorador**: Evitar try/except redundantes
- **Centralizar transformaciones**: Usar `error_map` para mapear excepciones
- **Excepciones específicas**: Lanzar la excepción más específica disponible

### 11.3 Testing de Errores

**Tags:** `#testing` `#error_testing` `#quality_assurance`

- **Verificar todos los flujos de error**: No solo los casos exitosos
- **Validar formato de respuestas**: Asegurar consistencia en estructura JSON
- **Comprobar códigos HTTP**: Verificar que se retornan los códigos correctos

## 12. Relación con Otros Sistemas

**Tags:** `#system_integration` `#cross_cutting_concerns`

### 12.1 Rate Limiting

**Tags:** `#rate_limiting` `#quotas` `#throttling`

El sistema de rate limiting debe lanzar excepciones estandarizadas:

```python
from common.errors import RateLimitExceeded

if current_rate > allowed_rate:
    raise RateLimitExceeded(
        message="Has excedido el límite de solicitudes por minuto",
        details={
            "limit": allowed_rate,
            "current": current_rate,
            "reset_in_seconds": reset_time
        }
    )
```

### 12.2 Validación de Contexto Multi-Tenant

**Tags:** `#multitenancy` `#tenant_validation` `#context_validation`

Para errores relacionados con contexto de tenant:

```python
from common.errors import ServiceError, ErrorCode

if not tenant_id or tenant_id == "default":
    raise ServiceError(
        message="Se requiere un tenant válido para esta operación",
        error_code=ErrorCode.TENANT_REQUIRED,
        status_code=400
    )
```

### 12.3 Integración con Sistema de Caché

**Tags:** `#cache` `#redis` `#error_handling`

```python
from common.errors import CacheError

try:
    result = await cache.get(key)
except RedisError as e:
    raise CacheError(
        message="Error al acceder a la caché",
        details={"operation": "get", "key": key}
    )
```

## 13. Métricas y Monitoreo

**Tags:** `#metrics` `#monitoring` `#observability`

### 13.1 Métricas a Recolectar

**Tags:** `#key_metrics` `#data_collection` `#analytics`

Según el documento "Métricas y Monitoreo":

- **Frecuencia por tipo de error**: Conteo por `error_code`
- **Errores por tenant**: Distribución entre tenants
- **Tasa de error**: Porcentaje de solicitudes que resultan en error
- **Latencia en caso de error**: Tiempo hasta que se detecta y maneja el error

### 13.2 Alertas Recomendadas

**Tags:** `#alerts` `#notifications` `#thresholds`

- Picos repentinos en la tasa de errores
- Errores críticos persistentes para un tenant específico
- Tiempos de respuesta anormales en caso de error
- Errores repetidos de comunicación entre servicios
