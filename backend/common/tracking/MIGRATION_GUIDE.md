# Guía de Migración del Sistema de Tracking de Tokens

## Introducción

Este documento proporciona instrucciones para la migración al nuevo sistema unificado de tracking de tokens que incluye las siguientes mejoras:
- Estandarización de tipos para token_type y operation_type
- Soporte para idempotencia
- Procedimiento unificado con mejor atribución de tokens y gestión de errores

## Cambios Realizados

1. **Consolidación de SQL**
   - Definiciones ENUM para `token_type` y `operation_type`
   - Tablas mejoradas para tracking diario y mensual
   - Procedimientos unificados para todas las operaciones de tracking

2. **Actualización de la Implementación Centralizada**
   - Función `track_token_usage` actualizada con soporte de idempotencia
   - Constantes estandarizadas para tipos de tokens y operaciones
   - Manejo mejorado de errores con fallback a la implementación anterior

3. **Migración de Servicios Dependientes**
   - Todos los servicios que utilizan `track_token_usage` ahora usan automáticamente la nueva implementación
   - Se mantiene compatibilidad hacia atrás para evitar interrupciones

## Guía de Migración para Servicios

Los servicios que ya utilizan la función `track_token_usage` no necesitan cambios inmediatos, ya que la implementación actualizada mantiene compatibilidad con las llamadas existentes.

Sin embargo, para aprovechar al máximo las nuevas funcionalidades, se recomienda actualizar gradualmente las llamadas siguiendo estas prácticas:

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

## Cronograma de Migración Recomendado

1. **Fase Inmediata**: No se requieren cambios - compatibilidad automática
2. **Corto Plazo (1-2 semanas)**: Actualizar a constantes estandarizadas
3. **Medio Plazo (2-4 semanas)**: Implementar idempotencia en operaciones críticas
4. **Largo Plazo (1-2 meses)**: Enriquecer metadatos y mejorar observabilidad

## Soporte y Resolución de Problemas

Si encuentras algún problema durante la migración, consulta los logs en nivel DEBUG para obtener información detallada sobre el funcionamiento interno de la función unificada.

Para preguntas o ayuda adicional, contacta al equipo de infraestructura.
