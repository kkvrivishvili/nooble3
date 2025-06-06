# Esquemas de Mensajes del Agent Orchestrator Service

## Introducción

Este documento define el esquema central de mensajes utilizados en la comunicación interna del Agent Orchestrator Service con otros servicios de la plataforma Nooble. Sirve como referencia canónica para todos los formatos de mensaje, sus campos obligatorios y opcionales, y los estándares de validación.

> **Importante**: Este documento implementa las especificaciones definidas en los [Estándares de Comunicación](../../../common-standarts/microservice_communication_standards_part1.md#4-formato-de-mensajes) y debe mantenerse sincronizado con ellos.

## Control de Versiones

| Versión | Fecha       | Autor         | Cambios                                                    |
|---------|------------|--------------|-----------------------------------------------------------|
| 1.1.0   | 2025-06-04 | Equipo Backend| Actualización para alinear con estándares globales:     |
|         |            |              | - Nueva estructura de tipo (domain/action)                |
|         |            |              | - Campos adicionales de trazabilidad                      |
|         |            |              | - Ejemplos actualizados para todos los servicios          |
| 1.0.0   | 2025-06-03 | DevTeam       | Versión inicial                                          |

## Formato Base de Mensaje

Todos los mensajes intercambiados entre el Agent Orchestrator Service y otros servicios deben seguir esta estructura base estandarizada:

```json
{
  "message_id": "uuid-v4",              // OBLIGATORIO: Identificador único del mensaje
  "task_id": "uuid-v4",               // OBLIGATORIO: ID de tarea asociada
  "tenant_id": "tenant-identifier",    // OBLIGATORIO: ID del tenant
  "session_id": "session-identifier",  // OPCIONAL: ID de sesión (cuando aplique)
  "conversation_id": "uuid-v4",        // OPCIONAL: ID de la conversación (cuando aplique)
  "correlation_id": "uuid-v4",         // OBLIGATORIO: ID de correlación para trazabilidad
  "created_at": "ISO-8601",           // OBLIGATORIO: Timestamp de creación
  "expires_at": "ISO-8601",           // OPCIONAL: Timestamp de expiración
  "schema_version": "1.1",            // OBLIGATORIO: Versión del esquema
  "status": "pending|processing|completed|failed",  // OBLIGATORIO: Estado
  "type": {                           // OBLIGATORIO: Tipo estructurado
    "domain": "agent|workflow|conversation|tool|system", // Dominio funcional
    "action": "execute|update|query|notify|status"      // Acción solicitada
  },
  "priority": 0-9,                     // OBLIGATORIO: Prioridad (0=más alta, 9=más baja)
  "source_service": "service-name",     // OBLIGATORIO: Servicio que origina el mensaje
  "target_service": "service-name",     // OBLIGATORIO: Servicio destinatario
  "delegated_services": [              // OPCIONAL: Servicios involucrados
    {
      "service": "service-name",
      "task_id": "service-specific-task-id",
      "status": "pending|completed|failed"
    }
  ],
  "metadata": {                        // OPCIONAL: Metadatos extensibles
    "source": "api|scheduled|system",
    "user_id": "optional-user-id",
    "timeout_ms": 30000,
    "retry_count": 0,
    "expected_duration_ms": 5000,
    "deduplication_key": "optional-key", // Para evitar duplicados
    "trace_id": "distributed-tracing-id", // Para trazabilidad distribuida
    "client_version": "client-version",   // Versión del cliente
    "idempotency_key": "idempotency-key" // Para operaciones idempotentes
  },
  "payload": {                         // OBLIGATORIO: Datos específicos
    // Contenido variable según el tipo - detallado por servicio
  },
  "error": {                           // OPCIONAL: Solo presente si hay error
    "code": "ERROR_CODE",
    "message": "Descripción legible del error",
    "details": {},
    "retry_suggested": true|false,
    "service": "service-name"
  }
}
```

### Reglas de Validación

1. **Campos obligatorios**: Todos los campos marcados como OBLIGATORIO deben estar presentes.
2. **Mutabilidad**: Ciertos campos (`message_id`, `task_id`, `tenant_id`, `correlation_id`, `created_at`, `schema_version`) son inmutables tras la creación.
3. **Unicidad**: Los `message_id` deben ser únicos a nivel global en toda la plataforma.
4. **Consistencia temporal**: `expires_at` debe ser posterior a `created_at`.
5. **Límites de contenido**: El tamaño total del mensaje no debe exceder 1MB.

## Campos Adicionales de Mensaje

### Metadata Extendida

El objeto `metadata` proporciona un mecanismo extensible para incluir información adicional sin modificar la estructura principal del mensaje.

| Campo              | Tipo     | Descripción                                      | Servicios Aplicables          |
|-------------------|----------|--------------------------------------------------|------------------------------|
| `source`           | string   | Origen de la solicitud (`api`, `scheduled`, `system`) | Todos                        |
| `user_id`          | string   | ID del usuario final que origina la solicitud    | Todos                        |
| `timeout_ms`       | integer  | Timeout personalizado en milisegundos           | Todos                        |
| `retry_count`      | integer  | Número de reintentos realizados                | Todos                        |
| `expected_duration_ms` | integer | Duración esperada de la operación          | Servicios ejecutores         |
| `deduplication_key`   | string  | Clave para evitar operaciones duplicadas       | Servicios transaccionales    |
| `trace_id`         | string   | ID para seguimiento distribuido (OpenTelemetry) | Todos                        |
| `client_version`   | string   | Versión del cliente que origina la solicitud   | Frontend/API                 |
| `idempotency_key`  | string   | Clave para garantizar idempotencia             | Servicios transaccionales    |
| `execution_context` | object  | Contexto adicional para la ejecución          | Agent Execution, Workflow    |
| `log_level`        | string   | Nivel de log (`debug`, `info`, `warn`, `error`) | Todos                        |
| `workflow_step_id`  | string  | ID del paso actual en un workflow              | Workflow Engine              |
| `user_locale`      | string   | Locale del usuario (ISO 639-1)                 | Servicios de presentación    |
| `experimental`     | boolean  | Indicador de funciones experimentales          | Todos                        |
| `sensitive_data`   | boolean  | Indicador de datos sensibles                    | Todos                        |

### Denominadores de Tiempo

Además de los campos principales de tiempo, los mensajes pueden utilizar estos campos temporales adicionales:

| Campo              | Tipo     | Descripción                                      |
|-------------------|----------|--------------------------------------------------|
| `processed_at`     | string   | Timestamp ISO-8601 de procesamiento              |
| `completed_at`     | string   | Timestamp ISO-8601 de completado                 |
| `scheduled_for`    | string   | Timestamp ISO-8601 de ejecución programada      |
| `valid_until`      | string   | Timestamp ISO-8601 de validez del mensaje       |

## Especificaciones de Payload por Tipo de Servicio

Cada servicio utiliza una estructura específica para el campo `payload` según el dominio y la acción que se está ejecutando. A continuación se detallan los formatos estandarizados para cada servicio.

### Agent Execution Service

#### Ejecución de Agente (domain: "agent", action: "execute")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "tenant-ab123",
  "session_id": "session-xyz789",
  "conversation_id": "conv-123456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002",
  "created_at": "2025-06-04T10:15:30.123Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "agent",
    "action": "execute"
  },
  "priority": 3,
  "source_service": "agent_orchestrator",
  "target_service": "agent_execution",
  "metadata": {
    "source": "api",
    "user_id": "user-123",
    "timeout_ms": 60000,
    "expected_duration_ms": 15000,
    "trace_id": "trace-abc123",
    "client_version": "1.5.0"
  },
  "payload": {
    "query": "Analiza los datos de ventas y recomienda estrategias para aumentar la conversión",
    "agent_config": {
      "agent_id": "sales-analysis-agent",
      "version": "1.2",
      "parameters": {
        "temperature": 0.7,
        "model": "gpt-4",
        "response_format": "markdown"
      }
    },
    "context": [
      {
        "type": "conversation_history",
        "content": [...]
      },
      {
        "type": "document_reference",
        "content": {
          "document_id": "doc-456",
          "chunks": [1, 2, 3]
        }
      }
    ],
    "stream": true,
    "tools": [
      {
        "name": "data_analysis",
        "description": "Analiza datos de ventas",
        "parameters": {
          "type": "object",
          "properties": {
            "date_range": {
              "type": "string",
              "description": "Rango de fechas para el análisis"
            },
            "metrics": {
              "type": "array",
              "items": {"type": "string"},
              "description": "Métricas a analizar"
            }
          },
          "required": ["date_range"]
        }
      }
    ],
    "max_tokens": 2000
  }
}
```

#### Notificación de Estado (domain: "agent", action: "status")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440010",
  "task_id": "550e8400-e29b-41d4-a716-446655440001", // Mismo task_id que la solicitud
  "tenant_id": "tenant-ab123",
  "session_id": "session-xyz789",
  "conversation_id": "conv-123456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002", // Mismo correlation_id
  "created_at": "2025-06-04T10:15:32.456Z",
  "schema_version": "1.1",
  "status": "processing",
  "type": {
    "domain": "agent",
    "action": "status"
  },
  "priority": 2, // Mayor prioridad para actualizaciones de estado
  "source_service": "agent_execution",
  "target_service": "agent_orchestrator",
  "metadata": {
    "trace_id": "trace-abc123",
    "processed_at": "2025-06-04T10:15:32.456Z"
  },
  "payload": {
    "progress": 25,
    "status_detail": "Analizando datos de ventas",
    "estimated_completion_seconds": 45,
    "stream_content": {
      "type": "thinking",
      "content": "Examinando patrones de ventas trimestrales..."
    }
  }
}
```

#### Respuesta Final (domain: "agent", action: "response")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440020",
  "task_id": "550e8400-e29b-41d4-a716-446655440001", // Mismo task_id que solicitud original
  "tenant_id": "tenant-ab123",
  "session_id": "session-xyz789",
  "conversation_id": "conv-123456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002", // Mismo correlation_id
  "created_at": "2025-06-04T10:15:50.789Z",
  "schema_version": "1.1",
  "status": "completed",
  "type": {
    "domain": "agent",
    "action": "response"
  },
  "priority": 2,
  "source_service": "agent_execution",
  "target_service": "agent_orchestrator",
  "metadata": {
    "trace_id": "trace-abc123",
    "completed_at": "2025-06-04T10:15:50.789Z",
    "processing_time_ms": 20666
  },
  "payload": {
    "response": "# Análisis de Ventas\n\nBasado en los datos proporcionados, se identificaron las siguientes oportunidades:\n\n1. **Incremento en tasa de conversión**...\n",
    "completion_tokens": 756,
    "total_tokens": 1234,
    "tool_calls": [
      {
        "tool_name": "data_analysis",
        "parameters": {
          "date_range": "Q1-Q2 2025",
          "metrics": ["conversion_rate", "average_order_value"]
        },
        "result": { /* contenido del resultado */ }
      }
    ],
    "sources": [
      {
        "document_id": "doc-456",
        "chunks": [1, 2],
        "relevance_score": 0.95
      }
    ],
    "thinking_process": "Primero analizé las tendencias de los últimos 6 meses..."
  }
}
```

### Workflow Engine Service

#### Inicio de Workflow (domain: "workflow", action: "start")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655441000",
  "task_id": "550e8400-e29b-41d4-a716-446655441001",
  "tenant_id": "tenant-ab123",
  "session_id": "session-def456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655441002",
  "created_at": "2025-06-04T11:30:00.000Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "workflow",
    "action": "start"
  },
  "priority": 4,
  "source_service": "agent_orchestrator",
  "target_service": "workflow_engine",
  "metadata": {
    "source": "api",
    "user_id": "user-123",
    "timeout_ms": 120000,
    "expected_duration_ms": 60000
  },
  "payload": {
    "workflow_template_id": "sales-analysis-workflow",
    "workflow_version": "2.1",
    "input_parameters": {
      "date_range": "2025-01-01,2025-06-01",
      "target_metrics": ["conversion_rate", "revenue", "customer_retention"],
      "market_segment": "enterprise"
    },
    "execution_mode": "async",
    "timeout_seconds": 600,
    "notification_config": {
      "on_complete": ["email", "webhook"],
      "on_error": ["email", "webhook", "slack"],
      "recipients": ["user@example.com"]
    },
    "context": {
      "triggered_by": "scheduled_report",
      "previous_workflow_id": "wf-20250520-123"
    }
  }
}
```

#### Ejecución de Paso (domain: "workflow", action: "step")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655441020",
  "task_id": "550e8400-e29b-41d4-a716-446655441021",
  "tenant_id": "tenant-ab123",
  "session_id": "session-def456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655441002", // Mismo correlation_id del workflow
  "created_at": "2025-06-04T11:30:15.000Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "workflow",
    "action": "step"
  },
  "priority": 5,
  "source_service": "workflow_engine",
  "target_service": "agent_orchestrator",
  "delegated_services": [
    {
      "service": "agent_execution",
      "task_id": "ae-task-001",
      "status": "pending"
    }
  ],
  "metadata": {
    "workflow_id": "wf-20250604-001", 
    "workflow_step_id": "step-002",
    "step_name": "generate_market_analysis",
    "timeout_ms": 60000
  },
  "payload": {
    "step_type": "agent_task",
    "agent_config": {
      "agent_id": "market-analysis-agent",
      "parameters": {
        "market_segment": "enterprise",
        "analysis_depth": "detailed"
      }
    },
    "input_data": {
      "sales_data": { "source": "previous_step", "step_id": "step-001" },
      "market_context": { "source": "workflow_input", "parameter": "market_segment" }
    },
    "expected_output": {
      "format": "json",
      "schema": { "$ref": "schemas/market_analysis_output.json" }
    },
    "on_failure": "retry_once_then_continue"
  }
}
```

#### Notificación de Estado de Workflow (domain: "workflow", action: "status")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655441050",
  "task_id": "550e8400-e29b-41d4-a716-446655441001", // Mismo task_id que el inicio del workflow
  "tenant_id": "tenant-ab123",
  "session_id": "session-def456",
  "correlation_id": "550e8400-e29b-41d4-a716-446655441002", // Mismo correlation_id
  "created_at": "2025-06-04T11:35:00.000Z",
  "schema_version": "1.1",
  "status": "processing",
  "type": {
    "domain": "workflow",
    "action": "status"
  },
  "priority": 3,
  "source_service": "workflow_engine",
  "target_service": "agent_orchestrator",
  "metadata": {
    "trace_id": "trace-def456",
    "workflow_id": "wf-20250604-001"
  },
  "payload": {
    "workflow_status": "running",
    "current_step": 2,
    "total_steps": 5,
    "completed_steps": 1,
    "progress_percentage": 20,
    "estimated_completion_seconds": 240,
    "steps_status": [
      { "step_id": "step-001", "name": "data_collection", "status": "completed" },
      { "step_id": "step-002", "name": "generate_market_analysis", "status": "running" },
      { "step_id": "step-003", "name": "generate_recommendations", "status": "pending" },
      { "step_id": "step-004", "name": "create_report", "status": "pending" },
      { "step_id": "step-005", "name": "deliver_results", "status": "pending" }
    ],
    "partial_results": {
      "step-001": { "status": "success", "data": { "records_processed": 5230 } }
    }
  }
}
```

### Conversation Service

#### Actualización de Conversación (domain: "conversation", action: "update")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655442000",
  "task_id": "550e8400-e29b-41d4-a716-446655442001",
  "tenant_id": "tenant-ab123",
  "conversation_id": "conv-123456", // ID de conversación primario para este servicio
  "correlation_id": "550e8400-e29b-41d4-a716-446655442002",
  "created_at": "2025-06-04T10:16:00.000Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "conversation",
    "action": "update"
  },
  "priority": 2,
  "source_service": "agent_orchestrator",
  "target_service": "conversation",
  "metadata": {
    "user_id": "user-123",
    "source": "agent_execution",
    "idempotency_key": "msg-20250604-1234"
  },
  "payload": {
    "message": {
      "id": "msg-20250604-1234",
      "content": "# Análisis de Ventas\n\nBasado en los datos proporcionados, se identificaron las siguientes oportunidades...",
      "role": "assistant",
      "created_at": "2025-06-04T10:15:50.000Z",
      "format": "markdown"
    },
    "attachments": [
      {
        "type": "image/png",
        "name": "ventas_q1q2.png",
        "url": "https://storage.example.com/attachments/ventas_q1q2.png",
        "size_bytes": 245000
      }
    ],
    "metadata": {
      "source_agent": "sales-analysis-agent",
      "completion_tokens": 756,
      "total_tokens": 1234,
      "sources": [
        { "document_id": "doc-456", "relevance_score": 0.95 }
      ]
    },
    "operation": "create"
  }
}
```

### Knowledge Base Service

#### Búsqueda Semántica (domain: "knowledge", action: "search")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655443000",
  "task_id": "550e8400-e29b-41d4-a716-446655443001",
  "tenant_id": "tenant-ab123",
  "session_id": "session-ghi789",
  "correlation_id": "550e8400-e29b-41d4-a716-446655443002",
  "created_at": "2025-06-04T12:00:00.000Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "knowledge",
    "action": "search"
  },
  "priority": 2,
  "source_service": "agent_orchestrator",
  "target_service": "knowledge_base",
  "metadata": {
    "source": "agent_execution",
    "user_id": "user-123",
    "timeout_ms": 15000
  },
  "payload": {
    "query": "estrategias para incrementar la tasa de conversión en ventas B2B",
    "search_config": {
      "search_type": "hybrid",
      "semantic_weight": 0.7,
      "keyword_weight": 0.3,
      "reranking": true
    },
    "filter": {
      "kb_ids": ["kb-sales-strategies", "kb-market-analysis"],
      "document_types": ["pdf", "markdown"],
      "metadata": {
        "department": "sales",
        "updated_after": "2024-01-01"
      }
    },
    "request_options": {
      "limit": 15,
      "return_metadata": true,
      "include_raw_content": true
    }
  }
}
```

#### Resultados de Búsqueda (domain: "knowledge", action: "results")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655443010",
  "task_id": "550e8400-e29b-41d4-a716-446655443001", // Mismo task_id que la solicitud
  "tenant_id": "tenant-ab123",
  "session_id": "session-ghi789",
  "correlation_id": "550e8400-e29b-41d4-a716-446655443002", // Mismo correlation_id
  "created_at": "2025-06-04T12:00:05.000Z",
  "schema_version": "1.1",
  "status": "completed",
  "type": {
    "domain": "knowledge",
    "action": "results"
  },
  "priority": 2,
  "source_service": "knowledge_base",
  "target_service": "agent_orchestrator",
  "metadata": {
    "trace_id": "trace-ghi789",
    "processing_time_ms": 4856
  },
  "payload": {
    "results": [
      {
        "document_id": "doc-sales-strategies-001",
        "chunk_id": "chunk-021",
        "content": "Los estudios demuestran que implementar un proceso de calificación de leads mejorado puede incrementar las tasas de conversión B2B hasta en un 30%. Las estrategias principales incluyen...",
        "metadata": {
          "source": "Sales Strategy Playbook 2025",
          "author": "Marketing Department",
          "created_at": "2024-11-15",
          "page": 42
        },
        "score": 0.92,
        "keywords": ["conversión", "B2B", "ventas", "estrategia"],
        "vector_id": "vec-chunk-021"
      },
      {
        "document_id": "doc-market-analysis-023",
        "chunk_id": "chunk-105",
        "content": "La personalización de la experiencia del cliente en cada etapa del embudo de ventas B2B ha mostrado incrementos en la tasa de conversión del 25% en empresas del sector tecnológico...",
        "metadata": {
          "source": "Análisis de Mercado Q1 2025",
          "author": "Research Team",
          "created_at": "2025-01-30",
          "tags": ["B2B", "personalización", "conversión"]
        },
        "score": 0.87,
        "vector_id": "vec-chunk-105"
      }
    ],
    "search_stats": {
      "total_results": 28,
      "returned_results": 15,
      "execution_time_ms": 1220,
      "indexes_searched": ["kb-sales-strategies", "kb-market-analysis"],
      "query_vector_id": "qvec-20250604-1200"
    },
    "facets": {
      "author": {
        "Marketing Department": 8,
        "Research Team": 5,
        "Sales Training": 2
      },
      "document_type": {
        "pdf": 10,
        "markdown": 5
      }
    },
    "related_queries": [
      "estrategias de seguimiento para leads B2B",
      "optimización de embudo de conversión empresarial"
    ]
  }
}
```

### Authentication Service

#### Verificación de Tokens (domain: "auth", action: "validate")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655444000",
  "task_id": "550e8400-e29b-41d4-a716-446655444001",
  "tenant_id": "tenant-ab123",
  "correlation_id": "550e8400-e29b-41d4-a716-446655444002",
  "created_at": "2025-06-04T12:30:00.000Z",
  "schema_version": "1.1",
  "status": "pending",
  "type": {
    "domain": "auth",
    "action": "validate"
  },
  "priority": 1, // Alta prioridad para autenticación
  "source_service": "agent_orchestrator",
  "target_service": "authentication",
  "metadata": {
    "source": "api_gateway",
    "timeout_ms": 5000
  },
  "payload": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "access",
    "validate_scope": true,
    "required_scopes": ["agent:execute", "knowledge:read"]
  }
}
```

#### Respuesta de Autenticación (domain: "auth", action: "result")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655444010",
  "task_id": "550e8400-e29b-41d4-a716-446655444001", // Mismo task_id que la solicitud
  "tenant_id": "tenant-ab123",
  "correlation_id": "550e8400-e29b-41d4-a716-446655444002", // Mismo correlation_id
  "created_at": "2025-06-04T12:30:00.250Z",
  "schema_version": "1.1",
  "status": "completed",
  "type": {
    "domain": "auth",
    "action": "result"
  },
  "priority": 1,
  "source_service": "authentication",
  "target_service": "agent_orchestrator",
  "metadata": {
    "processing_time_ms": 246
  },
  "payload": {
    "valid": true,
    "user": {
      "id": "user-123",
      "tenant_id": "tenant-ab123",
      "roles": ["user", "admin"],
      "permissions": ["agent:execute", "knowledge:read", "workflow:manage"]
    },
    "token_metadata": {
      "issued_at": "2025-06-04T10:00:00.000Z",
      "expires_at": "2025-06-04T22:00:00.000Z",
      "issuer": "auth.nooble.ai",
      "device_id": "device-xyz"
    },
    "scope_validation": {
      "has_required_scopes": true,
      "missing_scopes": []
    }
  }
}
```

### Control de Errores

#### Error de Autenticación (domain: "auth", action: "error")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655445000",
  "task_id": "550e8400-e29b-41d4-a716-446655445001",
  "tenant_id": "tenant-ab123",
  "correlation_id": "550e8400-e29b-41d4-a716-446655445002",
  "created_at": "2025-06-04T12:30:00.500Z",
  "schema_version": "1.1",
  "status": "error",
  "type": {
    "domain": "auth",
    "action": "error"
  },
  "priority": 1,
  "source_service": "authentication",
  "target_service": "agent_orchestrator",
  "metadata": {
    "error_code": "AUTH_001",
    "error_message": "Token inválido o expirado"
  },
  "payload": {
    "error_details": {
      "token_type": "access",
      "required_scopes": ["agent:execute", "knowledge:read"],
      "validation_result": {
        "valid": false,
        "reason": "Token inválido"
      }
    }
  }
}
```

## Manejo de Errores

### Formato Estándar de Errores

Todos los errores siguen una estructura estandarizada:

```json
{
  "message_id": "UUID-GENERATED",
  "task_id": "RELATED-TASK-ID",
  "tenant_id": "tenant-id",
  "correlation_id": "ORIGINAL-CORRELATION-ID",
  "created_at": "ISO-8601-TIMESTAMP",
  "schema_version": "1.1",
  "status": "error",
  "type": {
    "domain": "[original-domain]",
    "action": "error"
  },
  "priority": "[ORIGINAL-PRIORITY]",
  "source_service": "[SERVICE-WITH-ERROR]",
  "target_service": "[ORIGINAL-REQUESTOR]",
  "metadata": {
    "error_code": "[ERROR_CODE]",
    "error_category": "[client|server|validation|security|dependency]",
    "error_message": "[HUMAN-READABLE-MESSAGE]",
    "trace_id": "[TRACE-ID-IF-AVAILABLE]",
    "retry_count": "[RETRY-COUNT-IF-APPLICABLE]",
    "recovery_action": "[none|retry|circuit-breaker|fallback]"
  },
  "payload": {
    "error_details": {
      // Información detallada del error
    },
    "recovery_options": {
      // Opciones de recuperación si aplica
    }
  }
}
```

### Catálogo de Códigos de Error Estándar

Los códigos de error siguen el formato: `[CATEGORY]_[SERVICE-PREFIX]_[NUMBER]`

#### Errores Genéricos (Categoría: GEN)

| Código | Mensaje | Descripción | Acción Recomendada |
|---------|---------|------------|--------------------|
| `GEN_001` | Servicio no disponible | El servicio solicitado no está disponible en este momento | Reintentar con backoff exponencial |
| `GEN_002` | Timeout de operación | La operación excedió el tiempo límite | Reintentar con parámetros optimizados |
| `GEN_003` | Capacidad excedida | El servicio no puede procesar más solicitudes | Implementar limitación de frecuencia |
| `GEN_004` | Error interno | Error interno del servidor | Reportar al equipo de desarrollo |
| `GEN_005` | Dependencia fallida | Una dependencia del servicio falló | Verificar estado de servicios dependientes |

#### Errores de Validación (Categoría: VAL)

| Código | Mensaje | Descripción | Acción Recomendada |
|---------|---------|------------|--------------------|
| `VAL_001` | Parámetros inválidos | Los parámetros proporcionados son inválidos | Revisar y corregir parámetros |
| `VAL_002` | Campo requerido ausente | Falta un campo obligatorio | Añadir el campo requerido |
| `VAL_003` | Formato inválido | El formato del campo no cumple con el esperado | Corregir formato según documentación |
| `VAL_004` | Límite excedido | El valor excede los límites permitidos | Ajustar el valor dentro de los límites |
| `VAL_005` | Conflicto de recursos | El recurso ya existe o hay un conflicto | Resolver conflicto o usar recurso existente |

#### Errores de Autenticación/Autorización (Categoría: AUTH)

| Código | Mensaje | Descripción | Acción Recomendada |
|---------|---------|------------|--------------------|
| `AUTH_001` | Autenticación fallida | Credenciales inválidas o faltantes | Verificar credenciales |
| `AUTH_002` | Token expirado | El token de autenticación expiró | Renovar token |
| `AUTH_003` | Permiso denegado | No tiene permisos para esta operación | Solicitar permisos necesarios |
| `AUTH_004` | Requisito de autenticación | Se requiere autenticación | Autenticarse antes de continuar |
| `AUTH_005` | Límite de sesiones | Número máximo de sesiones alcanzado | Cerrar sesiones inactivas |

#### Errores Específicos de Agent Execution (Categoría: AEX)

| Código | Mensaje | Descripción | Acción Recomendada |
|---------|---------|------------|--------------------|
| `AEX_001` | Configuración de agente inválida | La configuración del agente es inválida | Revisar configuración del agente |
| `AEX_002` | Limite de tokens excedido | Se excedió el límite de tokens | Reducir tamaño del prompt o aumentar límite |
| `AEX_003` | Herramienta no disponible | La herramienta solicitada no está disponible | Verificar disponibilidad de herramientas |
| `AEX_004` | Error en llamada a modelo | Error en la API del modelo | Reintentar o usar modelo alternativo |
| `AEX_005` | Error en ejecución de herramienta | La ejecución de la herramienta falló | Verificar parámetros y estado de la herramienta |

#### Errores Específicos de Workflow (Categoría: WF)

| Código | Mensaje | Descripción | Acción Recomendada |
|---------|---------|------------|--------------------|
| `WF_001` | Definición de workflow inválida | La definición del workflow es inválida | Revisar definición del workflow |
| `WF_002` | Paso de workflow no encontrado | El paso especificado no existe | Verificar ID del paso |
| `WF_003` | Condición inválida | Condición de transición inválida | Revisar condiciones de transición |
| `WF_004` | Ciclo detectado | Se detectó un ciclo en el workflow | Corregir ciclo en el diseño del workflow |
| `WF_005` | Estado inválido | Transición a estado inválido | Verificar diagrama de estados |

### Ejemplos de Error

#### Error de Validación (domain: "agent", action: "error")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655446000",
  "task_id": "550e8400-e29b-41d4-a716-446655440001", // Task ID original
  "tenant_id": "tenant-ab123",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440002", // Correlation ID original
  "created_at": "2025-06-04T10:15:31.000Z",
  "schema_version": "1.1",
  "status": "error",
  "type": {
    "domain": "agent", 
    "action": "error"
  },
  "priority": 2, // Alta prioridad para notificar errores
  "source_service": "agent_execution",
  "target_service": "agent_orchestrator",
  "metadata": {
    "error_code": "VAL_AEX_001",
    "error_category": "validation",
    "error_message": "Configuración de agente inválida",
    "trace_id": "trace-abc123",
    "recovery_action": "none"
  },
  "payload": {
    "error_details": {
      "validation_errors": [
        { "field": "agent_config.parameters.temperature", "message": "El valor debe estar entre 0 y 1, se recibió: 1.5" },
        { "field": "agent_config.model", "message": "Modelo no compatible: 'custom-model-xyz'" }
      ],
      "agent_config": {
        "agent_id": "sales-analysis-agent",
        "version": "1.2",
        "parameters": {
          "temperature": 1.5, // Valor inválido
          "model": "custom-model-xyz", // Modelo no soportado
          "response_format": "markdown"
        }
      }
    }
  }
}
```

#### Error de Dependencia (domain: "workflow", action: "error")

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655446010",
  "task_id": "550e8400-e29b-41d4-a716-446655441021", // Task ID original
  "tenant_id": "tenant-ab123",
  "correlation_id": "550e8400-e29b-41d4-a716-446655441002", // Correlation ID original
  "created_at": "2025-06-04T11:30:20.000Z",
  "schema_version": "1.1",
  "status": "error",
  "type": {
    "domain": "workflow",
    "action": "error"
  },
  "priority": 3,
  "source_service": "workflow_engine",
  "target_service": "agent_orchestrator",
  "metadata": {
    "error_code": "GEN_005",
    "error_category": "dependency",
    "error_message": "Error en servicio dependiente",
    "trace_id": "trace-def456",
    "retry_count": 2,
    "recovery_action": "circuit-breaker"
  },
  "payload": {
    "error_details": {
      "dependency_service": "data_analysis_service",
      "dependency_operation": "analyze_sales_data",
      "status_code": 503,
      "response": "Service Unavailable"
    },
    "recovery_options": {
      "circuit_breaker": {
        "status": "open",
        "retry_after_seconds": 60,
        "failure_threshold": 5,
        "current_failures": 3
      },
      "fallback_options": [
        {
          "option": "use_cached_data",
          "availability": true,
          "data_freshness_seconds": 3600
        },
        {
          "option": "skip_step",
          "impact": "reduced_analysis_quality"
        }
      ]
    }
  }
}
```

## Estándar de Colas de Mensajes

Las colas para intercambio de mensajes entre servicios siguen el formato estándar:

```
service-name.[priority].[domain].[action]
```

Donde:

- `service-name`: Nombre del servicio destino (ej. `agent-execution`, `workflow-engine`).
- `priority` (opcional): Prioridad del mensaje (`high`, `normal`, `low`).
- `domain`: Dominio funcional del mensaje (ej. `agent`, `workflow`, `knowledge`).
- `action` (opcional): Acción específica dentro del dominio.

### Colas Principales por Servicio

| Servicio | Cola | Descripción |
|---------|------|-------------|
| Agent Execution | `agent_execution:tasks:{tenant_id}` | Cola de tareas pendientes de ejecución |
| Agent Execution | `agent_execution:results:{tenant_id}` | Cola de resultados de ejecución |
| Conversation | `conversation:tasks:{tenant_id}` | Cola de operaciones de conversación |
| Workflow Engine | `workflow_engine:tasks:{tenant_id}` | Cola de tareas de workflow |
| Tool Registry | `tool_registry:tasks:{tenant_id}` | Cola de ejecución de herramientas |
| Tool Registry | `tool_registry:results:{tenant_id}:{session_id}` | Cola de resultados de herramientas |
| Orchestrator | `orchestrator:dlq:{tenant_id}` | Dead Letter Queue global |

## Códigos de Error Comunes

| Código                 | HTTP Status | Descripción                                      | Reintentable |
|-----------------------|-------------|--------------------------------------------------|-------------|
| `validation_error`     | 400         | Error en la validación del formato del mensaje   | No          |
| `service_unavailable`  | 503         | Servicio de destino no disponible               | Sí          |
| `timeout`              | 504         | Timeout en la operación                          | Sí          |
| `authorization_error`  | 401         | Error de autorización entre servicios           | No          |
| `resource_not_found`   | 404         | Recurso solicitado no encontrado                 | No          |
| `rate_limited`         | 429         | Se excedió el límite de tasa                     | Sí          |
| `circuit_open`         | 503         | Circuit breaker abierto                          | Sí          |
| `invalid_session`      | 400         | Sesión inválida o expirada                       | No          |
| `service_error`        | 500         | Error interno del servicio                       | Sí          |

## Códigos de Error Específicos por Servicio

Los servicios pueden definir códigos específicos siguiendo este formato:
`{SERVICIO}_{CATEGORIA}_{NUMERO}`

Ejemplos:

| Código | Servicio | Descripción |
|--------|----------|-------------|
| `ORCH_AUTH_001` | Orchestrator | Error de autenticación |
| `AGEX_EXEC_002` | Agent Execution | Error de ejecución |
| `CONV_VAL_001` | Conversation | Error de validación |
| `TOOL_EXEC_003` | Tool Registry | Error de ejecución |
| `WFLOW_VAL_001` | Workflow Engine | Error de validación |

## Prioridades y Timeouts Recomendados

Las prioridades se definen en escala inversa: menor número = mayor prioridad.

| Tipo de Operación         | Prioridad recomendada | Timeout recomendado (ms) |
|--------------------------|---------------------|-------------------------|
| Chat en tiempo real       | 1                   | 30000 (30s)             |
| Ejecución de herramientas | 2                   | 10000 (10s)             |
| Workflows interactivos    | 3                   | 60000 (60s)             |
| Consultas de configuración| 4                   | 5000 (5s)               |
| Procesamiento por lotes   | 5                   | 300000 (5min)           |
| Tareas de mantenimiento   | 10                  | 1800000 (30min)         |

## Manejo de Compatibilidad y Versionado

1. **Compatibilidad hacia atrás**: 
   - Todos los servicios deben soportar formatos de versiones anteriores
   - Campos nuevos siempre deben ser opcionales
   - Campos existentes no deben cambiar su tipo

2. **Estrategia de versionado**:
   - Versión Principal (1.0, 2.0): Cambios incompatibles
   - Versión Menor (1.1, 1.2): Adiciones compatibles
   - Cada servicio debe validar el campo `version` y aplicar transformaciones si es necesario

3. **Migración gradual**:
   - Periodo de migración: 3 meses para migración completa a nueva versión
   - Deprecación: Las versiones antiguas deben generar advertencias de log