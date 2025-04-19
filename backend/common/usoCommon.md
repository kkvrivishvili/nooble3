# Uso de funciones y módulos de `common` en los servicios principales

Este documento se actualiza automáticamente cada vez que se revisan las implementaciones de funciones del directorio `common`. Aquí se indica en qué módulo y servicio se usa cada función/clase relevante.

| Función/Clase                        | agent | embedding | query | ingestion | Notas breves                                 |
|--------------------------------------|:-----:|:---------:|:-----:|:---------:|----------------------------------------------|
| config.get_settings                  |   ✔   |     ✔     |   ✔   |     ✔     | Configuración centralizada                   |
| config.get_tier_limits               |   ✔   |     ✔     |   ✔   |     ✔     | Límites por tier                             |
| config.get_available_llm_models      |   ✔   |     ✔     |   ✔   |           | Modelos LLM por tier                         |
| config.get_available_embedding_models|   ✔   |     ✔     |   ✔   |           | Modelos de embedding por tier                |
| auth.verify_tenant                   |   ✔   |     ✔     |   ✔   |     ✔     | Validación de tenant                         |
| auth.validate_model_access           |   ✔   |     ✔     |   ✔   |           | Validación de uso de modelos                 |
| cache.CacheManager                   |   ✔   |     ✔     |   ✔   |     ✔     | Caché unificada                              |
| context.with_context                 |   ✔   |     ✔     |   ✔   |     ✔     | Decorador de contexto                        |
| tracking.track_token_usage           |   ✔   |     ✔     |   ✔   |     ✔     | Tracking de tokens                           |
| tracking.track_embedding_usage       |       |     ✔     |       |     ✔     | Tracking de embeddings                       |
| db.get_supabase_client               |   ✔   |     ✔     |   ✔   |     ✔     | Cliente Supabase                             |
| db.get_table_name                    |   ✔   |     ✔     |   ✔   |     ✔     | Nombres de tablas multi-tenant               |
| llm.get_llm_model                    |   ✔   |           |   ✔   |           | Modelos LLM (OpenAI/Ollama)                  |
| llm.count_tokens                     |   ✔   |           |   ✔   |           | Contador de tokens                           |
| utils.call_service                   |       |           |   ✔   |     ✔     | Llamadas HTTP a microservicios               |
| utils.init_logging                   |   ✔   |     ✔     |   ✔   |     ✔     | Logging centralizado                         |
| utils.setup_rate_limiting            |   ✔   |     ✔     |   ✔   |     ✔     | Rate limiting                                |
| swagger.configure_swagger_ui         |   ✔   |     ✔     |   ✔   |     ✔     | Documentación interactiva                    |
| errors.handle_service_error_simple   |   ✔   |     ✔     |   ✔   |     ✔     | Decorador de manejo de errores               |

**Notas:**
- Este archivo debe mantenerse sincronizado con las revisiones de uso de funciones en los servicios.
- Si se detecta una función no utilizada, se debe marcar para revisión/eliminación en el archivo `muertasCommon.md`.
- Las rutas de importación deben seguir la arquitectura centralizada y las recomendaciones de refactorización.

---

Última actualización automática: 2025-04-18
