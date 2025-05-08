# Plan de Actualización de Servicios para el Nuevo Sistema de Tracking

## Objetivo
Actualizar todos los servicios que utilizan tracking de tokens para aprovechar el nuevo sistema centralizado con idempotencia y tipos estandarizados.

## Cronograma Propuesto

| Fase | Periodo | Descripción |
|------|---------|-------------|
| 1 | Semana 1 | Refactorización de servicios críticos (Agent, Query) |
| 2 | Semana 2 | Actualización de servicios secundarios (Embedding, Ingestion) |
| 3 | Semana 3 | Implementación de idempotencia en operaciones de alto valor |
| 4 | Semana 4 | Mejora de metadatos y observabilidad |

## Servicios a Actualizar

### 1. Agent Service (Prioridad Alta)
- **Archivos clave**: 
  - `agent-service/routes/chat.py`
  - `agent-service/routes/public.py`
  - `agent-service/services/agent_executor.py`
- **Cambios requeridos**:
  - Usar constantes estandarizadas (TOKEN_TYPE_LLM, OPERATION_CHAT)
  - Implementar idempotencia en operaciones críticas
  - Mejorar metadatos con information relevante de la ejecución

### 2. Query Service (Prioridad Alta)
- **Archivos clave**: 
  - `query-service/routes/query.py`
  - `query-service/routes/internal.py`
  - `query-service/services/query_engine.py`
- **Cambios requeridos**:
  - Estandarizar tipos de operaciones (OPERATION_QUERY, OPERATION_VECTOR_SEARCH)
  - Usar idempotencia en operaciones de búsqueda críticas
  - Enriquecer metadatos con información de rendimiento y estrategia

### 3. Embedding Service (Prioridad Media)
- **Archivos clave**: 
  - `embedding-service/routes/embeddings.py`
  - `embedding-service/services/embedding_provider.py`
  - `embedding-service/services/llama_index_utils.py`
- **Cambios requeridos**:
  - Usar TOKEN_TYPE_EMBEDDING consistentemente
  - Implementar idempotencia en procesamiento por lotes
  - Mejorar reporting de uso de modelos

### 4. Ingestion Service (Prioridad Media)
- **Archivos clave**: 
  - `ingestion-service/services/embedding.py`
  - `ingestion-service/services/chunking.py`
- **Cambios requeridos**:
  - Actualizar a constantes estandarizadas
  - Implementar idempotencia para evitar doble conteo en reintentos
  - Mejorar metadatos con información relevante de los documentos

### 5. Common Core (Prioridad Baja)
- **Archivos clave**: 
  - `common/db/rpc.py` (Marcar como obsoleto)
  - `common/core/adapters.py`
  - `common/llm/callbacks.py`
- **Cambios requeridos**:
  - Eliminar código duplicado o marcarlo como obsoleto
  - Asegurar compatibilidad con versiones antiguas
  - Actualizar documentación

## Implementación por Servicio

### Plantilla para Query Service

```python
# Importar constantes estandarizadas
from common.tracking import (
    track_token_usage, 
    TOKEN_TYPE_LLM, 
    OPERATION_QUERY, 
    OPERATION_VECTOR_SEARCH
)

async def process_query(query_text, tenant_id, conversation_id=None):
    # Generar clave idempotencia para esta operación específica
    operation_id = str(uuid.uuid4())
    idempotency_key = f"query:{tenant_id}:{operation_id}"
    
    # Ejecutar la consulta
    start_time = time.time()
    result = await query_engine.execute(query_text)
    execution_time_ms = int((time.time() - start_time) * 1000)
    
    # Registrar uso de tokens con idempotencia y metadatos enriquecidos
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=result.token_usage,
        model=result.model,
        token_type=TOKEN_TYPE_LLM,
        operation=OPERATION_QUERY,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        metadata={
            "query_type": "semantic",
            "execution_time_ms": execution_time_ms,
            "operation_id": operation_id,
            "query_strategy": result.strategy
        }
    )
    
    return result
```

### Plantilla para Agent Service

```python
# Importar constantes estandarizadas
from common.tracking import (
    track_token_usage, 
    TOKEN_TYPE_LLM, 
    OPERATION_CHAT
)

async def process_agent_chat(tenant_id, agent_id, conversation_id, message):
    # Generar clave idempotencia para esta operación específica 
    # con componentes relevantes para evitar duplicación
    idempotency_key = f"agent:{tenant_id}:{agent_id}:{conversation_id}:{message.message_id}"
    
    # Ejecutar el procesamiento del agente
    start_time = time.time()
    response = await agent_executor.process_message(message)
    execution_time_ms = int((time.time() - start_time) * 1000)
    
    # Registrar uso de tokens con idempotencia y metadatos enriquecidos
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=response.token_usage,
        model=response.model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type=TOKEN_TYPE_LLM,
        operation=OPERATION_CHAT,
        idempotency_key=idempotency_key,
        metadata={
            "message_id": message.message_id,
            "execution_time_ms": execution_time_ms,
            "tools_used": response.tools_used,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens
        }
    )
    
    return response
```

## Métricas de Progreso

Para cada servicio, el progreso se medirá por:
1. **Porcentaje de llamadas actualizadas** a la nueva interfaz
2. **Uso de claves de idempotencia** en operaciones críticas
3. **Riqueza de metadatos** proporcionados en cada tracking
4. **Reducción de llamadas** a código obsoleto o deprecated

## Plan de Pruebas

Para cada servicio actualizado:
1. Verificar que las estadísticas diarias y mensuales se actualizan correctamente
2. Comprobar que no hay conteo duplicado en operaciones con reintentos
3. Validar la correcta atribución de tokens en casos de agentes compartidos
4. Asegurar que los metadatos se registran y son accesibles para análisis

## Procedimiento de Rollback

En caso de problemas con la nueva implementación:
1. La estrategia de fallback automático permite volver al método anterior
2. No se requieren cambios en la base de datos para revertir cambios
3. En caso necesario, se puede revertir específicamente el código de los servicios afectados
