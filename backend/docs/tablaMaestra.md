# Tabla Maestra de Funciones y Usos del Módulo `common`

Este documento centraliza **todas** las funciones, clases y símbolos exportados en los `__init__.py` de cada submódulo de `common`, indicando claramente:
- Si se usan en algún servicio principal (`agent`, `embedding`, `query`, `ingestion`).
- Dónde se usan (por servicio).
- Si no se usan en ningún servicio (código muerto).

La información se construye a partir de los archivos `usoCommonAllExports.md` (exportaciones) y `usoCommonGeneral.md` (usos reales).

| Módulo      | Símbolo                    | Se Usa | Agent | Embedding | Query | Ingestion | No Usada |
|-------------|----------------------------|:------:|:-----:|:---------:|:-----:|:---------:|:--------:|
| auth        | verify_tenant              |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| auth        | is_tenant_active           |        |       |           |       |           |    ✔     |
| auth        | TenantInfo                 |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| auth        | get_auth_info              |        |       |           |       |           |    ✔     |
| auth        | get_auth_supabase_client   |        |       |           |       |           |    ✔     |
| auth        | with_auth_client           |        |       |           |       |           |    ✔     |
| auth        | AISchemaAccess             |        |       |           |       |           |    ✔     |
| auth        | validate_model_access      |   ✔    |       |           |   ✔   |           |          |
| cache       | CacheManager               |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| cache       | generate_hash              |        |       |           |       |           |    ✔     |
| config      | Settings                   |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| config      | get_settings               |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| config      | invalidate_settings_cache  |   ✔    |   ✔   |           |       |           |          |
| config      | get_service_configurations |        |       |           |       |           |    ✔     |
| config      | get_mock_configurations    |        |       |           |       |           |    ✔     |
| config      | get_tier_limits            |   ✔    |       |           |       |     ✔     |          |
| config      | get_available_llm_models   |        |       |           |       |           |    ✔     |
| config      | get_available_embedding_models | ✔  |       |           |       |     ✔     |          |
| config      | get_tier_rate_limit        |        |       |           |       |           |    ✔     |
| config      | override_settings_from_supabase |  |       |           |       |           |    ✔     |
| context     | get_current_tenant_id      |   ✔    |       |           |   ✔   |     ✔     |          |
| context     | get_required_tenant_id     |        |       |           |       |           |    ✔     |
| context     | get_current_agent_id       |        |       |           |       |           |    ✔     |
| context     | get_current_conversation_id|        |       |           |       |           |    ✔     |
| context     | get_current_collection_id  |   ✔    |       |           |   ✔   |     ✔     |          |
| context     | get_full_context           |        |       |           |       |           |    ✔     |
| context     | debug_context              |        |       |           |       |           |    ✔     |
| context     | set_current_tenant_id      |   ✔    |       |           |   ✔   |           |          |
| context     | set_current_agent_id       |        |       |           |       |           |    ✔     |
| context     | set_current_conversation_id|        |       |           |       |           |    ✔     |
| context     | set_current_collection_id  |        |       |           |       |           |    ✔     |
| context     | reset_context              |        |       |           |       |           |    ✔     |
| context     | Context                    |   ✔    |       |     ✔     |       |           |          |
| context     | ContextTokens              |        |       |           |       |           |    ✔     |
| context     | with_context               |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| context     | extract_context_from_headers|       |       |           |       |           |    ✔     |
| context     | add_context_to_headers     |        |       |           |       |           |    ✔     |
| context     | setup_context_from_headers |        |       |           |       |           |    ✔     |
| context     | run_public_context         |        |       |           |       |           |    ✔     |
| context     | ContextManager             |   ✔    |   ✔   |           |       |           |          |
| context     | validate_tenant_id         |        |       |           |       |           |    ✔     |
| context     | validate_current_tenant    |        |       |           |       |           |    ✔     |
| context     | asynccontextmanager        |        |       |           |       |           |    ✔     |
| db          | get_supabase_client        |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| db          | get_supabase_client_with_token |    |       |           |       |           |    ✔     |
| db          | init_supabase              |        |       |           |       |           |    ✔     |
| db          | get_tenant_configurations  |        |       |           |       |           |    ✔     |
| db          | set_tenant_configuration   |        |       |           |       |           |    ✔     |
| db          | get_effective_configurations|       |       |           |       |           |    ✔     |
| db          | get_table_name             |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| db          | get_table_description      |        |       |           |       |           |    ✔     |
| db          | get_tenant_vector_store    |        |       |           |       |           |    ✔     |
| db          | get_tenant_documents       |        |       |           |       |           |    ✔     |
| db          | get_tenant_collections     |        |       |           |       |           |    ✔     |
| db          | create_conversation        |        |       |           |       |           |    ✔     |
| db          | add_chat_message           |        |       |           |       |           |    ✔     |
| db          | add_chat_history           |        |       |           |       |           |    ✔     |
| db          | ~~increment_token_usage~~ |        |       |           |       |           | ❌ Eliminada |
| db          | increment_document_count   |        |       |           |       |           |    ✔     |
| db          | decrement_document_count   |        |       |           |       |           |    ✔     |
| db          | get_storage_client         |        |       |           |       |           |    ✔     |
| db          | upload_to_storage          |        |       |           |       |           |    ✔     |
| db          | get_file_from_storage      |        |       |           |       |           |    ✔     |
| db          | update_document_counters   |        |       |           |       |           |    ✔     |
| errors      | ServiceError               |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ValidationError            |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ErrorCode                  |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AuthenticationError        |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | PermissionError            |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ResourceNotFoundError      |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | RateLimitError             |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | RateLimitExceeded          |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | QuotaExceededError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ServiceUnavailableError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ExternalApiError           |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | DatabaseError              |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | CacheError                 |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | LlmGenerationError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ModelNotAvailableError     |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | EmbeddingError             |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | DocumentProcessingError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | CollectionError            |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ConversationError          |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentNotFoundError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentInactiveError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentExecutionError        |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentSetupError            |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentToolError             |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentLimitExceededError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | InvalidAgentIdError        |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentAlreadyExistsError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | AgentQuotaExceededError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | QueryProcessingError       |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | CollectionNotFoundError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | RetrievalError             |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | GenerationError            |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | InvalidQueryParamsError    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | EmbeddingGenerationError   |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | EmbeddingModelError        |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | TextTooLargeError          |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | BatchTooLargeError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | InvalidEmbeddingParamsError|   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | ConfigurationError         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| errors      | setup_error_handling       |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | get_llm_model              |   ✔    |       |     ✔     |   ✔   |           |          |
| llm         | get_embedding_model        |   ✔    |       |     ✔     |       |           |          |
| llm         | count_tokens               |   ✔    |   ✔   |           |   ✔   |           |          |
| llm         | BaseEmbeddingModel         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | BaseLLM                    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | GroqLLM                    |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | get_groq_llm_model         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | stream_groq_response       |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | is_groq_model              |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| llm         | get_openai_client          |        |       |           |       |           |    ✔     |
| llm         | get_openai_embedding_model |        |       |           |       |           |    ✔     |
| llm         | OllamaEmbeddings           |        |       |           |       |           |    ✔     |
| llm         | OllamaLLM                  |        |       |           |       |           |    ✔     |
| llm         | is_using_ollama            |        |       |           |       |           |    ✔     |
| models      | TenantInfo                 |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| models      | BaseModel                  |        |       |           |       |           |    ✔     |
| models      | BaseResponse               |        |       |           |       |           |    ✔     |
| models      | ErrorResponse              |        |       |           |       |           |    ✔     |
| models      | HealthResponse             |        |       |           |       |           |    ✔     |
| models      | PublicTenantInfo           |        |       |           |       |           |    ✔     |
| models      | AgentTool                  |        |       |           |       |           |    ✔     |
| models      | AgentConfig                |        |       |           |       |           |    ✔     |
| models      | AgentRequest               |        |       |           |       |           |    ✔     |
| models      | AgentResponse              |        |       |           |       |           |    ✔     |
| models      | AgentSummary               |        |       |           |       |           |    ✔     |
| models      | AgentsListResponse         |        |       |           |       |           |    ✔     |
| models      | DeleteAgentResponse        |        |       |           |       |           |    ✔     |
| models      | CollectionInfo             |        |       |           |       |           |    ✔     |
| models      | CollectionsListResponse    |        |       |           |       |           |    ✔     |
| models      | CollectionToolResponse     |        |       |           |       |           |    ✔     |
| models      | CollectionCreationResponse |        |       |           |       |           |    ✔     |
| models      | CollectionUpdateResponse   |        |       |           |       |           |    ✔     |
| models      | CollectionStatsResponse    |        |       |           |       |           |    ✔     |
| models      | ServiceStatusResponse      |        |       |           |       |           |    ✔     |
| models      | CacheStatsResponse         |        |       |           |       |           |    ✔     |
| models      | CacheClearResponse         |        |       |           |       |           |    ✔     |
| models      | ModelListResponse          |        |       |           |       |           |    ✔     |
| models      | EmbeddingRequest           |        |       |           |       |           |    ✔     |
| models      | EmbeddingResponse          |        |       |           |       |           |    ✔     |
| models      | QueryRequest               |        |       |           |       |           |    ✔     |
| models      | QueryResponse              |        |       |           |       |           |    ✔     |
| swagger     | configure_swagger_ui       |   ✔    |       |     ✔     |   ✔   |           |          |
| swagger     | get_swagger_ui_html        |        |       |           |       |           |    ✔     |
| swagger     | add_example_to_endpoint    |        |       |           |       |           |    ✔     |
| swagger     | generate_docstring_template|        |       |           |       |           |    ✔     |
| tracking    | track_token_usage         |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| tracking    | track_query                |   ✔    |   ✔   |           |   ✔   |           |          |
| tracking    | track_embedding_usage      |   ✔    |       |     ✔     |       |     ✔     |          |
| tracking    | track_usage                |   ✔    |   ✔   |           |   ✔   |           |          |
| tracking    | estimate_request_tokens   |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| utils       | call_service               |   ✔    |   ✔   |     ✔     |   ✔   |     ✔     |          |
| utils       | get_logger                 |        |       |           |       |           |    ✔     |
| utils       | apply_rate_limit           |        |       |           |       |           |    ✔     |
| utils       | setup_rate_limiting        |   ✔    |       |     ✔     |       |           |          |
| utils       | stream_llm_response        |   ✔    |   ✔   |           |       |           |          |

**Leyenda:**
- ✔ en "Se Usa" indica que la función está en uso en al menos un servicio.
- ✔ en un servicio específico indica uso concreto en ese servicio.
- ✔ en "No Usada" indica código muerto/exportado pero no usado.

**Última actualización automática:** 2025-04-18
