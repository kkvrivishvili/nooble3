# Esquemas de Mensajes del Agent Orchestrator Service

## Introducción

Este documento define el esquema central de mensajes utilizados en la comunicación interna del Agent Orchestrator Service con otros servicios de la plataforma Nooble. Sirve como referencia canónica para todos los formatos de mensaje, identificando claramente campos obligatorios y opcionales.

## Control de Versiones

| Versión | Fecha       | Autor     | Cambios                             |
|---------|------------|-----------|-------------------------------------|
| 1.0.0   | 2025-06-04 | DevTeam   | Versión inicial                     |

## Formato Base de Mensaje

Este formato define la estructura común que todos los mensajes deben seguir, independientemente del servicio de destino.

```json
{
  "message_id": "uuid-v4",               // OBLIGATORIO: Identificador único del mensaje
  "tenant_id": "tenant-identifier",      // OBLIGATORIO: Identificador del tenant
  "timestamp": "ISO-8601",              // OBLIGATORIO: Timestamp de creación
  "version": "1.0",                    // OBLIGATORIO: Versión del formato
  "correlation_id": "uuid-v4",          // OBLIGATORIO: ID para correlacionar mensajes
  "source": "service-name",             // OBLIGATORIO: Servicio de origen
  "destination": "service-name",        // OBLIGATORIO: Servicio de destino
  "type": "request|response|event",     // OBLIGATORIO: Tipo de mensaje
  "status": "pending|processing|completed|failed", // OPCIONAL: Estado del mensaje
  "priority": 1-10,                     // OPCIONAL: Prioridad (1=alta, 10=baja)
  "task_id": "uuid-v4",                 // OPCIONAL: ID de tarea asociada
  "session_id": "uuid-v4",              // OPCIONAL: ID de sesión asociada
  "metadata": {                         // OPCIONAL: Metadatos adicionales
    // Campos específicos de metadata - ver abajo
  },
  "payload": {                          // OBLIGATORIO: Datos específicos del mensaje
    // Campos específicos de payload - ver abajo
  },
  "error": {                            // OPCIONAL: Presente solo si hay error
    "code": "error_code",
    "message": "Descripción del error",
    "details": {}
  },
  "retries": 0                          // OPCIONAL: Contador de reintentos
}
```

## Metadata Común

Todos los mensajes pueden incluir un objeto `metadata` con campos opcionales según el contexto:

### Campos Comunes de Metadata

| Campo           | Tipo     | Obligatorio | Descripción                                         |
|----------------|----------|------------|-----------------------------------------------------|
| conversation_id | string   | No         | ID de la conversación                               |
| workflow_id     | string   | No         | ID del workflow                                     |
| agent_id        | string   | No         | ID del agente                                       |
| execution_id    | string   | No         | ID de ejecución                                     |
| timeout_ms      | integer  | No         | Timeout en ms. Default: 30000 (30s)                 |
| trace_id        | string   | No         | ID de trazabilidad distribuida                      |
| user_id         | string   | No         | ID del usuario final                                |
| client_version  | string   | No         | Versión del cliente que origina la solicitud        |
| source_type     | string   | No         | Tipo de fuente (chat/batch/workflow)                |

## Especificaciones de Payload por Tipo de Servicio

Cada servicio utiliza una estructura específica para el `payload`. A continuación se detallan los formatos por servicio:

### Agent Execution Service

#### AgentExecutionRequest

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_orchestrator",
  "destination": "agent_execution",
  "type": "request",
  "payload": {
    "query": "string",                  // OBLIGATORIO: Consulta o instrucción
    "agent_config": {},                 // OBLIGATORIO: Configuración del agente
    "context": [],                      // OPCIONAL: Contexto adicional
    "stream": true,                     // OPCIONAL: Habilita streaming (default: false)
    "tools": [                          // OPCIONAL: Herramientas disponibles
      {
        "name": "string",
        "description": "string",
        "parameters": {}
      }
    ],
    "max_tokens": 1000                  // OPCIONAL: Límite de tokens (default: 1000)
  }
}
```

#### AgentExecutionResponse

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_execution",
  "destination": "agent_orchestrator",
  "type": "response",
  "payload": {
    "response": "string",               // OBLIGATORIO: Respuesta generada
    "completion_tokens": 150,           // OPCIONAL: Tokens usados en la respuesta
    "total_tokens": 450,                // OPCIONAL: Tokens totales (consulta + respuesta)
    "tool_calls": [],                   // OPCIONAL: Llamadas a herramientas realizadas
    "sources": []                       // OPCIONAL: Fuentes utilizadas
  }
}
```

### Conversation Service

#### ConversationTaskMessage

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_orchestrator",
  "destination": "conversation",
  "type": "request",
  "payload": {
    "message": "string",                // OBLIGATORIO: Contenido del mensaje
    "role": "user|assistant|system",    // OBLIGATORIO: Rol del mensaje
    "context": {},                      // OPCIONAL: Contexto adicional
    "attachments": [],                  // OPCIONAL: Archivos adjuntos
    "operation": "create|update|delete" // OBLIGATORIO: Tipo de operación
  }
}
```

### Workflow Engine Service

#### WorkflowTaskMessage

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_orchestrator",
  "destination": "workflow_engine",
  "type": "request",
  "payload": {
    "workflow_template_id": "string",   // OBLIGATORIO: ID del template de workflow
    "input_parameters": {},             // OPCIONAL: Parámetros de entrada
    "execution_mode": "async|sync",     // OPCIONAL: Modo de ejecución (default: async)
    "timeout_seconds": 300              // OPCIONAL: Timeout en segundos (default: 300)
  }
}
```

### Tool Registry Service

#### ToolExecutionMessage

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_orchestrator",
  "destination": "tool_registry",
  "type": "request",
  "payload": {
    "tool_name": "string",              // OBLIGATORIO: Nombre de la herramienta
    "parameters": {},                   // OBLIGATORIO: Parámetros para la ejecución
    "timeout_ms": 5000,                 // OPCIONAL: Timeout en milisegundos (default: 5000)
    "async": false,                     // OPCIONAL: Ejecución asíncrona (default: false)
    "result_callback": "string"         // OPCIONAL: URL de callback para async
  }
}
```

### Agent Management Service

#### AgentConfigMessage

```json
{
  // Campos base omitidos por brevedad
  "source": "agent_orchestrator",
  "destination": "agent_management",
  "type": "request",
  "payload": {
    "agent_id": "string",               // OBLIGATORIO: ID del agente
    "operation": "get|update",          // OBLIGATORIO: Tipo de operación
    "version": "string",                // OPCIONAL: Versión específica del agente
    "config_parameters": {},            // OPCIONAL: Parámetros de configuración
    "include_tools": true               // OPCIONAL: Incluir tools (default: true)
  }
}
```

## Estándar de Colas de Mensajes

Las colas para intercambio de mensajes entre servicios siguen el formato estándar:

```
{servicio}:{tipo}:{tenant_id}:{identificador_opcional}
```

### Colas por Servicio

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