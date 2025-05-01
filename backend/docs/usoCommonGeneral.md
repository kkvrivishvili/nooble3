# Uso General de funciones y módulos de `common` en todos los servicios principales

Este documento centraliza el uso de todas las funciones y módulos del directorio `common` en los servicios principales (`agent-service`, `embedding-service`, `query-service`, `ingestion-service`).

| Módulo/Función                                    | Agent | Embedding | Query | Ingestion | Descripción breve |
|---------------------------------------------------|:-----:|:---------:|:-----:|:---------:|------------------|
| `common.config.get_settings`                      |   ✔   |     ✔     |   ✔   |     ✔     | Configuración centralizada                   |
| `common.config.invalidate_settings_cache`         |   ✔   |           |       |           | Limpia caché de settings                     |
| `common.models.*`                                 |   ✔   |     ✔     |   ✔   |     ✔     | Modelos de datos compartidos                 |
| `common.errors.*`                                 |   ✔   |     ✔     |   ✔   |     ✔     | Manejo y definición de errores               |
| `common.cache.manager.CacheManager`               |   ✔   |     ✔     |   ✔   |     ✔     | Gestión de caché unificada                   |
| `common.tracking.track_token_usage`               |   ✔   |     ✔     |   ✔   |     ✔     | Tracking de uso de tokens                    |
| `common.tracking.track_usage`                     |   ✔   |           |   ✔   |           | Tracking de uso general                      |
| `common.tracking.track_query`                     |   ✔   |           |   ✔   |           | Tracking de queries                          |
| `common.tracking.track_embedding_usage`           |       |     ✔     |       |     ✔     | Tracking de uso de embeddings                |
| `common.context.*`                                |   ✔   |     ✔     |   ✔   |     ✔     | Gestión de contexto y decoradores            |
| `common.context.ContextManager`                   |   ✔   |           |       |           | Gestión avanzada de contexto                 |
| `common.context.Context`                          |       |     ✔     |       |           | Contexto multinivel                          |
| `common.context.with_context`                     |   ✔   |     ✔     |   ✔   |     ✔     | Decorador para inyección de contexto         |
| `common.context.set_current_tenant_id`            |       |           |   ✔   |           | Setter de contexto de tenant                 |
| `common.context.get_current_tenant_id`            |       |           |   ✔   |           | Getter de contexto de tenant                 |
| `common.context.get_current_collection_id`        |       |           |   ✔   |           | Getter de contexto de colección              |
| `common.context.set_current_context_value`        |       |           |   ✔   |           | Setter de valores de contexto                |
| `common.context.vars.get_current_tenant_id`       |       |           |       |     ✔     | Getter de contexto de tenant (vars)          |
| `common.context.vars.get_current_collection_id`   |       |           |       |     ✔     | Getter de contexto de colección (vars)       |
| `common.db.supabase.get_supabase_client`          |   ✔   |     ✔     |   ✔   |     ✔     | Cliente para acceso a base de datos Supabase |
| `common.db.tables.get_table_name`                 |   ✔   |     ✔     |   ✔   |     ✔     | Utilidad para nombres de tablas              |
| `common.llm.token_counters.count_tokens`          |   ✔   |           |   ✔   |           | Contador de tokens para LLMs                 |
| `common.llm.ollama.get_llm_model`                 |       |     ✔     |   ✔   |           | Obtención del modelo LLM                     |
| `common.llm.ollama.get_embedding_model`           |       |     ✔     |       |           | Obtención del modelo de embedding            |
| `common.utils.stream.stream_llm_response`         |   ✔   |           |       |           | Streaming de respuestas LLM                  |
| `common.utils.http.call_service`                  |   ✔   |     ✔     |   ✔   |     ✔     | Llamadas HTTP a servicios externos           |
| `common.utils.http.check_service_health`          |       |           |       |     ✔     | Chequeo de salud de servicios externos       |
| `common.utils.logging.init_logging`               |       |     ✔     |       |           | Inicialización de logging                    |
| `common.utils.rate_limiting.setup_rate_limiting`  |       |     ✔     |       |           | Configuración de rate limiting               |
| `common.auth.verify_tenant`                       |   ✔   |     ✔     |   ✔   |     ✔     | Verificación de autenticidad de tenant       |
| `common.auth.validate_model_access`               |       |           |   ✔   |           | Validación de acceso a modelos               |
| `common.config.tiers.get_tier_limits`             |       |           |       |     ✔     | Límites de uso por tier                      |
| `common.config.tiers.get_available_embedding_models`|     |           |       |     ✔     | Modelos de embedding disponibles por tier    |
| `common.swagger.configure_swagger_ui`             |       |     ✔     |   ✔   |           | Configuración de Swagger UI                  |

**Notas:**
- Este archivo se genera automáticamente a partir de la revisión exhaustiva de los archivos usoCommon.md de cada servicio.
- Si se detectan funciones no usadas o referencias obsoletas, se marcarán para revisión en `muertasCommon.md`.
- Mantener las rutas de importación y dependencias actualizadas según la documentación de `common`.

Última actualización automática: 2025-04-18
