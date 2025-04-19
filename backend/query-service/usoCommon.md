# Uso de Common en Query Service

Este documento describe las funciones y módulos del directorio `common` utilizados por el servicio Query. Se actualiza automáticamente tras cada revisión exhaustiva de submódulos y archivos.

| Módulo/Función                                    | Descripción breve                                         | Implementación correcta |
|---------------------------------------------------|-----------------------------------------------------------|------------------------|
| `common.config.get_settings`                      | Obtiene la configuración centralizada                     | Sí                     |
| `common.models.*`                                 | Modelos de datos compartidos                              | Sí                     |
| `common.errors.*`                                 | Manejo y definición de errores                            | Sí                     |
| `common.cache.manager.CacheManager`               | Gestión de caché unificada                                | Sí                     |
| `common.tracking.track_token_usage`               | Tracking de uso de tokens                                 | Sí                     |
| `common.tracking.track_query`                     | Tracking de queries                                       | Sí                     |
| `common.tracking.track_usage`                     | Tracking de uso general                                   | Sí                     |
| `common.context.*`                                | Gestión de contexto y decoradores                         | Sí                     |
| `common.llm.token_counters.count_tokens`          | Contador de tokens para LLMs                              | Sí                     |
| `common.llm.ollama.get_llm_model`                 | Obtención del modelo LLM                                  | Sí                     |
| `common.db.supabase.get_supabase_client`          | Cliente para acceso a base de datos Supabase              | Sí                     |
| `common.db.tables.get_table_name`                 | Utilidad para nombres de tablas                           | Sí                     |
| `common.utils.http.call_service`                  | Llamadas HTTP a servicios externos                        | Sí                     |
| `common.auth.verify_tenant`                       | Verificación de autenticidad de tenant                    | Sí                     |
| `common.auth.validate_model_access`               | Validación de acceso a modelos                            | Sí                     |
| `common.context.with_context`                     | Decorador para inyección de contexto                      | Sí                     |
| `common.context.set_current_tenant_id`            | Setter de contexto de tenant                              | Sí                     |
| `common.context.get_current_tenant_id`            | Getter de contexto de tenant                              | Sí                     |
| `common.context.get_current_collection_id`        | Getter de contexto de colección                           | Sí                     |
| `common.context.set_current_context_value`        | Setter de valores de contexto                             | Sí                     |
| `common.swagger.configure_swagger_ui`             | Configuración de Swagger UI                               | Sí                     |

**Notas:**
- Todas las funciones de `common` utilizadas están alineadas con la arquitectura y la refactorización reciente.
- Mantener las rutas de importación y dependencias actualizadas según la documentación de `common`.
- Si se detectan funciones no usadas o referencias obsoletas, se marcarán para revisión en `muertasCommon.md`.

Última actualización automática: 2025-04-18
