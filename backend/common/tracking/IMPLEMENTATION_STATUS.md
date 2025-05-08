# Estado de Implementación del Sistema Unificado de Tracking de Tokens

## Cambios Realizados

### 1. Estandarización de Constantes

El módulo `common.tracking` ahora incluye constantes estandarizadas para:

- **Tipos de tokens**: `TOKEN_TYPE_LLM`, `TOKEN_TYPE_EMBEDDING`, `TOKEN_TYPE_FINE_TUNING`
- **Tipos de operaciones**: 
  - `OPERATION_QUERY`
  - `OPERATION_CHAT`
  - `OPERATION_SUMMARIZE`
  - `OPERATION_VECTOR_SEARCH`
  - `OPERATION_GENERATION`
  - `OPERATION_CLASSIFICATION`
  - `OPERATION_EXTRACTION`
  - `OPERATION_BATCH` (nueva)
  - `OPERATION_INTERNAL` (nueva)

Estas constantes corresponden exactamente a los ENUM definidos en la base de datos, garantizando la consistencia de los datos.

### 2. Soporte de Idempotencia

Se ha implementado el soporte completo de idempotencia en todos los servicios mediante:

- Generación de claves únicas basadas en el contenido de la operación y el tenant
- Uso del parámetro `idempotency_key` en todas las llamadas a `track_token_usage()`
- Estructura estandarizada para claves: `{operacion}:{tenant_id}:{hash_contenido}:{timestamp}`

Esto previene eficazmente el doble conteo de tokens en escenarios de reintento o errores transitorios.

### 3. Metadatos Enriquecidos

Los metadatos ahora incluyen información adicional crítica:

- **Proveedor de modelo**: Identificación específica para cada proveedor
  - `groq`: Para modelos Llama 3.2 70b y Llama 3.1 8b
  - `openai`: Para modelos de OpenAI
  - `ollama`: Para modelos locales como Qwen 3.0
- **Estadísticas de texto**: Caracteres totales, longitud media, tokens de entrada/salida
- **IDs de operación**: Para mejor trazabilidad y depuración

### 4. Servicios Actualizados

#### Servicio de Query
- Actualizado para identificar correctamente modelos de Groq y Ollama
- Implementado tracking preciso de tokens de entrada y salida
- Añadida información de familia de modelos para análisis detallado

#### Servicio de Embedding
- Actualizado para OpenAI y Ollama con metadatos específicos
- Todos los endpoints (`/embeddings`, `/embeddings/batch`, `/internal/embed`) ahora usan constantes estandarizadas
- Implementada idempotencia en todas las operaciones

## Próximos Pasos

### 1. Corrección de Inconsistencias

#### Alta Prioridad
- [ ] Estandarizar cálculo de tokens entre servicios (actualmente `count_tokens()` vs `estimate_prompt_tokens()`)
- [ ] Implementar política consistente de reintentos en todos los servicios

#### Media Prioridad
- [ ] Actualizar el servicio de Ingestion para tracking de tokens en chunking
- [ ] Verificar que el servicio de Agent no realice contabilización directa

#### Baja Prioridad
- [ ] Implementar pruebas automatizadas para verificar la idempotencia
- [ ] Añadir dashboards de monitoreo para uso de tokens por proveedor

### 2. Aspectos Técnicos Pendientes

- Mejorar el rendimiento en escenarios de alto volumen
- Completar la integración con el sistema de alertas
- Implementar reconciliación periódica para detectar inconsistencias

## Notas Técnicas

- La función `track_token_usage()` en `_base.py` ahora soporta fallback con un sistema de reintentos integrado
- Todos los servicios deben utilizar constantes estandarizadas en lugar de strings literales
- Las claves de idempotencia deben generarse de forma consistente según los patrones documentados

---

*Última actualización: 2025-05-08*
