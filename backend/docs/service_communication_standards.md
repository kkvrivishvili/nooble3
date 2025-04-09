# Estándares de Comunicación entre Servicios

## Introducción

Este documento define los estándares y mejores prácticas para la comunicación entre microservicios en la plataforma. El objetivo es garantizar uniformidad, confiabilidad y eficiencia en todas las interacciones entre servicios, facilitando el mantenimiento y la depuración.

## Arquitectura de Comunicación

### 1. Función Unificada: `call_service`

La comunicación entre servicios se realiza exclusivamente a través de la función `call_service` en el módulo `common.utils.http`. Esta función proporciona:

- **Propagación automática de contexto**: Tenant, agente, conversación y colección
- **Manejo estandarizado de errores**: Respuestas consistentes para errores de red, servidor, etc.
- **Gestión inteligente de timeouts**: Según el tipo de operación
- **Reintentos automáticos**: Para errores transitorios
- **Integración con caché**: Aprovechamiento opcional del `CacheManager`

### 2. Formato Estandarizado de Respuesta

Todas las respuestas entre servicios siguen este formato estándar:

```json
{
  "success": true|false,           // Estado de la operación
  "message": "Descripción clara",  // Mensaje descriptivo para humanos
  "data": { ... },                 // Datos principales (payload)
  "metadata": { ... },             // Metadatos de la operación
  "error": { ... }                 // Solo presente en caso de error
}
```

### 3. Nomenclatura de Endpoints Internos

Los endpoints destinados exclusivamente a comunicaciones entre servicios (no expuestos al usuario) siguen el patrón:

```
/internal/<nombre-operación>
```

Ejemplos:
- `/internal/query`: Consultas RAG desde Agent Service a Query Service
- `/internal/embed`: Generación de embeddings desde otros servicios a Embedding Service
- `/internal/search`: Búsqueda rápida de documentos desde Context Manager a Query Service

## Implementación

### Utilización de `call_service`

```python
from common.utils.http import call_service

# Ejemplo: Consulta desde Agent Service a Query Service
response = await call_service(
    url=f"{settings.query_service_url}/internal/query",
    data={
        "tenant_id": tenant_id,
        "query": query,
        "collection_id": collection_id,
        # Otros parámetros específicos de la operación
    },
    tenant_id=tenant_id,
    agent_id=agent_id,
    conversation_id=conversation_id,
    collection_id=collection_id,
    operation_type="rag_query",     # Tipo de operación para timeout apropiado
    use_cache=True,                # Activar caché para esta operación
    cache_ttl=1800                 # TTL personalizado (30 minutos)
)

# Procesamiento de respuesta estandarizada
if response.get("success", False):
    # Extraer datos del campo data
    result_data = response.get("data", {})
    # Procesar resultado...
else:
    # Manejar error
    error_message = response.get("message", "Error desconocido")
    error_details = response.get("error", {})
    logger.error(f"Error en operación: {error_message}")
    # Manejar el error apropiadamente...
```

### Definición de Endpoint Interno

```python
@router.post(
    "/internal/operation-name",
    tags=["Internal"]
)
@handle_service_error_simple
@with_context(tenant=True, agent=True, conversation=True, collection=True)
async def internal_operation(
    # Parámetros de la operación
) -> Dict[str, Any]:
    """
    Documentación del endpoint interno.
    """
    # Implementación...
    
    # Devolver respuesta en formato estandarizado
    return {
        "success": True,
        "message": "Operación completada con éxito",
        "data": {
            # Datos principales
        },
        "metadata": {
            "processing_time": processing_time,
            # Otros metadatos
        }
    }
```

## Integración con Sistema de Caché

El sistema de comunicación entre servicios se integra perfectamente con el `CacheManager`, permitiendo optimizar el rendimiento mediante la reducción de llamadas redundantes.

### Tipos de Operaciones y TTL Recomendados

| Tipo de Operación | Descripción | TTL Recomendado |
|-------------------|-------------|----------------|
| `embedding` | Generación de embeddings | 86400 (24 horas) |
| `rag_query` | Consultas RAG completas | 3600 (1 hora) |
| `rag_search` | Búsqueda simple sin generación | 1800 (30 min) |
| `agent_response` | Respuestas de agentes | 1800 (30 min) |
| `agent_config` | Configuraciones de agentes | 300 (5 min) |
| `default` | Operación genérica | 300 (5 min) |

### Invalidación de Caché

Cuando un servicio modifica datos que podrían estar en caché, debe invalidar las entradas correspondientes:

```python
# Ejemplo: Después de actualizar documentos en una colección
from common.cache.manager import CacheManager

await CacheManager.invalidate(
    tenant_id=tenant_id,
    data_type="query_result",
    collection_id=collection_id
)
```

## Gestión de Timeouts

La función `call_service` utiliza timeouts diferentes según el tipo de operación:

```python
OPERATION_TIMEOUTS = {
    "default": 30.0,           # Operación genérica: 30 segundos
    "embedding": 60.0,         # Generación de embeddings: 60 segundos
    "rag_query": 45.0,         # Consultas RAG: 45 segundos
    "rag_search": 20.0,        # Búsqueda simple: 20 segundos
    "agent_config": 10.0,      # Configuración de agente: 10 segundos
    "health_check": 5.0        # Verificación de salud: 5 segundos
}
```

Se puede personalizar el timeout para casos especiales:

```python
# Ejemplo: Operación que requiere timeout extendido
response = await call_service(
    url=url,
    data=data,
    # Otros parámetros...
    custom_timeout=120.0  # 2 minutos para operaciones largas
)
```

## Manejo de Errores

El sistema proporciona manejo automático de errores comunes:

- **Errores de conexión**: Reintentos automáticos con backoff exponencial
- **Errores de servidor (5xx)**: Registrados con detalles y devueltos de forma estandarizada
- **Errores de cliente (4xx)**: Registrados como advertencias
- **Timeouts**: Registrados claramente con la operación que los causó

### Ejemplo de Respuesta de Error Estandarizada

```json
{
  "success": false,
  "message": "Error al procesar la consulta RAG",
  "data": null,
  "metadata": {
    "processing_time": 1.25,
    "error_type": "TimeoutError"
  },
  "error": {
    "type": "TimeoutError",
    "message": "La operación excedió el tiempo límite de 45 segundos",
    "details": {
      "service": "query-service",
      "endpoint": "/internal/query",
      "operation_type": "rag_query"
    }
  }
}
```

## Expansión del Sistema

### Añadir Nuevos Tipos de Operaciones

Para añadir un nuevo tipo de operación:

1. Actualizar `OPERATION_TIMEOUTS` en `common.utils.http` con el nuevo tipo y su timeout recomendado
2. Documentar el nuevo tipo y su uso recomendado en este documento
3. Implementar cualquier lógica especializada en `get_timeout_for_operation` si es necesario

### Añadir Nuevos Campos a la Respuesta Estándar

Si se necesita expandir el formato de respuesta estándar:

1. Actualizar la función `standardize_response` en `common.utils.http`
2. Mantener compatibilidad con el formato básico (`success`, `message`, `data`, `metadata`, `error`)
3. Documentar el nuevo campo y su propósito en este documento
4. Actualizar los endpoints existentes de forma incremental

## Mejores Prácticas

1. **Siempre utilizar `call_service`**: Nunca implementar llamadas HTTP directas entre servicios

2. **Diseñar para reintentos idempotentes**: Asegurar que las operaciones son seguras para reintentar

3. **Aprovechar el contexto**: Pasar siempre tenant_id, agent_id, conversation_id y collection_id cuando estén disponibles

4. **Utilizar caché de forma inteligente**: Activar caché para operaciones costosas o frecuentes

5. **Documentar endpoints internos**: Proporcionar documentación clara de todos los endpoints internos

6. **Mantener la compatibilidad**: Al modificar endpoints, asegurar compatibilidad con versiones anteriores

7. **Probar errores**: Verificar que los errores se manejan correctamente en escenarios de fallo

8. **Monitorizar latencia**: Registrar y analizar los tiempos de respuesta entre servicios

9. **Validar respuestas**: Verificar siempre el campo `success` antes de procesar datos

10. **Estructura de URL adecuada**: Seguir el patrón `/internal/<operación>` para endpoints internos
