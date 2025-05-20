# API Models Reference - Agent Service

Este documento proporciona una referencia detallada de los modelos de datos utilizados en los endpoints del Agent Service, su estructura y ejemplos de uso.

## Tabla de Contenidos

1. [Modelos de Agente](#modelos-de-agente)
   - [AgentCreate](#agentcreate)
   - [AgentUpdate](#agentupdate)
   - [Agent](#agent)
   - [AgentResponse](#agentresponse)
   - [AgentType](#agenttype)
   - [AgentState](#agentstate)
   - [AgentConfig](#agentconfig)

2. [Modelos de Conversación](#modelos-de-conversación)
   - [ChatRequest](#chatrequest)
   - [ChatResponse](#chatresponse)
   - [ConversationMessage](#conversationmessage)
   - [MessageRole](#messagerole)

3. [Modelos de Flujo](#modelos-de-flujo)
   - [FlowNode](#flownode)
   - [FlowNodeConnection](#flownodeconnection)
   - [FlowExecution](#flowexecution)
   - [FlowExecutionState](#flowexecutionstate)

4. [Ejemplos de API](#ejemplos-de-api)
   - [Crear un Agente](#ejemplo-crear-un-agente)
   - [Actualizar un Agente](#ejemplo-actualizar-un-agente)
   - [Chatear con un Agente](#ejemplo-chatear-con-un-agente)
   - [Listar Conversaciones](#ejemplo-listar-conversaciones)

---

## Modelos de Agente

### AgentType

Enumeración que define los tipos de agentes soportados por el sistema.

| Valor | Descripción |
|-------|-------------|
| `conversational` | Agente conversacional estándar |
| `flow` | Agente basado en flujos de trabajo |
| `rag` | Agente con capacidades de RAG (Retrieval-Augmented Generation) |
| `assistant` | Agente tipo asistente (para compatibilidad con OpenAI Assistants) |

### AgentState

Enumeración que define los estados posibles de un agente.

| Valor | Descripción |
|-------|-------------|
| `created` | Agente recién creado |
| `active` | Agente activo y disponible |
| `paused` | Agente pausado temporalmente |
| `deleted` | Agente eliminado (soft delete) |

### AgentConfig

Configuración detallada del comportamiento de un agente.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `system_prompt` | string | Sí | Prompt de sistema que define el comportamiento del agente |
| `temperature` | float | No (default: 0.7) | Temperatura para las respuestas del LLM (0-1) |
| `model` | string | No (default: "gpt-3.5-turbo") | Modelo LLM a utilizar |
| `max_tokens` | integer | No | Máximo de tokens en respuestas. Si es null, usa el valor por defecto del modelo |
| `context_window` | integer | No (default: 10) | Número de mensajes a mantener en contexto |
| `functions_enabled` | boolean | No (default: true) | Si las funciones/herramientas están habilitadas |
| `collection_ids` | array[string] | No | IDs de colecciones para RAG |
| `memory_enabled` | boolean | No (default: true) | Si la memoria de conversación está habilitada |
| `metadata` | object | No | Metadatos adicionales para personalizar el agente |

### AgentCreate

Modelo para crear un nuevo agente.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `name` | string | Sí | Nombre del agente |
| `description` | string | No | Descripción del agente |
| `type` | AgentType | Sí | Tipo de agente |
| `config` | AgentConfig | Sí | Configuración del agente |
| `tenant_id` | string | Sí | ID del tenant |
| `collection_ids` | array[string] | No | IDs de colecciones para RAG |
| `is_public` | boolean | No (default: false) | Si el agente es accesible públicamente |
| `metadata` | object | No | Metadatos adicionales |

### AgentUpdate

Modelo para actualizar un agente existente. Todos los campos son opcionales.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `name` | string | No | Nombre del agente |
| `description` | string | No | Descripción del agente |
| `type` | AgentType | No | Tipo de agente |
| `config` | AgentConfig | No | Configuración del agente |
| `collection_ids` | array[string] | No | IDs de colecciones para RAG |
| `is_public` | boolean | No | Si el agente es accesible públicamente |
| `state` | AgentState | No | Estado del agente |
| `metadata` | object | No | Metadatos adicionales |

### Agent

Modelo completo que representa un agente.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `agent_id` | string | Sí (autogenerado) | ID único del agente |
| `name` | string | Sí | Nombre del agente |
| `description` | string | No | Descripción del agente |
| `type` | AgentType | Sí | Tipo de agente |
| `config` | AgentConfig | Sí | Configuración del agente |
| `tenant_id` | string | Sí | ID del tenant |
| `collection_ids` | array[string] | No | IDs de colecciones para RAG |
| `is_public` | boolean | No (default: false) | Si el agente es accesible públicamente |
| `state` | AgentState | Sí (default: "created") | Estado del agente |
| `created_at` | datetime | Sí (autogenerado) | Timestamp de creación |
| `updated_at` | datetime | Sí (autogenerado) | Timestamp de última actualización |
| `metadata` | object | No | Metadatos adicionales |

### AgentResponse

Respuesta estándar para operaciones de agentes.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `success` | boolean | Sí | Si la operación fue exitosa |
| `message` | string | Sí | Mensaje descriptivo del resultado |
| `data` | Agent/[Agent]/object | No | Datos de respuesta (agente o lista de agentes) |
| `error` | string | No | Mensaje de error (si success=false) |

---

## Modelos de Conversación

### MessageRole

Enumeración que define los roles posibles en una conversación.

| Valor | Descripción |
|-------|-------------|
| `system` | Mensaje del sistema, define el comportamiento |
| `user` | Mensaje del usuario |
| `assistant` | Mensaje del asistente/agente |
| `function` | Resultado de una llamada a función |
| `tool` | Resultado de una llamada a herramienta |

### ConversationMessage

Modelo para un mensaje de conversación.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `message_id` | string | Sí (autogenerado) | ID único del mensaje |
| `conversation_id` | string | Sí | ID de la conversación |
| `agent_id` | string | Sí | ID del agente |
| `tenant_id` | string | Sí | ID del tenant |
| `role` | MessageRole | Sí | Rol del remitente del mensaje |
| `content` | string | Sí | Contenido del mensaje |
| `timestamp` | datetime | Sí (autogenerado) | Timestamp del mensaje |
| `metadata` | object | No | Metadatos adicionales del mensaje |

### ChatRequest

Modelo para una solicitud de chat.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `message` | string | Sí | Contenido del mensaje del usuario |
| `conversation_id` | string | No | ID de conversación (para continuar una conversación) |
| `agent_id` | string | Sí | ID del agente |
| `user_id` | string | No | ID del usuario, si aplica |
| `collection_ids` | array[string] | No | IDs de colecciones para RAG (sobreescribe las del agente) |
| `metadata` | object | No | Metadatos adicionales de la solicitud |

### ChatResponse

Modelo para una respuesta de chat.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `success` | boolean | Sí | Si la operación fue exitosa |
| `message` | string | Sí | Contenido de la respuesta del asistente |
| `conversation_id` | string | Sí | ID de la conversación |
| `agent_id` | string | Sí | ID del agente |
| `metadata` | object | No | Metadatos de la respuesta |
| `sources` | array[object] | No | Referencias de fuentes de RAG |
| `tools_used` | array[object] | No | Herramientas utilizadas para generar la respuesta |
| `thinking` | string | No | Proceso de razonamiento (si está habilitado) |
| `error` | string | No | Mensaje de error (si success=false) |

---

## Modelos de Flujo

### FlowNodeConnection

Conexión entre nodos de flujo.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `source_id` | string | Sí | ID del nodo origen |
| `target_id` | string | Sí | ID del nodo destino |
| `condition` | string | No | Condición opcional para la conexión |

### FlowNode

Nodo en un flujo.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `node_id` | string | Sí (autogenerado) | ID único del nodo |
| `flow_id` | string | Sí | ID del flujo |
| `type` | string | Sí | Tipo de nodo (agent, tool, condition, etc.) |
| `name` | string | Sí | Nombre del nodo |
| `config` | object | Sí | Configuración del nodo |
| `position` | object | Sí | Posición del nodo en la UI |
| `metadata` | object | No | Metadatos adicionales del nodo |

### FlowExecutionState

Enumeración que define los estados posibles de una ejecución de flujo.

| Valor | Descripción |
|-------|-------------|
| `created` | Ejecución creada |
| `active` | Ejecución en progreso |
| `paused` | Ejecución pausada |
| `completed` | Ejecución completada con éxito |
| `failed` | Ejecución fallida |

### FlowExecution

Modelo para una ejecución de flujo.

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `execution_id` | string | Sí (autogenerado) | ID único de la ejecución |
| `flow_id` | string | Sí | ID del flujo |
| `tenant_id` | string | Sí | ID del tenant |
| `state` | FlowExecutionState | Sí (default: "created") | Estado de la ejecución |
| `current_node_id` | string | No | ID del nodo que se está ejecutando actualmente |
| `start_time` | datetime | Sí (autogenerado) | Timestamp de inicio |
| `end_time` | datetime | No | Timestamp de finalización |
| `input_data` | object | No | Datos de entrada para el flujo |
| `output_data` | object | No | Datos de salida del flujo |
| `execution_history` | array[object] | Sí (default: []) | Historial de ejecuciones de nodos |
| `error_message` | string | No | Mensaje de error si falló |
| `metadata` | object | No | Metadatos adicionales de la ejecución |

---

## Ejemplos de API

### Ejemplo: Crear un Agente

#### Request

```http
POST /agents
Content-Type: application/json
X-Tenant-ID: tenant123

{
  "name": "Asistente de Ventas",
  "description": "Agente especializado en responder preguntas sobre productos",
  "type": "rag",
  "config": {
    "system_prompt": "Eres un asistente de ventas experto que ayuda a los clientes a encontrar los productos adecuados.",
    "temperature": 0.5,
    "model": "gpt-4",
    "max_tokens": 1000,
    "context_window": 15,
    "functions_enabled": true,
    "collection_ids": ["collection123", "collection456"],
    "memory_enabled": true
  },
  "tenant_id": "tenant123",
  "is_public": false,
  "metadata": {
    "department": "sales",
    "version": "1.0"
  }
}
```

#### Response

```json
{
  "success": true,
  "message": "Agent created successfully",
  "data": {
    "agent_id": "agent789",
    "name": "Asistente de Ventas",
    "description": "Agente especializado en responder preguntas sobre productos",
    "type": "rag",
    "config": {
      "system_prompt": "Eres un asistente de ventas experto que ayuda a los clientes a encontrar los productos adecuados.",
      "temperature": 0.5,
      "model": "gpt-4",
      "max_tokens": 1000,
      "context_window": 15,
      "functions_enabled": true,
      "collection_ids": ["collection123", "collection456"],
      "memory_enabled": true
    },
    "tenant_id": "tenant123",
    "collection_ids": ["collection123", "collection456"],
    "is_public": false,
    "state": "created",
    "created_at": "2025-05-20T20:05:51-03:00",
    "updated_at": "2025-05-20T20:05:51-03:00",
    "metadata": {
      "department": "sales",
      "version": "1.0"
    }
  }
}
```

### Ejemplo: Actualizar un Agente

#### Request

```http
PUT /agents/agent789
Content-Type: application/json
X-Tenant-ID: tenant123

{
  "name": "Asistente de Ventas Premium",
  "config": {
    "temperature": 0.3,
    "model": "gpt-4-turbo"
  },
  "state": "active"
}
```

#### Response

```json
{
  "success": true,
  "message": "Agent updated successfully",
  "data": {
    "agent_id": "agent789",
    "name": "Asistente de Ventas Premium",
    "description": "Agente especializado en responder preguntas sobre productos",
    "type": "rag",
    "config": {
      "system_prompt": "Eres un asistente de ventas experto que ayuda a los clientes a encontrar los productos adecuados.",
      "temperature": 0.3,
      "model": "gpt-4-turbo",
      "max_tokens": 1000,
      "context_window": 15,
      "functions_enabled": true,
      "collection_ids": ["collection123", "collection456"],
      "memory_enabled": true
    },
    "tenant_id": "tenant123",
    "collection_ids": ["collection123", "collection456"],
    "is_public": false,
    "state": "active",
    "created_at": "2025-05-20T20:05:51-03:00",
    "updated_at": "2025-05-20T20:15:30-03:00",
    "metadata": {
      "department": "sales",
      "version": "1.0"
    }
  }
}
```

### Ejemplo: Chatear con un Agente

#### Request

```http
POST /agents/agent789/chat
Content-Type: application/json
X-Tenant-ID: tenant123

{
  "message": "¿Cuáles son nuestros productos más vendidos?",
  "conversation_id": null,
  "agent_id": "agent789",
  "metadata": {
    "source": "website",
    "user_location": "Argentina"
  }
}
```

#### Response

```json
{
  "success": true,
  "message": "Nuestros productos más vendidos este mes son:\n\n1. Software de Gestión Empresarial Premium - 215 unidades\n2. Licencia de Análisis de Datos Pro - 189 unidades\n3. Suite de Seguridad Avanzada - 142 unidades\n\nEstos productos han tenido una excelente recepción, especialmente en Argentina donde las ventas han aumentado un 28% respecto al mes anterior.",
  "conversation_id": "conv123",
  "agent_id": "agent789",
  "metadata": {
    "token_usage": {
      "prompt_tokens": 342,
      "completion_tokens": 89,
      "total_tokens": 431
    },
    "latency_ms": 1240
  },
  "sources": [
    {
      "document_id": "doc456",
      "title": "Reporte de Ventas Mayo 2025",
      "url": "https://example.com/reports/sales-may-2025",
      "relevance_score": 0.89
    },
    {
      "document_id": "doc789",
      "title": "Análisis Regional LATAM",
      "url": "https://example.com/reports/latam-q2-2025",
      "relevance_score": 0.76
    }
  ],
  "tools_used": [
    {
      "tool_name": "RAGQueryTool",
      "execution_time_ms": 420,
      "query": "productos más vendidos estadísticas recientes"
    }
  ]
}
```

### Ejemplo: Listar Conversaciones

#### Request

```http
GET /agents/agent789/conversations?limit=5&offset=0
X-Tenant-ID: tenant123
```

#### Response

```json
{
  "success": true,
  "message": "Conversations retrieved successfully",
  "data": [
    {
      "conversation_id": "conv123",
      "agent_id": "agent789",
      "tenant_id": "tenant123",
      "title": "Consulta sobre productos más vendidos",
      "created_at": "2025-05-20T20:15:30-03:00",
      "updated_at": "2025-05-20T20:17:45-03:00",
      "message_count": 2,
      "last_message_preview": "Nuestros productos más vendidos este mes son...",
      "metadata": {
        "source": "website",
        "user_location": "Argentina"
      }
    },
    {
      "conversation_id": "conv456",
      "agent_id": "agent789",
      "tenant_id": "tenant123",
      "title": "Información sobre precios",
      "created_at": "2025-05-19T14:30:22-03:00",
      "updated_at": "2025-05-19T14:35:10-03:00",
      "message_count": 4,
      "last_message_preview": "Los precios de nuestros planes son los siguientes...",
      "metadata": {
        "source": "mobile_app",
        "user_location": "Chile"
      }
    }
  ],
  "pagination": {
    "total": 12,
    "limit": 5,
    "offset": 0,
    "has_more": true
  }
}
```

## Notas Importantes

1. **Autenticación y Autorización:**
   - Todos los endpoints requieren el header `X-Tenant-ID` para identificar el tenant.
   - Algunos endpoints pueden requerir autenticación adicional según la configuración del sistema.

2. **Manejo de Errores:**
   - Los errores siguen un formato estándar con `success: false` y un mensaje de error descriptivo.
   - Se incluyen códigos HTTP apropiados (400, 403, 404, 500, etc.) según el tipo de error.

3. **Paginación:**
   - Los endpoints que devuelven listas admiten parámetros de paginación (`limit` y `offset`).
   - Las respuestas incluyen metadatos de paginación cuando corresponde.

4. **Validación de Modelos:**
   - El servicio valida automáticamente el acceso a modelos LLM según el nivel de suscripción del tenant.
   - Algunos modelos premium pueden no estar disponibles para todos los tenants.

5. **Límites:**
   - Existen límites en la cantidad de agentes, herramientas y otros recursos según el nivel del tenant.
   - Los límites se verifican en tiempo de ejecución en los endpoints relevantes.
