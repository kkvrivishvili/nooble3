# Índice de Implementación: Agent Service

Este directorio contiene los planes detallados de implementación del sistema, organizados para minimizar refactorizaciones y completar el Agent Service antes de expandir a otros componentes.

## BLOQUE 1: CORE DEL AGENT SERVICE

### 1. [Core del Agent Service](01_AGENT_SERVICE_CORE.md)
   - **Componentes implementados**:
     - Clase LangChainAgentService con inicialización asíncrona
     - Métodos create_agent y execute_agent con soporte multitenancy
     - ServiceRegistry para comunicación segura entre servicios
     - Integración con sistema de tier (free, pro, business, enterprise)
     - Validación de modelos LLM y embedding según tier
     - BaseTool abstracta con propagación de contexto
     - RAGQueryTool para consultas a colecciones
   - **Características principales**:
     - Soporte para ejecución asíncrona vía sistema de colas
     - Selección dinámica de colecciones (explicita y federada)
     - Integración con Context para validación de tenant_id, agent_id, conversation_id
     - Sistema de delegación a agentes especializados
     - Manejo de errores unificado con @handle_errors
   - **Integraciones**:
     - Con Embedding Service para generación de embeddings
     - Con Query Service para consultas RAG
     - Con sistema de caché centralizado (patrón Cache-Aside)
   - **Estructura de datos clave**:
     - agent_registry: Dict[tenant_id, Dict[agent_id, agent_config]]
     - AgentConfig: configuración del agente (modelo, herramientas, etc.)
     - AgentResponse: modelo de respuesta estandarizado
   - **Impacto**: Implementación inicial - cambios mínimos
   - **Dependencias**: common/context, common/errors, common/cache
   - **Servicios afectados**: Agent Service (principal), Query Service, Embedding Service (secundarios)

### 2. [Sistema de Caché para Agent Service](01_02_AGENT_SERVICE_CACHE.md)
   - **Componentes implementados**:
     - ConversationMemoryManager para gestión eficiente de historiales
     - AgentExecutionStateManager para estados de ejecución
     - Jerarquía de claves multi-nivel (tenant > agent > conversation)
     - Sistema de métricas para monitoreo de rendimiento de caché
     - Métodos de invalidación selectiva para coherencia de datos
   - **Patrones específicos**:
     - Distinción clara entre uso de métodos estáticos/instancia de CacheManager
     - Implementación optimizada del patrón Cache-Aside para datos persistentes
     - Operaciones directas para datos temporales o proporcionados por el frontend
     - Métodos especializados para listas con get_instance().rpush/lpop
     - Segregación por TTL (standard, short, extended) según el tipo de dato
   - **TTLs recomendados por tipo**:
     - agent_config: ttl_standard (1 hora) - Configuraciones de agentes
     - conversation_memory: ttl_extended (24 horas) - Memoria de conversación
     - agent_tools: ttl_standard (1 hora) - Herramientas disponibles
     - agent_execution_state: ttl_short (5 min) - Estados temporales
   - **Integración futura**:
     - Compatibilidad diseñada para sistema de colas (Fase 7)
     - Soporte para notificaciones WebSocket de cambios de estado
   - **Impacto**: Extensión natural del core - cambios mínimos
   - **Dependencias**: common/cache, 01_AGENT_SERVICE_CORE
   - **Servicios afectados**: Agent Service

### 3. [Estrategia de Colecciones](04_COLLECTION_STRATEGY.md)
   - **Componentes implementados**:
     - CollectionStrategy para selección de fuentes
     - Actualizaciones a RAGQueryTool
     - Integración con Agent Service para consultas contextuales
     - Soporte para federación de colecciones
   - **Impacto**: Extensión de funcionalidad - cambios medios
   - **Dependencias**: 01_AGENT_SERVICE_CORE, common/context

## BLOQUE 2: OPTIMIZACIÓN DE SERVICIOS BASE

### 4. [Refactorización del Query Service](02_QUERY_SERVICE_REFACTOR.md)
   - **Componentes implementados**:
     - Modelos de datos actualizados (InternalQueryRequest, InternalQueryResponse)
     - Método `create_query_engine` refactorizado para aceptar embeddings pre-generados
     - Endpoints internos `/internal/query` y `/internal/search` optimizados
     - Factory de LLM `create_llm_for_queries` para garantizar uso exclusivo de Groq
   - **Características principales**:
     - Eliminación de dependencias directas con el Embedding Service
     - Soporte para embeddings pre-generados desde el Agent Service
     - Integración con sistema de tracking de tokens y métricas
     - Implementación de factory para asegurar uso de Groq como proveedor LLM
     - Patrones de error estandarizados con decorador @handle_errors
   - **Patrones específicos**:
     - Separación clara de responsabilidades según arquitectura de microservicios
     - Uso del patrón Cache-Aside para vector stores y resultados de consultas
     - Validación de contexto con decorador @with_context
     - Factory method para creación de instancias LLM
   - **Metadatos y tracking**:
     - Seguimiento de origen de solicitudes para análisis
     - Métricas de rendimiento de consultas (tokens, tiempo, fuentes)
     - Registro de uso de embeddings pre-generados vs. generados
   - **Impacto**: Refactorización estructural - cambios significativos
   - **Dependencias**: common/context, common/errors, common/config/tiers, common/cache
   - **Servicios afectados**: Query Service (principal), Agent Service (para integración)

### 5. [Optimización del Embedding Service](03_EMBEDDING_SERVICE_OPTIMIZE.md)
   - **Componentes implementados**:
     - Actualización de `provider/openai.py` con tracking mejorado
     - Endpoints internos `/internal/embed` y `/internal/batch` optimizados
     - Sistema de métricas detalladas para generación de embeddings
     - Implementación de `get_embedding_with_cache()` usando el patrón Cache-Aside
   - **Características principales**:
     - Uso exclusivo de OpenAI para generación de embeddings
     - Tracking detallado de tokens con integración del sistema centralizado
     - Caché optimizada con TTL extendido (24 horas) para embeddings
     - Eliminación de endpoints públicos (excepto /health)
     - Procesamiento por lotes con concurrencia controlada
   - **Patrones específicos**:
     - Implementación rigurosa del patrón Cache-Aside estándar
     - Uso de hash MD5 para identificación de textos
     - Serialización especializada para embeddings
     - Propagación de contexto y metadatos enriquecidos
   - **Métricas y tracking**:
     - Registro de tiempo de generación de embeddings (ms)
     - Cálculo de eficiencia de tokens (tokens/carácter)
     - Seguimiento detallado de origen del conteo de tokens (API vs estimado)
     - Monitoreo de tasa de éxito en procesamiento por lotes
   - **Impacto**: Optimización de rendimiento - cambios medios
   - **Dependencias**: common/tracking, common/cache, common/context, common/errors 
   - **Servicios afectados**: Embedding Service (principal), Agent Service (para integración)

### 6. [Sistema de Colas de Trabajo](07_WORK_QUEUE_SYSTEM.MD)
   - **Componentes implementados**:
     - Integración Celery y RabbitMQ para procesamiento asíncrono
     - Decorador `create_context_task` para preservar contexto multitenancy
     - `WebSocketManager` para notificaciones en tiempo real
     - `WorkQueueService` para gestión de trabajos y estados
     - Endpoints para crear, monitorear y cancelar trabajos
   - **Características principales**:
     - Comunicación asíncrona entre el frontend y backend
     - Notificaciones en tiempo real vía WebSockets
     - Preservación completa del contexto multitenancy entre procesos
     - Control granular de colas por tipo de trabajo y servicio
     - Integración con sistema de caché para resultados persistentes
   - **Patrones específicos**:
     - Cola prioritaria para tareas críticas
     - Patrón Singleton para gestores de WebSocket y colas
     - Patrón Publisher-Subscriber para notificaciones
     - Sistema de idempotencia para operaciones críticas
     - Generación consistente de claves de caché para resultados
   - **Configuración y despliegue**:
     - Diferentes colas para distintos tipos de tareas
     - Políticas de reintentos y timeouts específicos por operación
     - Alta disponibilidad con clúster de RabbitMQ
     - Aislamiento por entorno con colas virtuales
   - **Impacto**: Nueva infraestructura - cambios significativos
   - **Dependencias**: common/cache, common/context, common/config, common/utils/metrics
   - **Servicios afectados**: Todos los servicios del backend, Fronted (integración WebSocket)

### 7. [Sistema Multi-Agente](06_MULTI_AGENT_SYSTEM.md)
   - **Componentes implementados**:
     - `AgentOrchestrator` para coordinación y ejecución de múltiples agentes
     - `ConsultAgentTool` para comunicación entre agentes
     - `TeamAgentExecutor` con integración de LangChain Team
     - `SpecializedAgentFactory` para creación de agentes temáticos predefinidos
     - Endpoints para ejecuciones multi-agente con contexto compartido
   - **Características principales**:
     - Ejecución secuencial de agentes (pipeline de procesamiento)
     - Ejecución paralela con consolidación de resultados
     - Agentes especializados con roles predefinidos (investigador, redactor, analista)
     - Propagación automática de contexto multitenancy
     - Integración opcional con sistema de colas para tareas asíncronas
   - **Patrones específicos**:
     - Patrón Factory para creación de agentes especializados
     - Patrón Orquestador para coordinación entre agentes
     - Patrón Adaptador para integración con LangChain Team
     - Separación de configuración y ejecución de agentes
     - Templates preconstruidos para equipos comunes
   - **Mejoras sobre soluciones existentes**:
     - Preservación completa del contexto multitenancy entre agentes
     - Supervisión centralizada y gestión de errores uniforme
     - Agentes capaces de consultar a otros agentes especialistas
     - Compatibilidad con sistemas de colas y webSockets (Fase 7)
   - **Impacto**: Nueva funcionalidad avanzada - cambios significativos
   - **Dependencias**: 01_AGENT_SERVICE_CORE, common/context, common/errors
   - **Servicios afectados**: Agent Service (principal)

### 8. [Integración con Frontend](05_FRONTEND_INTEGRATION.md)
   - **Componentes implementados**:
     - Modelos de solicitud (ExecuteAgentRequest, ConfigureAgentRequest)
     - Modelos de respuesta (AgentExecutionResponse, AgentConfigurationResponse)
     - Endpoints para ejecución de agentes con streaming o asíncrono
     - Endpoints para administración de agentes (configuración, lista, eliminación)
   - **Características principales**:
     - Soporte para streaming de respuestas en tiempo real
     - Integración con sistema de colas para operaciones largas
     - Control granular de configuraciones de agentes
     - Validación de tier y permisos para modelos avanzados
     - Componentes React optimizados para experiencia fluida
   - **Soporte de modos de ejecución**:
     - **Estándar**: Ejecución síncrona con respuesta completa
     - **Streaming**: Envío de respuesta por partes a medida que se genera
     - **Asíncrono**: Soporte para operaciones largas vía WebSockets
   - **Componentes clave del frontend**:
     - Componente de chat optimizado para streaming
     - Selectores de colección y modelos según tier
     - Visualizador de fuentes RAG con filtros
     - Dashboard de métricas de agentes y ejecuciones
   - **Impacto**: Extensión de usabilidad - cambios medios
   - **Dependencias**: 01_AGENT_SERVICE_CORE, 07_WORK_QUEUE_SYSTEM, common/context
   - **Servicios afectados**: Agent Service, Frontend (React)

### 9. [Integración de Metadatos](08_METADATA_INTEGRATION.md)
   - **Componentes implementados**:
     - Función centralizada `standardize_langchain_metadata` para compatibilidad
     - Adaptador para RAGQueryTool con soporte de metadatos estandarizados
     - Actualización de LangChainAgentService para mantener consistencia
     - Sistema de compatibilidad bidireccional para LlamaIndex y LangChain
   - **Características principales**:
     - Traducción automática de metadatos entre frameworks
     - Preservación de información relevante entre servicios
     - Reutilización de estándares existentes para minimizar duplicación
     - Soporte mejorado para depuración y trazabilidad entre servicios
     - Validación y enriquecimiento automático de metadatos
   - **Campos estandarizados**:
     - `tenant_id`: ID del tenant (obligatorio en todos los metadatos)
     - `agent_id`: ID del agente para servicios de LangChain
     - `conversation_id`: ID de la conversación para mantener contexto
     - `collection_id`: ID de la colección para compatible con LlamaIndex
     - `source_framework`: Origen del metadato (langchain o llamaindex)
   - **Impacto**: Integración entre frameworks - cambios medios
   - **Dependencias**: common/cache, common/langchain, common/context
   - **Servicios afectados**: Agent Service, Query Service, Embedding Service

## BLOQUE 2: OPTIMIZACIÓN DE SERVICIOS BASE

### 6. [Sistema de Colas de Trabajo](07_WORK_QUEUE_SYSTEM.md)
   - **Componentes implementados**:
     - Infraestructura con Celery y RabbitMQ
     - WorkQueueService para gestión de tareas asíncronas
     - WebSocketManager para notificaciones en tiempo real
     - Integración con call_service para comunicación HTTP
     - Colas intermedias entre Agent, Query y Embedding services
   - **Impacto**: Cambio arquitectónico significativo - cambios altos
   - **Dependencias**: common/context, common/cache, common/errors
   - **Servicios afectados**: Todos (Agent, Query, Embedding, Ingestion)

### 7. [Integración de Metadatos](08_METADATA_INTEGRATION.md)
   - **Componentes implementados**:
     - Estandarización de formato de metadatos entre frameworks
     - Adaptadores para LlamaIndex y LangChain
     - Pipeline de enriquecimiento de metadatos
     - Sistema de tracking de proveniencia
   - **Impacto**: Mejora de interoperabilidad - cambios medios
   - **Dependencias**: 01_AGENT_SERVICE_CORE, 04_COLLECTION_STRATEGY
   - **Servicios afectados**: Agent Service, Query Service

## BLOQUE 3: REFACTORIZACIÓN DE SERVICIOS ESPECIALIZADOS

### 8. [Refactorización del Query Service](02_QUERY_SERVICE_REFACTOR.md)
   - **Componentes implementados**:
     - Nuevos modelos de datos para vectores y consultas
     - Endpoints internos optimizados
     - Integración con sistema de embeddings pre-generados
     - Implementación de patrones estandarizados de caché y errores
   - **Impacto**: Refactorización significativa - cambios altos
   - **Dependencias**: 07_WORK_QUEUE_SYSTEM, common/context, common/cache
   - **Servicios afectados**: Query Service, Agent Service

### 9. [Optimización del Embedding Service](03_EMBEDDING_SERVICE_OPTIMIZE.md)
   - **Componentes implementados**:
     - Sistema optimizado de tracking de tokens
     - Caché multinivel para embeddings
     - Endpoints internos mejorados
     - Integración con work queue para procesamiento en batch
   - **Impacto**: Refactorización significativa - cambios altos
   - **Dependencias**: 07_WORK_QUEUE_SYSTEM, common/context, common/cache
   - **Servicios afectados**: Embedding Service, Query Service, Ingestion Service

## Organización de Pruebas

Cada implementación incluye una carpeta de pruebas específica:

```
/agent-service/tests/
  /unit/                 # Pruebas unitarias (por módulo)
  /integration/          # Pruebas de integración entre componentes
  /e2e/                  # Pruebas end-to-end de flujos completos
  /performance/          # Pruebas de rendimiento y carga
```

## Seguimiento de Progreso

Cada archivo contiene tareas específicas con marcadores de estado:

- [ ] Tarea pendiente
- [x] Tarea completada
- [~] Tarea en progreso
- [!] Tarea que requiere revisión
