# Reporte Detallado de Uso y Exportación de Funciones del Módulo `common`

## 1. Objetivo y Alcance
Este documento analiza **en profundidad** el uso real y la oferta de funciones, clases y utilidades del módulo `common` en todos los servicios principales del proyecto. Permite detectar inconsistencias, código muerto, duplicidades y oportunidades de refactorización.

---

## 2. Fuentes Analizadas
- **usoCommonGeneral.md**: Uso real de funciones de `common` en los servicios (`agent`, `embedding`, `query`, `ingestion`).
- **usoCommonAllExports.md**: Todas las funciones/clases exportadas explícitamente en los `__init__.py` de cada submódulo de `common`.

---

## 3. Tabla Maestra: Exportado vs Usado

| Símbolo/Módulo                      | Exportado | Agent | Embedding | Query | Ingestion | Observaciones |
|-------------------------------------|:---------:|:-----:|:---------:|:-----:|:---------:|--------------|
| get_settings                        |    ✔      |   ✔   |     ✔     |   ✔   |     ✔     | Uso transversal |
| invalidate_settings_cache           |    ✔      |   ✔   |           |       |           | Solo Agent |
| CacheManager                        |    ✔      |   ✔   |     ✔     |   ✔   |     ✔     | Uso transversal |
| generate_hash                       |    ✔      |       |           |       |           | **No usado** |
| verify_tenant                       |    ✔      |   ✔   |     ✔     |   ✔   |     ✔     | Uso transversal |
| is_tenant_active                    |    ✔      |       |           |       |           | **No usado** |
| get_auth_info                       |    ✔      |       |           |       |           | **No usado** |
| get_auth_supabase_client            |    ✔      |       |           |       |           | **No usado** |
| with_auth_client                    |    ✔      |       |           |       |           | **No usado** |
| AISchemaAccess                      |    ✔      |       |           |       |           | **No usado** |
| validate_model_access               |    ✔      |       |           |   ✔   |           | Uso en Query |
| ...                                 | ...      | ...   | ...       | ...   | ...       | ... |
| get_logger                          |    ✔      |       |           |       |           | **No usado** |
| apply_rate_limit                    |    ✔      |       |           |       |           | **No usado** |
| ...                                 | ...      | ...   | ...       | ...   | ...       | ... |

**Nota:** Las tablas completas y desglosadas están en los archivos fuente.

---

## 4. Listado Exhaustivo de Funciones Exportadas pero NO Usadas (Código Muerto)

- **auth:** is_tenant_active, get_auth_info, get_auth_supabase_client, with_auth_client, AISchemaAccess
- **cache:** generate_hash
- **config:** get_service_configurations, get_mock_configurations, override_settings_from_supabase, get_tier_rate_limit
- **context:** get_required_tenant_id, get_current_agent_id, get_current_conversation_id, debug_context, set_current_agent_id, set_current_conversation_id, reset_context, ContextTokens, extract_context_from_headers, add_context_to_headers, setup_context_from_headers, run_public_context, validate_tenant_id, validate_current_tenant, asynccontextmanager
- **db:** get_supabase_client_with_token, init_supabase, get_tenant_configurations, set_tenant_configuration, get_effective_configurations, get_table_description, get_tenant_vector_store, get_tenant_documents, get_tenant_collections, create_conversation, add_chat_message, add_chat_history, increment_token_usage, increment_document_count, decrement_document_count, get_storage_client, update_document_counters
- **llm:** BaseEmbeddingModel, BaseLLM, get_openai_client, get_openai_embedding_model, OllamaEmbeddings, OllamaLLM, is_using_ollama, count_message_tokens, estimate_max_tokens_for_model, estimate_remaining_tokens, stream_openai_response, stream_ollama_response
- **models:** La mayoría de los modelos específicos de respuesta no son usados en todos los servicios.
- **swagger:** get_swagger_ui_html, add_example_to_endpoint, generate_docstring_template
- **tracking:** estimate_prompt_tokens
- **utils:** get_logger, apply_rate_limit

---

## 5. Funciones Usadas pero NO Exportadas
No se detectan funciones usadas que no estén exportadas en los `__init__.py` de los submódulos. **Consistencia total.**

---

## 6. Consistencia y Buenas Prácticas
- **Separación de responsabilidades:** Cumplida (ver memorias de refactorización de tiers, modelos y tracking).
- **Single Source/Implementation:** Cumplido para configuraciones, validación y tracking.
- **Importaciones:** Se recomienda importar SIEMPRE desde los paths oficiales (`common.config.tiers`, `common.auth`, `common.tracking`).

---

## 7. Diferencias de Uso entre Servicios
- **Agent:** Uso intensivo de helpers de contexto, tracking y streaming.
- **Embedding:** Enfocado en embeddings, logging y rate limiting.
- **Query:** Validación de modelos, contexto avanzado y tracking de queries.
- **Ingestion:** Contexto, utilidades de tier y tracking de embeddings.

---

## 8. Recomendaciones de Mantenimiento
- **Limpiar exports:** Eliminar funciones nunca usadas o mover a helpers internos.
- **Documentar helpers avanzados:** Si se mantienen, indicar claramente su propósito y si son solo para uso interno.
- **Actualizar periódicamente:** Mantener sincronizados los archivos de uso y exportación.
- **Revisar dependencias:** Evitar dependencias circulares y mantener la arquitectura modular.

---

## 9. Acciones Sugeridas
- Generar/actualizar `muertasCommon.md` con todas las funciones exportadas pero no usadas.
- Revisar con el equipo si alguna función "muerta" debe mantenerse como API interna o eliminarse.
- Mantener este reporte como referencia viva para futuras refactorizaciones.

---

## 10. Anexos
- [usoCommonGeneral.md](usoCommonGeneral.md): Uso real en servicios.
- [usoCommonAllExports.md](usoCommonAllExports.md): Exportaciones disponibles.
- [muertasCommon.md](muertasCommon.md): Código muerto detectado.

---

**Última actualización automática:** 2025-04-18
