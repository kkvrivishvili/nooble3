# Sistema de Comunicación HTTP Entre Servicios

## Descripción General

Este módulo proporciona una implementación centralizada para la comunicación HTTP entre los distintos microservicios del backend. Está diseñado para garantizar prácticas óptimas, alta disponibilidad y comunicación consistente entre todos los componentes del sistema.

El módulo se encuentra en `common/utils/http.py` y representa el estándar para todas las comunicaciones entre servicios.

## Características Principales

### 1. Comunicación Estandarizada con `call_service`

La función `call_service` es el método principal para realizar llamadas entre servicios:

```python
from common.utils.http import call_service

response = await call_service(
    url="http://embedding-service:8000/api/generate",
    data={"text": text_to_embed},
    tenant_id=tenant_id,
    operation_type="embedding",
    use_cache=True
)
```

Características destacadas:

- **Propagación automática de contexto**: Preserva información de tenant, agent, conversation y collection
- **Manejo de reintentos**: Implementa backoff exponencial con jitter para alta disponibilidad
- **Timeouts específicos**: Configurados según el tipo de operación
- **Circuit breaker**: Previene cascadas de fallos cuando un servicio está degradado
- **Caché de respuestas**: Optimización opcional para llamadas frecuentes e idempotentes
- **Respuestas estandarizadas**: Formato consistente para facilitar el procesamiento

### 2. Verificación de Salud de Servicios

```python
from common.utils.http import check_service_health

is_available = await check_service_health(
    service_url="http://embedding-service:8000",
    service_name="Embedding Service"
)
```

### 3. Manejo Estandarizado de Errores

```python
from common.utils.http import create_error_response

error_response = create_error_response(
    "No se pudo procesar la solicitud",
    {"details": "Error específico"}
)
```

## Estado Actual de Implementación

### Uso Correcto del Módulo

Los siguientes servicios utilizan correctamente `call_service` para comunicación:

- **Query Service**: Para solicitudes a servicios externos de LLM y embeddings
- **Ingestion Service**: Para solicitudes al servicio de embeddings
- **Agent Service**: Para comunicación con herramientas y servicios externos

### Implementaciones No Estandarizadas

Se han identificado algunas implementaciones que utilizan directamente `httpx` en lugar del módulo centralizado:

1. **Verificaciones de salud** (health checks): La mayoría de los endpoints de health utilizan implementaciones personalizadas
2. **Comunicación con Ollama**: Llamadas directas al servicio local de Ollama
3. **Comunicación streaming de LLM**: Casos específicos donde se requiere streaming

## Buenas Prácticas

1. **Siempre usar `call_service` para comunicación entre servicios**
   ```python
   # ✅ CORRECTO
   from common.utils.http import call_service
   result = await call_service(url=service_url, data=request_data)
   
   # ❌ INCORRECTO
   import httpx
   async with httpx.AsyncClient() as client:
       response = await client.post(service_url, json=request_data)
   ```

2. **Propagar el contexto automáticamente**
   ```python
   # El contexto se propaga automáticamente
   result = await call_service(
       url=service_url,
       data=request_data
       # tenant_id, agent_id, etc. se toman del contexto actual
   )
   ```

3. **Utilizar tipos de operación específicos para timeouts adecuados**
   ```python
   # Para operaciones de embedding (timeout de 60s)
   result = await call_service(url=embedding_url, data=data, operation_type="embedding")
   
   # Para operaciones más intensivas de RAG (timeout de 120s)
   result = await call_service(url=query_url, data=data, operation_type="rag_query")
   ```

4. **Manejar correctamente las respuestas**
   ```python
   result = await call_service(url=service_url, data=request_data)
   
   if result["success"]:
       # Procesar datos
       return result["data"]
   else:
       # Manejar error
       logger.error(f"Error en llamada: {result['error']['message']}")
       raise ServiceError(result["error"]["message"])
   ```

## Casos de Uso Específicos

### Llamadas con Caché

Para operaciones idempotentes que pueden beneficiarse de caché:

```python
result = await call_service(
    url=service_url,
    data=request_data,
    use_cache=True,
    cache_ttl=600  # 10 minutos
)
```

### Comunicación con API Externas

Para APIs externas (no microservicios de nuestra plataforma):

```python
result = await call_service(
    url=external_api_url,
    data=request_data,
    headers={"Authorization": f"Bearer {api_key}"},
    max_retries=5,
    custom_timeout=120.0
)
```

### Solicitudes GET

Para solicitudes GET en lugar de POST:

```python
result = await call_service(
    url=service_url,
    data=query_params,  # Se convierten en parámetros de URL
    method="GET"
)
```

## Áreas de Mejora

Tras el análisis del sistema actual, se identifican las siguientes oportunidades de mejora:

1. **Estandarización completa**
   - Migrar todas las llamadas HTTP directas al módulo centralizado
   - Estandarizar las verificaciones de salud entre servicios

2. **Telemetría y observabilidad**
   - Agregar soporte para tracing distribuido (OpenTelemetry)
   - Mejorar métricas de latencia y disponibilidad entre servicios

3. **Mejoras en el circuit breaker**
   - Implementar persistencia de estado entre instancias
   - Configuración por servicio de umbrales y tiempos de recuperación

4. **Autenticación y seguridad**
   - Implementar mecanismos de autenticación entre servicios
   - Añadir firmas de solicitudes para verificación de integridad

5. **Soporte para comunicación streaming**
   - Extender la API para soportar respuestas streaming de manera estandarizada
   - Integración con el sistema de streaming existente

## Migración y Adopción

Para migrar implementaciones existentes al módulo centralizado:

1. Identificar todas las llamadas directas con `httpx`
2. Reemplazar por llamadas a `call_service` con parámetros equivalentes
3. Adaptar el manejo de respuestas al formato estandarizado

## Conclusión

El sistema de comunicación HTTP centralizado proporciona una base sólida para la comunicación entre servicios, con características avanzadas de resiliencia y propagación de contexto. Su adopción completa garantizará un comportamiento consistente, mejor observabilidad y mayor robustez en el ecosistema de microservicios.
