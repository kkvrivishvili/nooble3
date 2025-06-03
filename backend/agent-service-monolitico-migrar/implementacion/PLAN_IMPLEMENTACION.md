# Plan de Implementación: Agent Service

Este documento presenta el plan organizado de implementación para el sistema Nooble3, estructurado en bloques funcionales que permiten un desarrollo progresivo y reducen la necesidad de refactorizaciones.

## BLOQUE 1: ARQUITECTURA CORE DEL AGENT SERVICE

### 1. Core del Agent Service [01_AGENT_SERVICE_CORE.md]
- [x] Implementar clase `LangChainAgentService` con inicialización asíncrona
- [x] Desarrollar métodos `create_agent` y `execute_agent` con soporte multitenancy
- [x] Crear `ServiceRegistry` para comunicación segura entre servicios
- [x] Integrar validación de modelos LLM y embedding según tier
- [x] Implementar clase `BaseTool` abstracta con propagación de contexto
- [x] Desarrollar `RAGQueryTool` para consultas a colecciones

#### Mejoras Identificadas para Core
- [x] Refactorizar método `execute_agent` para reducir responsabilidades y mejorar mantenibilidad
- [x] Implementar validación explícita tenant-agente en todos los endpoints
- [x] Mejorar el manejo de concurrencia para ejecuciones simultáneas del mismo agente
- [x] Mejorar la sanitización de entradas en herramientas de API externas
- [x] Agregar pruebas de conectividad para servicios externos antes de ejecutar herramientas

### 2. Sistema de Caché para Agent Service [01_02_AGENT_SERVICE_CACHE.md]
- [x] Implementar `ConversationMemoryManager` para gestión de historiales
- [x] Crear `AgentExecutionStateManager` para estados de ejecución
- [x] Establecer jerarquía de claves multi-nivel (tenant > agent > conversation)
- [x] Implementar sistema de métricas básicas para rendimiento de caché
- [x] Optimizar patrón Cache-Aside para datos persistentes

#### Mejoras Identificadas para Caché
- [x] Estandarizar formato de claves de caché en todo el servicio (eliminar inconsistencias)
   - [x] Auditar uso actual de claves vs. patrón estandarizado en common/cache/manager.py
   - [x] Refactorizar llamadas directas a CacheManager por get_with_cache_aside
   - [x] Documentar patrón de claves implementado
- [x] Migrar a TTLs centralizados definidos en common/core/constants.py
   - [x] Reemplazar valores hardcodeados por constantes TTL_SHORT, TTL_STANDARD, TTL_EXTENDED
   - [x] Verificar que los tipos de datos nuevos sigan DEFAULT_TTL_MAPPING
   - [x] Unificar mecanismo de extensión de TTL para objetos frecuentes
- [x] Implementar invalidación en cascada para cachés relacionadas
   - [x] Identificar dependencias entre objetos cacheados (ej: agente -> herramientas -> memoria)
   - [x] Crear método centralizado de invalidación que maneje las dependencias
   - [x] Integrar con sistema de tracking para monitorear patrones de invalidación
- [x] Añadir monitoreo de tamaño de objetos en caché
   - [x] Implementar estimación de tamaño en _track_cache_size
   - [x] Configurar umbrales de alerta para objetos grandes
   - [x] Integrar con sistema centralizado de métricas
- [ ] Implementar pre-calentamiento de caché para recursos frecuentemente accedidos
   - [ ] Diseñar mecanismo de identificación de recursos frecuentes basado en métricas
   - [ ] Implementar carga asincrónica de objetos frecuentes
   - [ ] Agregar soporte para invalidación coordinada entre instancias

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
