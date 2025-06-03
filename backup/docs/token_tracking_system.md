# Sistema Unificado de Tracking de Tokens

## Arquitectura y Estado de Implementación

Este documento describe la arquitectura y el estado actual del sistema unificado de tracking de tokens implementado en todos los servicios backend.

## Estado de Implementación (08/05/2025)

| Fase | Estado | Descripción | Completado |
|------|--------|-------------|------------|
| 1 | **COMPLETADO** | Refactorización de servicios críticos (Agent, Query) | ✅ |
| 2 | **COMPLETADO** | Actualización de servicios secundarios (Embedding, Ingestion) | ✅ |
| 3 | **COMPLETADO** | Implementación de idempotencia en operaciones de alto valor | ✅ |
| 4 | En progreso | Mejora de metadatos y observabilidad | 80% |

## Componentes Clave del Sistema

### 1. Tipos Estandarizados
- Constantes como `TOKEN_TYPE_LLM`, `TOKEN_TYPE_EMBEDDING`, `TOKEN_TYPE_FINE_TUNING`
- Operaciones estandarizadas: `OPERATION_QUERY`, `OPERATION_CHAT`, `OPERATION_SUMMARIZE`, `OPERATION_BATCH`, `OPERATION_INTERNAL`
- Correspondencia exacta con ENUM en base de datos para consistencia

### 2. Soporte para Idempotencia
- Parámetro `idempotency_key` en la función `track_token_usage`
- Generación automática de claves basadas en la operación: `{operacion}:{tenant_id}:{id_recurso}:{timestamp}`
- Prevención efectiva del doble conteo en escenarios de reintento

### 3. Función Unificada
```python
async def track_token_usage(
    tenant_id: Optional[str] = None,
    tokens: int = 0,
    model: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    token_type: str = "llm",  # Usar constantes TOKEN_TYPE_*
    operation: str = "query", # Usar constantes OPERATION_*
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None
) -> bool:
```

## Servicios Actualizados

### 1. Agent Service (COMPLETADO ✅)
- **Archivos actualizados**: 
  - `agent-service/services/agent_executor.py` - Desactivado tracking directo para evitar doble conteo
- **Detalles de implementación**:
  - Tokens contabilizados por Query Service para evitar doble conteo
  - Añadidos comentarios explicativos en el código
  - Mantenido logging para debugging sin impactar contabilización

### 2. Query Service (COMPLETADO ✅)
- **Archivos actualizados**: 
  - `query-service/services/query_engine.py`
- **Detalles de implementación**:
  - Uso de constantes estandarizadas para todas las operaciones
  - Implementada generación de claves de idempotencia robustas
  - Soporte para modelos de múltiples proveedores (OpenAI, Groq, Ollama)
  - Metadatos enriquecidos con estadísticas de rendimiento

### 3. Embedding Service (COMPLETADO ✅)
- **Archivos actualizados**: 
  - `embedding-service/routes/embeddings.py`
- **Detalles de implementación**:
  - Uso de constantes estandarizadas (`TOKEN_TYPE_EMBEDDING`)
  - Implementación de idempotencia en procesamiento por lotes
  - Soporte para modelos de OpenAI, Ollama y otros proveedores
  - Metadatos enriquecidos con estadísticas de uso

### 4. Ingestion Service (COMPLETADO ✅)
- **Archivos actualizados**: 
  - `ingestion-service/services/chunking.py`
- **Detalles de implementación**:
  - Tracking de tokens durante el proceso de chunking
  - Generación de claves de idempotencia basadas en hash del documento
  - Estadísticas detalladas de chunking en metadatos
  - Uso consistente de la función `estimate_prompt_tokens()`

### 5. Integración con Proveedores de LLM

#### OpenAI
- Identificación específica de modelos (gpt-3.5-turbo, gpt-4, text-embedding-ada-002)
- Manejo apropiado de conteo de tokens para diferentes tamaños de contexto

#### Groq
- Soporte completo para modelos Llama 3, incluyendo:
  - `llama3-8b-8192` (Llama 3 8B)
  - `llama3-70b-8192` (Llama 3 70B)
  - `llama3-1-8b-8192` (Llama 3.1 8B)
  - `llama3-1-70b-8192` (Llama 3.1 70B)
  - `mixtral-8x7b-32768` (Mixtral 8x7B)
  - `gemma-7b-it` (Gemma 7B)
- Integración mediante biblioteca oficial `groq`
- Streaming optimizado para baja latencia
- Gestión eficiente de tokens y contexto según el modelo

#### Ollama
- Soporte para modelos locales (Llama, Qwen, Mistral)
- Estimación precisa de tokens para cada modelo

## Beneficios Principales del Sistema

1. **Prevención de doble conteo**: Gracias a la implementación de idempotencia, las operaciones con reintentos no generan duplicación de conteo.
2. **Mejor atribución**: Identificación correcta del propietario de tokens en escenarios complejos como agentes compartidos.
3. **Reporting detallado**: Las tablas diarias y mensuales proporcionan una vista completa del uso de recursos.
4. **Consistencia entre servicios**: Uso de constantes estandarizadas para evitar inconsistencias.
5. **Observabilidad mejorada**: Metadatos enriquecidos permiten análisis detallado del uso.

## Interfaz de Base de Datos

El sistema utiliza las siguientes tablas:
- `daily_token_usage`: Registro diario de uso de tokens por tenant y tipo
- `monthly_token_usage`: Agregación mensual por tenant y tipo
- `token_idempotency`: Registro de operaciones para garantizar idempotencia

## Próximos Pasos

1. **Completar fase de observabilidad**: Finalizar la implementación de metadatos enriquecidos en todos los servicios
2. **Dashboard de monitoreo**: Implementar visualizaciones para facilitar el análisis de uso
3. **Alertas automáticas**: Configurar umbrales de alerta para detectar anomalías en el uso
4. **Documentación para desarrolladores**: Guías detalladas para la implementación correcta

## Guía para Desarrolladores

Para implementar tracking de tokens en un nuevo servicio:

```python
from common.tracking import (
    track_token_usage,
    TOKEN_TYPE_LLM,  # Para LLMs (o TOKEN_TYPE_EMBEDDING para embeddings)
    OPERATION_QUERY  # Operación correspondiente
)
import hashlib
import time

async def process_operation(tenant_id, input_text):
    # 1. Generar un identificador único para la operación
    operation_id = str(uuid.uuid4())
    timestamp = int(time.time())
    
    # 2. Crear una clave de idempotencia basada en datos relevantes
    idempotency_key = f"operation:{tenant_id}:{operation_id}:{timestamp}"
    
    # 3. Ejecutar la operación principal
    result = await perform_operation(input_text)
    
    # 4. Registrar uso de tokens con todos los detalles relevantes
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=result.token_usage,
        model=result.model_used,
        token_type=TOKEN_TYPE_LLM,
        operation=OPERATION_QUERY,
        idempotency_key=idempotency_key,
        metadata={
            "execution_time_ms": result.execution_time,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "operation_id": operation_id
        }
    )
    
    return result
```

## Referencias

- Documentación API en `common/tracking/README.md`
- Implementación principal en `common/tracking/_base.py`
- Memoria técnica: "Sistema Unificado de Tracking de Tokens" (Nooble Docs)
