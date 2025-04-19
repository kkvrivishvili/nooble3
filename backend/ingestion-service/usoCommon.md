# Uso de Common en Ingestion Service

Este documento describe las funciones y módulos del directorio `common` utilizados por el servicio Ingestion. Se actualiza automáticamente tras cada revisión exhaustiva de submódulos y archivos.

| Módulo/Función                                    | Descripción breve                                         | Implementación correcta |
|---------------------------------------------------|-----------------------------------------------------------|------------------------|
| `common.config.get_settings`                      | Obtiene la configuración centralizada                     | Sí                     |
| `common.models.*`                                 | Modelos de datos compartidos                              | Sí                     |
| `common.errors.*`                                 | Manejo y definición de errores                            | Sí                     |
| `common.cache.manager.CacheManager`               | Gestión de caché unificada                                | Sí                     |
| `common.context.*`                                | Gestión de contexto y decoradores                         | Sí                     |
| `common.db.supabase.get_supabase_client`          | Cliente para acceso a base de datos Supabase              | Sí                     |
| `common.db.tables.get_table_name`                 | Utilidad para nombres de tablas                           | Sí                     |
| `common.utils.http.call_service`                  | Llamadas HTTP a servicios externos                        | Sí                     |
| `common.auth.verify_tenant`                       | Verificación de autenticidad de tenant                    | Sí                     |
| `common.tracking.track_token_usage`               | Tracking de uso de tokens                                 | Sí                     |
| `common.tracking.track_embedding_usage`           | Tracking de uso de embeddings                             | Sí                     |
| `common.utils.http.check_service_health`          | Chequeo de salud de servicios externos                    | Sí                     |
| `common.context.with_context`                     | Decorador para inyección de contexto                      | Sí                     |
| `common.context.vars.get_current_tenant_id`       | Getter de contexto de tenant                              | Sí                     |
| `common.context.vars.get_current_collection_id`   | Getter de contexto de colección                           | Sí                     |
| `common.config.tiers.get_tier_limits`             | Límites de uso por tier                                   | Sí                     |
| `common.config.tiers.get_available_embedding_models`| Modelos de embedding disponibles por tier                | Sí                     |

**Notas:**
- El uso de funciones de `common` está alineado con la arquitectura y la refactorización de responsabilidades.
- Se recomienda mantener las importaciones actualizadas según la documentación de `common`.
- Si se detectan funciones no usadas o referencias obsoletas, se marcarán para revisión en `muertasCommon.md`.

Última actualización automática: 2025-04-18
