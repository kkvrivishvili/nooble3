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

## Tareas Completadas

### 1. Corrección de Inconsistencias

#### Alta Prioridad
- [x] Estandarizado cálculo de tokens entre servicios usando `count_tokens()` en todos los servicios
- [x] Implementada política consistente de reintentos con idempotencia

#### Media Prioridad
- [x] Actualizado el servicio de Ingestion para tracking de tokens en chunking
- [x] Verificado que el servicio de Agent no realiza contabilización directa para evitar doble conteo

#### Baja Prioridad
- [x] Implementadas pruebas básicas para verificar la idempotencia
- [ ] Añadir dashboards de monitoreo para uso de tokens por proveedor (Pendiente)

### 2. Integración con Proveedores

- [x] OpenAI: Implementación completa con modelos actuales
- [x] Groq: Implementación completa para modelos Llama 3/3.1 y Mixtral
- [x] Ollama: Implementación completa para modelos locales

### 3. Próximos Pasos

- Mejorar dashboards de monitoreo para uso de tokens por proveedor
- Ampliar el sistema de alertas para notificaciones en tiempo real
- Optimizar rendimiento en escenarios de alto volumen

## Notas Técnicas

- La función `track_token_usage()` en `_base.py` es ahora la única implementación centralizada
- Código legacy eliminado completamente del sistema (`increment_token_usage` y relacionados)
- Todos los servicios utilizan constantes estandarizadas del módulo `common.tracking`
- Implementado soporte para Groq en `query-service/provider/groq.py` con tracking unificado
- Implementadas funciones específicas de conteo de tokens en cada servicio:
  - `query-service/utils/token_counters.py`: Para modelos LLM (Groq, OpenAI, etc.)
  - `embedding-service/utils/token_counters.py`: Para modelos de embedding
- La carpeta `common/llm` ha sido completamente eliminada y sus funcionalidades migradas a los servicios específicos

---

*Última actualización: 2025-05-13*
