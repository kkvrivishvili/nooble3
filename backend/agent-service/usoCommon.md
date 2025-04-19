# Uso de Common en Agent Service

Este documento describe las funciones y módulos del directorio `common` utilizados por el servicio Agent. Se actualiza automáticamente tras cada revisión exhaustiva de submódulos y archivos.

| Módulo/Función                                    | Descripción breve                                         | Implementación correcta |
|---------------------------------------------------|-----------------------------------------------------------|------------------------|
| `common.config.get_settings`                      | Obtiene la configuración centralizada                     | Sí                     |
| `common.config.invalidate_settings_cache`         | Limpia la caché de settings tras cambios                  | Sí                     |
| `common.models.*`                                 | Modelos de datos compartidos                              | Sí                     |
| `common.errors.*`                                 | Manejo y definición de errores                            | Sí                     |
| `common.cache.manager.CacheManager`               | Gestión de caché unificada                                | Sí                     |
| `common.tracking.track_token_usage`               | Tracking de uso de tokens                                 | Sí                     |
| `common.tracking.track_usage`                     | Tracking de uso general                                   | Sí                     |
| `common.tracking.track_query`                     | Tracking de queries                                       | Sí                     |
| `common.context.*`                                | Gestión de contexto y decoradores                         | Sí                     |
| `common.db.supabase.get_supabase_client`          | Cliente para acceso a base de datos Supabase              | Sí                     |
| `common.db.tables.get_table_name`                 | Utilidad para nombres de tablas                           | Sí                     |
| `common.llm.token_counters.count_tokens`          | Contador de tokens para LLMs                              | Sí                     |
| `common.utils.stream.stream_llm_response`         | Streaming de respuestas LLM                               | Sí                     |
| `common.utils.http.call_service`                  | Llamadas HTTP a servicios externos                        | Sí                     |
| `common.context.ContextManager`                   | Gestión avanzada de contexto                              | Sí                     |
| `common.context.with_context`                     | Decorador para inyección de contexto                      | Sí                     |
| `common.auth.verify_tenant`                       | Verificación de autenticidad de tenant                    | Sí                     |

**Notas:**
- Todas las importaciones se ajustan a la arquitectura centralizada y a la refactorización reciente.
- Se recomienda mantener las rutas de importación actualizadas según la documentación de `common`.
- Si se detectan funciones no usadas o referencias obsoletas, se marcarán para revisión en `muertasCommon.md`.

Última actualización automática: 2025-04-18
