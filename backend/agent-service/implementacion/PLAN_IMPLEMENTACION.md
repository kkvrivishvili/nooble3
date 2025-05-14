# Plan de Implementación: Agent Service

Este documento presenta el plan organizado de implementación para el sistema Nooble3, estructurado en bloques funcionales que permiten un desarrollo progresivo y reducen la necesidad de refactorizaciones.

## BLOQUE 1: ARQUITECTURA CORE DEL AGENT SERVICE

### 1. Core del Agent Service [01_AGENT_SERVICE_CORE.md]
- [ ] Implementar clase `LangChainAgentService` con inicialización asíncrona
- [ ] Desarrollar métodos `create_agent` y `execute_agent` con soporte multitenancy
- [ ] Crear `ServiceRegistry` para comunicación segura entre servicios
- [ ] Integrar validación de modelos LLM y embedding según tier
- [ ] Implementar clase `BaseTool` abstracta con propagación de contexto
- [ ] Desarrollar `RAGQueryTool` para consultas a colecciones

### 2. Sistema de Caché para Agent Service [01_02_AGENT_SERVICE_CACHE.md]
- [ ] Implementar `ConversationMemoryManager` para gestión de historiales
- [ ] Crear `AgentExecutionStateManager` para estados de ejecución
- [ ] Establecer jerarquía de claves multi-nivel (tenant > agent > conversation)
- [ ] Implementar sistema de métricas para rendimiento de caché
- [ ] Desarrollar métodos de invalidación selectiva para coherencia de datos
- [ ] Optimizar patrón Cache-Aside para datos persistentes

### 3. Estrategia de Colecciones [04_COLLECTION_STRATEGY.md]
- [ ] Implementar `CollectionStrategy` para selección inteligente de fuentes
- [ ] Actualizar `RAGQueryTool` para integración con strategy
- [ ] Desarrollar soporte para federación automática de colecciones
- [ ] Implementar selección contextual basada en consulta

## BLOQUE 2: OPTIMIZACIÓN DE SERVICIOS EXTERNOS

### 4. Refactorización del Query Service [02_QUERY_SERVICE_REFACTOR.md]
- [ ] Actualizar modelos de datos (InternalQueryRequest, InternalQueryResponse)
- [ ] Refactorizar `create_query_engine` para aceptar embeddings pre-generados
- [ ] Optimizar endpoints internos `/internal/query` y `/internal/search`
- [ ] Implementar factory de LLM `create_llm_for_queries` para Groq
- [ ] Eliminar dependencias directas con Embedding Service
- [ ] Integrar tracking de tokens y métricas de rendimiento

### 5. Optimización del Embedding Service [03_EMBEDDING_SERVICE_OPTIMIZE.md]
- [ ] Actualizar `provider/openai.py` con tracking mejorado
- [ ] Optimizar endpoints internos `/internal/embed` y `/internal/batch`
- [ ] Implementar sistema de métricas detalladas para embeddings
- [ ] Desarrollar `get_embedding_with_cache()` usando Cache-Aside
- [ ] Implementar serialización especializada para embeddings
- [ ] Eliminar endpoints públicos (excepto /health)
- [ ] Implementar procesamiento por lotes con concurrencia controlada

## BLOQUE 3: CAPACIDADES AVANZADAS

### 6. Sistema Multi-Agente [06_MULTI_AGENT_SYSTEM.md]
- [ ] Implementar `AgentOrchestrator` para coordinación entre agentes
- [ ] Desarrollar `ConsultAgentTool` para comunicación entre agentes
- [ ] Crear `TeamAgentExecutor` con integración de LangChain Team
- [ ] Implementar `SpecializedAgentFactory` para agentes temáticos
- [ ] Desarrollar endpoints para ejecuciones multi-agente
- [ ] Implementar ejecución secuencial y paralela de agentes
- [ ] Crear roles predefinidos (investigador, redactor, analista)

### 7. Sistema de Colas de Trabajo [07_WORK_QUEUE_SYSTEM.MD]
- [ ] Integrar Celery y RabbitMQ para procesamiento asíncrono
- [ ] Implementar decorador `create_context_task` para preservar contexto
- [ ] Desarrollar `WebSocketManager` para notificaciones en tiempo real
- [ ] Crear `WorkQueueService` para gestión de trabajos
- [ ] Implementar endpoints para crear, monitorear y cancelar trabajos
- [ ] Configurar colas por tipo de trabajo (agent, query, embedding)
- [ ] Establecer políticas de reintentos y timeouts

## BLOQUE 4: INTEGRACIONES

### 8. Integración con Frontend [05_FRONTEND_INTEGRATION.md]
- [ ] Desarrollar modelos de solicitud (ExecuteAgentRequest, ConfigureAgentRequest)
- [ ] Crear modelos de respuesta (AgentExecutionResponse, AgentConfigurationResponse)
- [ ] Implementar endpoints para ejecución con streaming o asíncrono
- [ ] Desarrollar endpoints para administración de agentes
- [ ] Implementar validación de tier y permisos para modelos
- [ ] Crear componentes React (chat, selectores, visualizador)
- [ ] Desarrollar soporte para los tres modos de ejecución

### 9. Integración de Metadatos [08_METADATA_INTEGRATION.md]
- [ ] Implementar función `standardize_langchain_metadata` para compatibilidad
- [ ] Crear adaptador para RAGQueryTool con metadatos estandarizados
- [ ] Actualizar LangChainAgentService para mantener consistencia
- [ ] Implementar sistema bidireccional LlamaIndex/LangChain
- [ ] Estandarizar campos (tenant_id, agent_id, conversation_id, collection_id)
- [ ] Desarrollar validación y enriquecimiento automático de metadatos

## Dependencias entre bloques

- El BLOQUE 1 debe completarse primero, ya que establece la arquitectura core
- Los componentes del BLOQUE 2 pueden desarrollarse en paralelo, pero dependen del BLOQUE 1
- El BLOQUE 3 depende de que se complete el BLOQUE 1, pero es independiente del BLOQUE 2
- El BLOQUE 4 debe implementarse al final, cuando los demás bloques estén operativos

## Priorización recomendada

1. Implementar primero los componentes esenciales del Core (BLOQUE 1)
2. Proceder con la optimización de servicios externos (BLOQUE 2)
3. Desarrollar capacidades avanzadas (BLOQUE 3)
4. Finalizar con las integraciones (BLOQUE 4)

Esta estructura permite un desarrollo incremental, donde cada fase construye sobre la anterior y minimiza la necesidad de cambios a componentes ya implementados.
