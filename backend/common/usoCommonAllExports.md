# Funciones y Clases Exportadas en los __init__.py de `common`

Este documento lista **todas** las funciones, clases y símbolos exportados explícitamente en los `__init__.py` de cada submódulo de `common`. Útil para comparar con el uso real en los servicios (`usoCommonGeneral.md`).

| Módulo                  | Símbolo exportado                    | Tipo/Descripción breve                |
|-------------------------|--------------------------------------|---------------------------------------|
| **auth**                | verify_tenant                        | Verificación de tenant                |
|                         | is_tenant_active                     | Estado de tenant                      |
|                         | TenantInfo                           | Modelo de tenant                      |
|                         | get_auth_info                        | Info de autenticación                 |
|                         | get_auth_supabase_client             | Cliente supabase autenticado          |
|                         | with_auth_client                     | Decorador de cliente auth             |
|                         | AISchemaAccess                       | Acceso a esquema AI                   |
|                         | validate_model_access                | Validación de acceso a modelos        |
| **cache**               | CacheManager                         | Gestor de caché                       |
|                         | generate_hash                        | Generación de hash para caché         |
| **config**              | Settings                             | Modelo de settings                    |
|                         | get_settings                         | Obtener configuración                 |
|                         | invalidate_settings_cache             | Limpiar caché de settings             |
|                         | get_service_configurations           | Configuración de servicios            |
|                         | get_mock_configurations              | Mock de configuraciones               |
|                         | get_tier_limits                      | Límites por tier                      |
|                         | get_available_llm_models             | Modelos LLM por tier                  |
|                         | get_available_embedding_models        | Modelos embedding por tier            |
|                         | get_tier_rate_limit                  | Rate limit por tier                   |
|                         | override_settings_from_supabase       | Override de settings                  |
| **context**             | get_current_tenant_id                | Getter de tenant actual               |
|                         | get_required_tenant_id               | Getter obligatorio de tenant          |
|                         | get_current_agent_id                 | Getter de agent actual                |
|                         | get_current_conversation_id           | Getter de conversación actual         |
|                         | get_current_collection_id            | Getter de colección actual            |
|                         | get_full_context                     | Contexto completo                     |
|                         | debug_context                        | Debug de contexto                     |
|                         | set_current_tenant_id                | Setter de tenant actual               |
|                         | set_current_agent_id                 | Setter de agent actual                |
|                         | set_current_conversation_id           | Setter de conversación actual         |
|                         | set_current_collection_id            | Setter de colección actual            |
|                         | reset_context                        | Reset de contexto                     |
|                         | Context                              | Clase de contexto                     |
|                         | ContextTokens                        | Tokens de contexto                    |
|                         | with_context                         | Decorador de contexto                 |
|                         | extract_context_from_headers          | Extraer contexto de headers           |
|                         | add_context_to_headers                | Añadir contexto a headers             |
|                         | setup_context_from_headers            | Setup de contexto desde headers       |
|                         | run_public_context                   | Contexto público                      |
|                         | ContextManager                       | Gestor avanzado de contexto           |
|                         | validate_tenant_id                   | Validación de tenant                  |
|                         | validate_current_tenant              | Validación de tenant actual           |
|                         | asynccontextmanager                   | Context manager asíncrono             |
| **db**                  | get_supabase_client                   | Cliente supabase                      |
|                         | get_supabase_client_with_token        | Cliente supabase con token            |
|                         | init_supabase                        | Inicializar supabase                  |
|                         | get_tenant_configurations             | Configuración de tenant               |
|                         | set_tenant_configuration              | Set configuración de tenant           |
|                         | get_effective_configurations          | Configuración efectiva                 |
|                         | get_table_name                        | Nombre de tabla                       |
|                         | get_table_description                 | Descripción de tabla                  |
|                         | get_tenant_vector_store               | Vector store de tenant                |
|                         | get_tenant_documents                  | Documentos de tenant                  |
|                         | get_tenant_collections                | Colecciones de tenant                 |
|                         | create_conversation                   | Crear conversación                    |
|                         | add_chat_message                      | Agregar mensaje                       |
|                         | add_chat_history                      | Agregar historial                     |
|                         | increment_token_usage                  | Incrementar tokens                    |
|                         | increment_document_count               | Incrementar documentos                |
|                         | decrement_document_count               | Decrementar documentos                |
|                         | get_storage_client                     | Cliente de storage                    |
|                         | upload_to_storage                      | Subir a storage                       |
|                         | get_file_from_storage                  | Obtener archivo de storage            |
|                         | update_document_counters               | Actualizar contadores de docs         |
| **errors**              | ErrorCode                              | Código de error                       |
|                         | ServiceError                           | Error de servicio                     |
|                         | ValidationError                        | Error de validación                   |
|                         | AuthenticationError                    | Error de autenticación                |
|                         | PermissionError                        | Error de permisos                     |
|                         | ResourceNotFoundError                  | No encontrado                         |
|                         | RateLimitError                         | Error de rate limit                   |
|                         | RateLimitExceeded                      | Rate limit excedido                   |
|                         | QuotaExceededError                     | Cuota excedida                        |
|                         | ServiceUnavailableError                | Servicio no disponible                |
|                         | ExternalApiError                       | Error API externa                     |
|                         | DatabaseError                          | Error de base de datos                |
|                         | CacheError                             | Error de caché                        |
|                         | LlmGenerationError                     | Error generación LLM                  |
|                         | ModelNotAvailableError                  | Modelo no disponible                  |
|                         | EmbeddingError                         | Error de embedding                    |
|                         | DocumentProcessingError                 | Error procesamiento de doc            |
|                         | CollectionError                        | Error de colección                    |
|                         | ConversationError                      | Error de conversación                 |
|                         | AgentNotFoundError                     | Agent no encontrado                   |
|                         | AgentInactiveError                     | Agent inactivo                        |
|                         | AgentExecutionError                    | Error ejecución agent                 |
|                         | AgentSetupError                        | Error setup agent                     |
|                         | AgentToolError                         | Error de tool agent                   |
|                         | AgentLimitExceededError                | Límite de agent excedido              |
|                         | InvalidAgentIdError                    | Agent ID inválido                     |
|                         | AgentAlreadyExistsError                | Agent ya existe                       |
|                         | AgentQuotaExceededError                | Cuota de agent excedida               |
|                         | QueryProcessingError                   | Error procesamiento de query          |
|                         | CollectionNotFoundError                | Colección no encontrada               |
|                         | RetrievalError                         | Error de retrieval                    |
|                         | GenerationError                        | Error de generación                   |
|                         | InvalidQueryParamsError                | Params de query inválidos             |
|                         | EmbeddingGenerationError               | Error generación embedding            |
|                         | EmbeddingModelError                    | Error de modelo embedding             |
|                         | TextTooLargeError                      | Texto muy grande                      |
|                         | BatchTooLargeError                     | Batch muy grande                      |
|                         | InvalidEmbeddingParamsError            | Params embedding inválidos            |
|                         | ConfigurationError                     | Error de configuración                |
|                         | setup_error_handling                   | Setup de manejo de errores            |
| **llm**                 | BaseEmbeddingModel                     | Modelo base embedding                 |
|                         | BaseLLM                                | Modelo base LLM                       |
|                         | get_openai_client                      | Cliente OpenAI                        |
|                         | get_openai_embedding_model             | Modelo embedding OpenAI               |
|                         | OllamaEmbeddings                       | Embeddings Ollama                     |
|                         | OllamaLLM                              | LLM Ollama                            |
|                         | get_embedding_model                    | Obtener modelo embedding              |
|                         | get_llm_model                          | Obtener modelo LLM                    |
|                         | is_using_ollama                        | Usa Ollama                            |
|                         | count_tokens                           | Contar tokens                         |
|                         | count_message_tokens                   | Contar tokens en mensajes             |
|                         | estimate_max_tokens_for_model          | Estimar tokens máx. modelo            |
|                         | estimate_remaining_tokens              | Estimar tokens restantes              |
|                         | stream_openai_response                 | Streaming respuesta OpenAI            |
|                         | stream_ollama_response                 | Streaming respuesta Ollama            |
| **models**              | BaseModel                              | Modelo base                           |
|                         | BaseResponse                           | Respuesta base                        |
|                         | ErrorResponse                          | Respuesta de error                    |
|                         | HealthResponse                         | Respuesta de salud                    |
|                         | TenantInfo                             | Info de tenant                        |
|                         | PublicTenantInfo                       | Info pública de tenant                |
|                         | AgentTool                              | Herramienta agent                     |
|                         | AgentConfig                            | Configuración agent                   |
|                         | AgentRequest                           | Request de agent                      |
|                         | AgentResponse                          | Respuesta de agent                    |
|                         | AgentSummary                           | Resumen de agent                      |
|                         | AgentsListResponse                     | Lista de agents                       |
|                         | DeleteAgentResponse                    | Respuesta de borrado de agent         |
|                         | CollectionInfo                         | Info de colección                     |
|                         | CollectionsListResponse                | Lista de colecciones                  |
|                         | CollectionToolResponse                 | Herramienta de colección              |
|                         | CollectionCreationResponse             | Creación de colección                 |
|                         | CollectionUpdateResponse               | Actualización de colección            |
|                         | CollectionStatsResponse                | Stats de colección                    |
|                         | ServiceStatusResponse                  | Estado de servicio                    |
|                         | CacheStatsResponse                     | Stats de caché                        |
|                         | CacheClearResponse                     | Limpieza de caché                     |
|                         | ModelListResponse                      | Lista de modelos                      |
|                         | EmbeddingRequest                       | Request de embedding                  |
|                         | EmbeddingResponse                      | Respuesta de embedding                |
|                         | QueryRequest                           | Request de query                      |
|                         | QueryResponse                          | Respuesta de query                    |
| **swagger**             | configure_swagger_ui                   | Configuración Swagger                 |
|                         | get_swagger_ui_html                    | HTML de Swagger UI                    |
|                         | add_example_to_endpoint                | Ejemplo para endpoint                 |
|                         | generate_docstring_template            | Plantilla de docstring                |
| **tracking**            | track_token_usage                      | Tracking de tokens                    |
|                         | track_query                            | Tracking de queries                   |
|                         | track_embedding_usage                  | Tracking de embeddings                |
|                         | track_usage                            | Tracking general                      |
|                         | estimate_prompt_tokens                 | Estimar tokens de prompt              |
| **utils**               | call_service                           | Llamada HTTP                          |
|                         | init_logging                           | Inicializar logging                   |
|                         | get_logger                             | Obtener logger                        |
|                         | apply_rate_limit                       | Aplicar rate limit                    |
|                         | setup_rate_limiting                    | Configurar rate limiting              |
|                         | stream_llm_response                    | Streaming de LLM                      |

**Notas:**
- Esta tabla se genera a partir de los símbolos exportados explícitamente en los `__init__.py` de cada submódulo de `common`.
- Puedes comparar esta lista con el uso real en `usoCommonGeneral.md` para detectar funciones no usadas o faltantes.
- Última actualización automática: 2025-04-18
