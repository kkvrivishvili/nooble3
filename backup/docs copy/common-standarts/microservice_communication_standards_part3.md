# Estándares de Comunicación entre Microservicios - Nooble AI (Parte 3)

## 11. Implementación por Niveles de Flujo

### 11.1 Matriz de Implementación Priorizada

Los flujos de trabajo identificados deben implementarse siguiendo esta secuencia priorizada:

| Fase | Flujos | Servicios Críticos | Prioridad |
|------|--------|-------------------|-----------|
| 1 | Conversación Simple, Consulta con Contexto, Búsqueda RAG Básica | Orchestrator, Agent Execution, Query Service, Embedding Service | 🔥 P0 |
| 2 | Multi-turno, Herramientas Simples, Generación con Memoria | + Conversation Service, Tool Registry | 🟡 P1 |
| 3 | Workflow Multi-etapa, Ingestión Documentos, Multi-colección | + Workflow Engine, Ingestion Service | 🟠 P2 |
| 4 | Multi-documento, Workflows Adaptativos, Multi-agente | Todos los servicios | 🔵 P3 |
| 5 | Monitoreo y Salud, Recuperación, Optimización | Todos los servicios | Continuo |

### 11.2 Implementación de Flujos Básicos (Nivel 1)

Para implementar correctamente los flujos básicos, cada servicio debe:

#### Orchestrator Service:
- Mantener colas: `orchestrator.session.{tenant}.{session}`, `orchestrator.tasks.{tenant}`
- Implementar endpoints: `/api/v1/sessions`, `/api/v1/messages`
- Configurar canales WebSocket: `/ws/{tenant_id}/frontend/{session_id}`

#### Agent Execution Service:
- Consumir de: `orchestrator.tasks.{tenant}`
- Producir en: `agent_execution.results.{tenant}.{task_id}`
- Solicitar embeddings mediante: `embedding.tasks.{tenant}`

#### Query Service:
- Consumir de: `query.generation.{tenant}`
- Integrar con LLM Providers (OpenAI, Groq)
- Implementar búsqueda vectorial

#### Embedding Service:
- Consumir de: `embedding.tasks.{tenant}`
- Implementar modelos de embedding
- Producir en: `embedding.results.{tenant}.{task_id}`

### 11.3 Implementación de Flujos Intermedios (Nivel 2)

Tras implementar los flujos básicos, expandir a:

#### Conversation Service:
- Mantener historial en BD relacional
- Implementar windowing de contexto
- Exponer colas: `conversation.context.{tenant}.{session}`

#### Tool Registry Service:
- Mantener registro de herramientas por tenant
- Implementar execución segura de herramientas
- Exponer colas: `tools.execution.{tenant}`, `tools.results.{tenant}.{execution_id}`

#### Agent Management Service:
- Gestionar configuraciones de agente
- Mantener memoria persistente
- Exponer cola: `agent.memory.{tenant}.{agent}`

## 12. Ejemplos de Implementación

### 12.1 Ejemplo Flujo 1: Conversación Simple

#### Mensaje de Solicitud (Orchestrator → Agent Execution)

```json
{
  "task_id": "44f6d65e-8573-4c29-9e55-d4eee4d77752",
  "tenant_id": "acme-corp",
  "created_at": "2025-06-03T20:15:00Z",
  "status": "pending",
  "type": "agent_execution",
  "priority": 2,
  "metadata": {
    "source_service": "orchestrator",
    "correlation_id": "44f6d65e-8573-4c29-9e55-d4eee4d77752",
    "session_id": "session-789",
    "user_id": "user-123"
  },
  "payload": {
    "agent_id": "customer-support-agent",
    "messages": [
      {
        "role": "user",
        "content": "¿Cuáles son sus horarios de atención?"
      }
    ],
    "stream": true
  }
}
```

#### Mensaje de Respuesta (Agent Execution → Orchestrator)

```json
{
  "task_id": "44f6d65e-8573-4c29-9e55-d4eee4d77752",
  "tenant_id": "acme-corp",
  "created_at": "2025-06-03T20:15:00Z",
  "completed_at": "2025-06-03T20:15:03Z",
  "status": "completed",
  "type": "agent_execution_result",
  "metadata": {
    "source_service": "agent_execution",
    "correlation_id": "44f6d65e-8573-4c29-9e55-d4eee4d77752",
    "session_id": "session-789"
  },
  "payload": {
    "agent_id": "customer-support-agent",
    "response": {
      "role": "assistant",
      "content": "Nuestros horarios de atención son de lunes a viernes de 9:00 a 18:00 y los sábados de 10:00 a 14:00. Los domingos no ofrecemos servicio de atención al cliente. ¿Hay algo más en lo que pueda ayudarte?"
    },
    "metrics": {
      "tokens_input": 12,
      "tokens_output": 45,
      "processing_time_ms": 2500
    }
  }
}
```

### 12.2 Ejemplo Flujo 3: Búsqueda RAG Básica

#### Solicitud de Embedding (Agent Execution → Embedding Service)

```json
{
  "task_id": "7a9c1b3e-5f24-4d81-b8c7-2e98d5a21f30",
  "tenant_id": "acme-corp",
  "created_at": "2025-06-03T20:20:00Z",
  "status": "pending",
  "type": "single_embedding",
  "priority": 3,
  "metadata": {
    "source_service": "agent_execution",
    "correlation_id": "98d76e4f-2c1a-4b3f-9d5e-7c8a6b4f3d2a",
    "session_id": "session-456"
  },
  "payload": {
    "texts": ["¿Cómo puedo devolver un producto defectuoso?"],
    "dimensions": 1536,
    "model": "text-embedding-3-small"
  }
}
```

#### Solicitud de Búsqueda RAG (Agent Execution → Query Service)

```json
{
  "task_id": "98d76e4f-2c1a-4b3f-9d5e-7c8a6b4f3d2a",
  "tenant_id": "acme-corp",
  "created_at": "2025-06-03T20:20:01Z",
  "status": "pending",
  "type": "rag_query",
  "priority": 3,
  "metadata": {
    "source_service": "agent_execution",
    "correlation_id": "98d76e4f-2c1a-4b3f-9d5e-7c8a6b4f3d2a",
    "session_id": "session-456"
  },
  "payload": {
    "query": "¿Cómo puedo devolver un producto defectuoso?",
    "embedding": [0.023, -0.14, ...], // Vector truncado para brevedad
    "collection_ids": ["support-docs"],
    "top_k": 3,
    "similarity_threshold": 0.75,
    "model": "groq-mixtral-8x7b"
  }
}
```

#### Evento WebSocket (Query Service → Orchestrator → Frontend)

```json
{
  "event": "rag_search_completed",
  "service": "query_service",
  "task_id": "98d76e4f-2c1a-4b3f-9d5e-7c8a6b4f3d2a",
  "tenant_id": "acme-corp",
  "timestamp": "2025-06-03T20:20:03Z",
  "data": {
    "session_id": "session-456",
    "search_time_ms": 150,
    "document_count": 3
  }
}
```

## 13. Patrones de Diseño Recomendados

### 13.1 Patrones Asíncronos

| Patrón | Caso de Uso | Beneficio |
|--------|------------|----------|
| **Publisher/Subscriber** | Notificaciones multi-consumidor | Desacoplamiento |
| **Event Sourcing** | Tracking de cambios de estado | Auditabilidad |
| **CQRS** | Separación lectura/escritura | Escalabilidad |
| **Saga** | Transacciones distribuidas | Consistencia |

### 13.2 Patrones de Resiliencia

| Patrón | Caso de Uso | Beneficio |
|--------|------------|----------|
| **Circuit Breaker** | Protección contra fallos | Prevención cascada |
| **Bulkhead** | Aislamiento de recursos | Contención de fallos |
| **Timeout** | Operaciones bloqueantes | Liberación recursos |
| **Retry** | Errores transitorios | Recuperación |
| **Fallback** | Respuesta degradada | Disponibilidad |

### 13.3 Patrones de Escalabilidad

| Patrón | Caso de Uso | Beneficio |
|--------|------------|----------|
| **Sharding** | Particionamiento por tenant | Aislamiento |
| **Competing Consumers** | Procesamiento paralelo | Throughput |
| **Cache-Aside** | Reducción carga BD | Rendimiento |
| **Throttling** | Control de carga | Estabilidad |

## 14. Validación y Testing

### 14.1 Pruebas de Contrato

Cada servicio debe definir y validar contratos de comunicación:

- **Producer Contract**: Schema esperado de mensajes producidos
- **Consumer Contract**: Schema requerido para mensajes consumidos

Herramientas recomendadas:
- Pact para pruebas de contrato
- JSON Schema para validación

### 14.2 Pruebas de Integración

Escenarios mínimos a probar:

- **Flujo Feliz**: Comunicación normal
- **Circuit Breaking**: Comportamiento ante fallos
- **Timeout**: Comportamiento ante latencias altas
- **Recuperación**: Tras caída de servicio

### 14.3 Chaos Engineering

Estrategias recomendadas:

- **Inyección de Latencia**: Verificar timeouts
- **Caída de Servicios**: Verificar degradación
- **Particiones de Red**: Verificar recuperación
- **Sobrecarga de Cola**: Verificar backpressure

## 15. Registro de Cambios y Evolución

### 15.1 Versionado de APIs y Mensajes

- **Versiones Mayores**: Campos obligatorios o incompatibles
- **Versiones Menores**: Adiciones opcionales
- **Compatibilidad**: Asegurar N-1 durante transiciones

### 15.2 Estrategia de Evolución

1. **Añadir** campos opcionales
2. **Deprecar** campos con período de gracia
3. **Eliminar** solo tras período de deprecación
4. **Mantener** compatibilidad hacia atrás cuando sea posible

### 15.3 Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial |

## 16. Referencias y Recursos

### 16.1 Documentación Relacionada

- [Arquitectura de Microservicios Nooble](../architecture/microservices_architecture.md)
- [Estándares de Bases de Datos](./database_structure_standards.md)
- [Guía de Observabilidad](../operations/observability_guidelines.md)

### 16.2 Ejemplos de Implementación

Ejemplos completos para implementaciones de referencia:

- [Agent Orchestrator Service](../agent-orchestrator-service/communication/internal)
- [Agent Execution Service](../agent-execution-service/communication/internal)
- [Embedding Service](../embedding-service/communication/internal)

### 16.3 Herramientas Internas

- [Schema Registry](http://schema-registry.nooble.io)
- [Message Explorer](http://message-explorer.nooble.io)
- [Flow Visualizer](http://flow-visualizer.nooble.io)
