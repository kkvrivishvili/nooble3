# Guía de Referencia del Sistema Unificado de Tracking de Tokens

## Introducción

Este documento proporciona una referencia del sistema unificado de tracking de tokens que ha sido implementado en todos los servicios. Las mejoras incluyen:
- Tipos estandarizados para `token_type` y `operation_type`
- Soporte completo para idempotencia
- Procedimiento unificado con mejor atribución de tokens y gestión de errores
- Integración con múltiples proveedores de LLM (OpenAI, Groq, Ollama)

## Implementación Completada

1. **Sistema Backend**
   - Tipos estandarizados en `common/tracking/__init__.py` (`TOKEN_TYPE_*` y `OPERATION_*`)
   - Función central `track_token_usage` con soporte completo para idempotencia
   - Eliminado código legacy (`increment_token_usage` y funciones relacionadas)

2. **Integración de Servicios**
   - **Agent Service**: Desactivado tracking directo para evitar doble conteo
   - **Query Service**: Implementada generación de claves de idempotencia y metadatos enriquecidos
   - **Embedding Service**: Soporte para operaciones por lotes con idempotencia
   - **Ingestion Service**: Tracking durante el proceso de chunking

3. **Soporte para Proveedores LLM**
   - **OpenAI**: Integración completa con modelos actuales
   - **Groq**: Implementado soporte para modelos Llama 3/3.1 y Mixtral
   - **Ollama**: Mantenida compatibilidad para despliegue local

## Patrones de Implementación Estandarizados

Todos los servicios core han sido actualizados al nuevo sistema. Esta guía de referencia muestra los patrones implementados que deben seguirse para cualquier nuevo desarrollo:

### 1. Usar Constantes Estandarizadas para Tipos

```python
# Antes
await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    token_type="llm",
    operation="query"
)

# Después
from common.tracking import track_token_usage, TOKEN_TYPE_LLM, OPERATION_QUERY

await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    token_type=TOKEN_TYPE_LLM,
    operation=OPERATION_QUERY
)
```

### 2. Aprovechar la Idempotencia

Para operaciones críticas donde es importante evitar el doble conteo de tokens:

```python
# Generar una clave de idempotencia basada en datos de la operación
idempotency_key = f"{operation_id}_{tenant_id}_{retry_count}"

await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    token_type=TOKEN_TYPE_LLM,
    operation=OPERATION_QUERY,
    idempotency_key=idempotency_key
)
```

### 3. Enriquecer Metadatos

Incluir metadatos enriquecidos para mejor observabilidad y auditoría:

```python
metadata = {
    "collection_id": collection_id,
    "document_ids": document_ids,
    "query_strategy": strategy,
    "operation_id": operation_id,
    "execution_time_ms": execution_time
}

await track_token_usage(
    tenant_id=tenant_id,
    tokens=token_count,
    token_type=TOKEN_TYPE_LLM,
    operation=OPERATION_QUERY,
    metadata=metadata
)
```

## Integración con Groq

El sistema de tracking ahora incluye soporte completo para modelos de Groq:

```python
from common.tracking import track_token_usage, TOKEN_TYPE_LLM, OPERATION_QUERY
from common.llm import get_groq_llm_model

# Obtener un modelo Groq
llm = get_groq_llm_model(model="llama3-70b-8192")

# Realizar la operación con el modelo
response = await llm.chat(messages=[{"role": "user", "content": query}])

# Registrar el uso con el sistema unificado
await track_token_usage(
    tenant_id=tenant_id,
    tokens=response["metadata"]["input_tokens"] + response["metadata"]["output_tokens"],
    model="llama3-70b-8192",
    token_type=TOKEN_TYPE_LLM,
    operation=OPERATION_QUERY,
    idempotency_key=f"groq:{tenant_id}:{uuid.uuid4()}",
    metadata={
        "provider": "groq",
        "input_tokens": response["metadata"]["input_tokens"],
        "output_tokens": response["metadata"]["output_tokens"]
    }
)
```

## Soporte y Resolución de Problemas

Si encuentras algún problema durante la migración, consulta los logs en nivel DEBUG para obtener información detallada sobre el funcionamiento interno de la función unificada.

Para preguntas o ayuda adicional, contacta al equipo de infraestructura.
