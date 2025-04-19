# Uso de Common en Embedding Service

Este documento describe las funciones y módulos del directorio `common` utilizados por el servicio Embedding. Se actualiza automáticamente tras cada revisión exhaustiva de submódulos y archivos.

| Módulo/Función                                    | Descripción breve                                         | Implementación correcta |
|---------------------------------------------------|-----------------------------------------------------------|------------------------|
| `common.config.get_settings`                      | Obtiene la configuración centralizada                     | Sí                     |
| `common.models.*`                                 | Modelos de datos compartidos                              | Sí                     |
| `common.errors.*`                                 | Manejo y definición de errores                            | Sí                     |
| `common.cache.manager.CacheManager`               | Gestión de caché unificada                                | Sí                     |
| `common.tracking.track_embedding_usage`           | Tracking de uso de embeddings                             | Sí                     |
| `common.tracking.track_token_usage`               | Tracking de uso de tokens                                 | Sí                     |
| `common.context.*`                                | Gestión de contexto y decoradores                         | Sí                     |
| `common.llm.ollama.get_embedding_model`           | Obtención del modelo de embedding                         | Sí                     |
| `common.db.supabase.get_supabase_client`          | Cliente para acceso a base de datos Supabase              | Sí                     |
| `common.db.tables.get_table_name`                 | Utilidad para nombres de tablas                           | Sí                     |
| `common.utils.logging.init_logging`               | Inicialización de logging                                 | Sí                     |
| `common.utils.rate_limiting.setup_rate_limiting`  | Configuración de rate limiting                            | Sí                     |
| `common.auth.verify_tenant`                       | Verificación de autenticidad de tenant                    | Sí                     |
| `common.swagger.configure_swagger_ui`             | Configuración de Swagger UI                               | Sí                     |
| `common.context.with_context`                     | Decorador para inyección de contexto                      | Sí                     |
| `common.context.Context`                          | Contexto multinivel                                       | Sí                     |

**Notas:**
- Todas las importaciones siguen la arquitectura centralizada y las recomendaciones de refactorización.
- Revisar periódicamente la documentación de `common` para mantener las rutas actualizadas.
- Si se detectan funciones no usadas o referencias obsoletas, se marcarán para revisión en `muertasCommon.md`.

Última actualización automática: 2025-04-18
