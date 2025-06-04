# Comunicación con Tool Registry Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Visión General](#1-visión-general)
2. [Integración en Flujos de Trabajo](#2-integración-en-flujos-de-trabajo)
3. [Estructura de Colas](#3-estructura-de-colas)
4. [Formato de Mensajes](#4-formato-de-mensajes)
5. [Comunicación WebSocket](#5-comunicación-websocket)
6. [REST API](#6-rest-api)
7. [Gestión de Errores](#7-gestión-de-errores)

## 1. Visión General

El Tool Registry Service es responsable del registro, validación y ejecución de herramientas (tools) que pueden ser utilizadas por los agentes en la plataforma Nooble. Este servicio proporciona un mecanismo central para descubrir y utilizar herramientas de forma segura y controlada.

### 1.1 Principios de Comunicación

La comunicación entre el Agent Orchestrator Service y el Tool Registry Service se rige por los siguientes principios:

1. **Centralización**: El Agent Orchestrator Service actúa como punto de entrada único para todas las solicitudes de registro, descubrimiento y ejecución de herramientas.

2. **Aislamiento Multi-tenant**: Toda comunicación incluye identificación de tenant para garantizar el aislamiento de datos.

3. **Asincronía**: Las operaciones de larga duración (como validación y ejecución de herramientas externas) se procesan de forma asíncrona mediante colas.

4. **Notificaciones en Tiempo Real**: El uso de WebSockets para recibir actualizaciones inmediatas sobre el estado de ejecución de herramientas.

### 1.2 Responsabilidades del Orchestrator

En la comunicación con el Tool Registry Service, el Agent Orchestrator Service es responsable de:

1. **Enrutar solicitudes** de agentes y workflows para la ejecución de herramientas
2. **Validar permisos** de acceso a herramientas específicas
3. **Procesar resultados** de la ejecución de herramientas y reenviarlos a los servicios solicitantes
4. **Propagar eventos** de estado de herramientas a los clientes frontend
5. **Gestionar errores** y reintentos en caso de fallos

## 2. Integración en Flujos de Trabajo

### 2.1 Ejecución de Herramientas desde Agentes

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator as Agent Orchestrator
    participant AES as Agent Execution Service
    participant TRS as Tool Registry Service
    
    Cliente->>Orchestrator: Solicita ejecución con herramientas
    Orchestrator->>AES: Inicia ejecución del agente
    AES->>Orchestrator: Solicita herramientas disponibles
    Orchestrator->>TRS: get_available_tools(tenant_id, agent_id)
    TRS-->>Orchestrator: Lista de herramientas disponibles
    Orchestrator-->>AES: Herramientas disponibles
    AES->>Orchestrator: Solicita ejecutar herramienta
    Orchestrator->>TRS: execute_tool(tool_id, params)
    Note over TRS: Ejecución asíncrona
    TRS-->>Orchestrator: task_id (WebSocket)
    TRS->>TRS: Procesa herramienta
    TRS-->>Orchestrator: Notifica resultado (WebSocket)
    Orchestrator-->>AES: Resultado herramienta
    AES-->>Orchestrator: Respuesta procesada
    Orchestrator-->>Cliente: Entrega respuesta
```

### 2.2 Registro de Nueva Herramienta

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator as Agent Orchestrator
    participant TRS as Tool Registry Service
    
    Cliente->>Orchestrator: Registrar nueva herramienta
    Orchestrator->>TRS: register_tool(tool_config)
    Note over TRS: Validación asíncrona
    TRS-->>Orchestrator: registration_task_id
    TRS->>TRS: Valida configuración
    TRS->>TRS: Prueba conexión (si es API externa)
    alt Validación exitosa
        TRS-->>Orchestrator: Notifica registro completo (WebSocket)
        Orchestrator-->>Cliente: Herramienta registrada
    else Error de validación
        TRS-->>Orchestrator: Notifica error (WebSocket)
        Orchestrator-->>Cliente: Error en registro
    end
```

### 2.3 Ejecución desde Workflow

```mermaid
sequenceDiagram
    participant Orchestrator as Agent Orchestrator
    participant WES as Workflow Engine Service
    participant TRS as Tool Registry Service
    
    WES->>Orchestrator: Ejecutar paso con herramienta
    Orchestrator->>TRS: execute_tool(tool_id, params)
    TRS-->>Orchestrator: task_id
    Note over TRS: Ejecución asíncrona
    TRS->>TRS: Procesa herramienta
    TRS-->>Orchestrator: Notifica resultado (WebSocket)
    Orchestrator-->>WES: Resultado herramienta
    WES->>WES: Continúa workflow
```

## 3. Estructura de Colas

El Agent Orchestrator Service produce y consume varias colas Redis para la comunicación con el Tool Registry Service. Siguiendo el estándar global de comunicación, todas las colas utilizan la convención `service-name.[priority].[domain].[action]` para facilitar el enrutamiento, monitoreo y escalabilidad de forma consistente.

### 3.1 Colas que Produce el Orchestrator

| Cola | Domain | Action | Propósito | Prioridad | Consumidor |
|------|--------|--------|-----------|-----------|------------|
| `orchestrator.standard.tool.execute` | `tool` | `execute` | Solicitudes de ejecución de herramientas | Estándar | Tool Registry Service |
| `orchestrator.standard.tool.register` | `tool` | `register` | Registro de nuevas herramientas | Estándar | Tool Registry Service |
| `orchestrator.standard.tool.discover` | `tool` | `discover` | Descubrimiento de herramientas disponibles | Estándar | Tool Registry Service |

### 3.2 Colas que Consume el Orchestrator

| Cola | Domain | Action | Propósito | Prioridad | Productor |
|------|--------|--------|-----------|-----------|----------|
| `tool-registry.standard.tool.result` | `tool` | `result` | Resultados de ejecución de herramientas | Estándar | Tool Registry Service |
| `tool-registry.standard.tool.error` | `tool` | `error` | Errores de ejecución de herramientas | Alta | Tool Registry Service |
| `tool-registry.low.tool.status` | `tool` | `status` | Actualizaciones de estado de herramientas | Baja | Tool Registry Service |

## 4. Formato de Mensajes

### 4.1 Estructura Base de Mensajes

Todos los mensajes intercambiados entre Agent Orchestrator Service y Tool Registry Service siguen el estándar global domain/action con la siguiente estructura base:

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",  // ID único del mensaje
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",  // ID para seguimiento de flujos
  "task_id": "550e8400-e29b-41d4-a716-446655440002",  // ID de la tarea 
  "tenant_id": "tenant-identifier",  // ID del tenant
  "schema_version": "1.1",           // Versión del esquema
  "created_at": "2025-06-03T15:23:10.123Z",  // Timestamp ISO-8601 con milisegundos
  "type": {
    "domain": "tool",                // Dominio del mensaje (tool, agent, system, etc)
    "action": "execute"              // Acción dentro del dominio (execute, register, discover, etc)
  },
  "source_service": "orchestrator",   // Servicio que origina el mensaje
  "target_service": "tool_registry", // Servicio destinatario
  "priority": 2,                     // Prioridad (0-9, 9 es la más alta)
  "metadata": {                      // Metadatos adicionales para trazabilidad
    "trace_id": "trace-xyz123",      // ID de traza para observabilidad
    "user_id": "user-identifier",    // ID del usuario que origina la solicitud
    "session_id": "session-123"      // ID de sesión si aplica
  },
  "payload": {}                      // Datos específicos de la operación
}
```

### 4.2 Campos Estándar de Control

| Campo | Tipo | Descripción | Obligatorio |
|-------|------|-------------|-------------|
| `message_id` | String (UUID) | Identificador único del mensaje | Sí |
| `correlation_id` | String (UUID) | Identificador para correlacionar mensajes relacionados | Sí |
| `task_id` | String (UUID) | Identificador de la tarea que genera el mensaje | Sí |
| `tenant_id` | String | Identificador del tenant (cliente) | Sí |
| `schema_version` | String | Versión del esquema de mensajes (e.g. "1.1") | Sí |
| `created_at` | String (ISO-8601) | Timestamp con formato ISO-8601 y milisegundos | Sí |
| `type.domain` | String | Dominio funcional del mensaje | Sí |
| `type.action` | String | Acción específica dentro del dominio | Sí |
| `source_service` | String | Servicio que origina el mensaje | Sí |
| `target_service` | String | Servicio destinatario | Sí |
| `priority` | Integer (0-9) | Prioridad del mensaje | Sí |

### 4.3 Mensaje de Ejecución de Herramienta

El Agent Orchestrator Service envía este mensaje para solicitar la ejecución de una herramienta.

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "task_id": "550e8400-e29b-41d4-a716-446655440002",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:05:23.456Z",
  "type": {
    "domain": "tool",
    "action": "execute"
  },
  "source_service": "orchestrator",
  "target_service": "tool_registry",
  "priority": 2,
  "metadata": {
    "trace_id": "trace-xyz123",
    "user_id": "user-identifier",
    "session_id": "session-identifier",
    "timeout_ms": 30000
  },
  "payload": {
    "tool_id": "weather-api-tool",
    "parameters": {
      "city": "Madrid",
      "units": "metric"
    },
    "execution_context": {
      "agent_id": "customer-support-agent",
      "user_query": "Cómo estará el tiempo hoy en Madrid?"
    }
  }
}
```

### 4.4 Mensaje de Registro de Herramienta

El Agent Orchestrator Service envía este mensaje para registrar una nueva herramienta en el catálogo.

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440003",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440004",
  "task_id": "550e8400-e29b-41d4-a716-446655440005",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T16:42:15.789Z",
  "type": {
    "domain": "tool",
    "action": "register"
  },
  "source_service": "orchestrator",
  "target_service": "tool_registry",
  "priority": 1,
  "metadata": {
    "trace_id": "trace-admin123",
    "user_id": "admin-identifier",
    "origin": "admin-portal"
  },
  "payload": {
    "tool": {
      "name": "Weather API Tool",
      "id": "weather-api-tool",
      "description": "Obtiene datos meteorológicos actuales y pronósticos",
      "version": "1.0.0",
      "schema": {
        "type": "object",
        "properties": {
          "city": {
            "type": "string",
            "description": "Ciudad para la consulta meteorológica"
          },
          "units": {
            "type": "string",
            "enum": ["metric", "imperial"],
            "default": "metric"
          }
        },
        "required": ["city"]
      },
      "authentication": {
        "type": "api_key",
        "header_name": "X-API-Key"
      },
      "category": "information_retrieval",
      "tags": ["weather", "forecast"],
      "timeout_ms": 15000
    }
  }
}
```

### 4.5 Mensaje de Descubrimiento de Herramientas

Mensaje enviado por el Agent Orchestrator Service para consultar herramientas disponibles para un tenant.

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440006",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440007",
  "task_id": "550e8400-e29b-41d4-a716-446655440008",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:01:08.432Z",
  "type": {
    "domain": "tool",
    "action": "discover"
  },
  "source_service": "orchestrator",
  "target_service": "tool_registry",
  "priority": 1,
  "metadata": {
    "trace_id": "trace-xyz456",
    "user_id": "user-identifier",
    "session_id": "session-identifier",
    "agent_id": "research-assistant"
  },
  "payload": {
    "query": "weather",
    "limit": 10,
    "categories": ["information_retrieval"],
    "include_schemas": true
  }
}
```

### 4.6 Mensaje de Resultado de Herramienta

Mensaje enviado por el Tool Registry Service al Orchestrator con los resultados de la ejecución.

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440009",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",  // Mismo correlation_id de la solicitud original
  "task_id": "550e8400-e29b-41d4-a716-446655440010",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:10:05.321Z",
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "priority": 2,
  "metadata": {
    "trace_id": "trace-xyz123",  // Mismo trace_id para seguimiento completo
    "source_task_id": "550e8400-e29b-41d4-a716-446655440002",  // task_id original
    "session_id": "session-identifier",
    "execution_time_ms": 1253
  },
  "payload": {
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "result": {
      "temperature": 22.5,
      "humidity": 45,
      "conditions": "Parcialmente nublado",
      "forecast": [
        {
          "day": "tomorrow",
          "temperature": 24.0,
          "conditions": "Soleado"
        }
      ]
    },
    "status": "completed"
  }
}
```

### 4.7 Mensaje de Error de Herramienta

Mensaje enviado por el Tool Registry Service al Orchestrator para notificar errores en la ejecución.

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440011",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",  // Mismo correlation_id de la solicitud original
  "task_id": "550e8400-e29b-41d4-a716-446655440012",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:06:28.765Z",
  "type": {
    "domain": "tool",
    "action": "error"
  },
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "priority": 3,  // Mayor prioridad para errores
  "metadata": {
    "trace_id": "trace-xyz123",  // Mismo trace_id para seguimiento completo
    "source_task_id": "550e8400-e29b-41d4-a716-446655440002",  // task_id original
    "session_id": "session-identifier",
    "execution_time_ms": 532
  },
  "error": {
    "code": "tool.execute.rate_limit_exceeded",  // Formato domain.action.error_type
    "message": "API rate limit exceeded",
    "details": "El proveedor externo ha rechazado la solicitud por exceso de peticiones",
    "severity": "warning",
    "context": {
      "tool_id": "weather-api-tool",
      "execution_id": "exec-12345",
      "status_code": 429,
      "retry_after": 60,
      "retryable": true
    }
  }
}
```

## 5. Comunicación WebSocket

El Agent Orchestrator Service se suscribe a eventos del Tool Registry Service a través de WebSockets para recibir actualizaciones en tiempo real sobre el estado de ejecución de las herramientas. Siguiendo el estándar global domain/action, los mensajes WebSocket también utilizan esta estructura para mantener la consistencia.

### 5.1 Mensajes WebSocket

| Domain | Action | Descripción | Emisor | Destinatario |
|--------|--------|------------|-------|-------------|
| `tool` | `status` | Actualiza el estado de ejecución | Tool Registry | Orchestrator |
| `tool` | `result` | Notifica ejecución exitosa con resultados | Tool Registry | Orchestrator |
| `tool` | `error` | Notifica error en ejecución | Tool Registry | Orchestrator |
| `subscription` | `register` | Registra suscriptor para recibir actualizaciones | Orchestrator | Tool Registry |

### 5.2 Formato de Mensajes WebSocket

#### 5.2.1 Mensaje de Estado de Herramienta

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440013",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",  // Relaciona con la solicitud original
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:10:02.654Z",
  "type": {
    "domain": "tool",
    "action": "status"
  },
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "metadata": {
    "trace_id": "trace-xyz123",
    "session_id": "session-identifier"
  },
  "payload": {
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "status": "processing",
    "progress": 25,
    "message": "Ejecución de herramienta iniciada",
    "estimated_completion_ms": 5000
  }
}
```

#### 5.2.2 Mensaje de Resultado de Herramienta (WebSocket)

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440014",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:10:05.321Z",
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "metadata": {
    "trace_id": "trace-xyz123",
    "session_id": "session-identifier"
  },
  "payload": {
    "tool_id": "weather-api-tool",
    "execution_id": "exec-12345",
    "result": {
      "temperature": 22.5,
      "humidity": 45,
      "conditions": "Parcialmente nublado"
    },
    "execution_time_ms": 3245
  }
}
```

#### 5.2.3 Mensaje de Error de Herramienta (WebSocket)

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440015",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:10:05.789Z",
  "type": {
    "domain": "tool",
    "action": "error"
  },
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "metadata": {
    "trace_id": "trace-xyz123",
    "session_id": "session-identifier"
  },
  "error": {
    "code": "tool.execute.rate_limit_exceeded",
    "message": "API rate limit exceeded",
    "details": "El proveedor externo ha rechazado la solicitud por exceso de peticiones",
    "severity": "warning",
    "context": {
      "tool_id": "weather-api-tool",
      "execution_id": "exec-12345",
      "retryable": true,
      "retry_after": 60
    }
  }
}
```

#### 5.2.4 Registro de Suscripción

```json
{
  "message_id": "550e8400-e29b-41d4-a716-446655440016",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440017",
  "tenant_id": "tenant-identifier",
  "schema_version": "1.1",
  "created_at": "2025-06-03T17:09:45.123Z",
  "type": {
    "domain": "subscription",
    "action": "register"
  },
  "source_service": "orchestrator",
  "target_service": "tool_registry",
  "metadata": {
    "trace_id": "trace-xyz123",
    "session_id": "session-identifier"
  },
  "payload": {
    "subscription_id": "sub-12345",
    "client_id": "orchestrator-instance-1",
    "domains": ["tool"],
    "actions": ["status", "result", "error"],
    "filters": {
      "tool_ids": ["weather-api-tool", "calculator-tool"],
      "agent_id": "research-assistant"
    }
  }
}
```

### 5.3 Implementación de Cliente WebSocket

```python
import websockets
import json
import asyncio
import uuid
from datetime import datetime

class ToolRegistryWebSocketClient:
    def __init__(self, tenant_id, session_id):
        self.ws_uri = "wss://tool-registry.nooble.internal/ws"
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.client_id = f"orchestrator-{uuid.uuid4()}"
        self.trace_id = str(uuid.uuid4())
        self.ws = None
        self.handlers = {
            # Manejadores por domain/action
            "tool.status": self._handle_tool_status,
            "tool.result": self._handle_tool_result,
            "tool.error": self._handle_tool_error
        }

    async def connect(self):
        headers = {
            "X-Tenant-ID": self.tenant_id,
            "Authorization": f"Bearer {self._get_service_token()}"
        }
        self.ws = await websockets.connect(self.ws_uri, extra_headers=headers)
        
        # Registrar suscripción
        await self.register_subscription()
        
        # Iniciar bucle de escucha
        asyncio.create_task(self._listen())

    async def register_subscription(self):
        subscription_message = {
            "message_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()),
            "tenant_id": self.tenant_id,
            "schema_version": "1.1",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "type": {
                "domain": "subscription",
                "action": "register"
            },
            "source_service": "orchestrator",
            "target_service": "tool_registry",
            "metadata": {
                "trace_id": self.trace_id,
                "session_id": self.session_id
            },
            "payload": {
                "subscription_id": str(uuid.uuid4()),
                "client_id": self.client_id,
                "domains": ["tool"],
                "actions": ["status", "result", "error"]
            }
        }
        await self.ws.send(json.dumps(subscription_message))

    async def _listen(self):
        try:
            async for message in self.ws:
                await self._process_message(json.loads(message))
        except Exception as e:
            print(f"Error en WebSocket: {str(e)}")
            # Implementar reconexión

    async def _process_message(self, message):
        # Validar estructura domain/action
        if "type" in message and isinstance(message["type"], dict):
            domain = message["type"].get("domain")
            action = message["type"].get("action")
            
            if domain and action:
                # Clave compuesta para el manejador
                handler_key = f"{domain}.{action}"
                
                # Buscar y ejecutar manejador adecuado
                if handler_key in self.handlers:
                    await self.handlers[handler_key](message)
                else:
                    print(f"No se encontró manejador para {handler_key}")
        else:
            print("Mensaje recibido no cumple con el esquema domain/action")

    async def _handle_tool_status(self, message):
        # Procesar actualización de estado
        payload = message.get("payload", {})
        tool_id = payload.get("tool_id")
        status = payload.get("status")
        progress = payload.get("progress")
        print(f"Estado de herramienta {tool_id}: {status} ({progress}%)")
        # Actualizar estado interno o notificar a otros componentes

    async def _handle_tool_result(self, message):
        # Procesar resultado
        payload = message.get("payload", {})
        tool_id = payload.get("tool_id")
        result = payload.get("result")
        # Procesar resultados y enviarlos al componente correspondiente

    async def _handle_tool_error(self, message):
        # Procesar error
        error = message.get("error", {})
        code = error.get("code")
        msg = error.get("message")
        context = error.get("context", {})
        tool_id = context.get("tool_id")
        print(f"Error en herramienta {tool_id}: {code} - {msg}")
        # Manejar estrategia de recuperación según el tipo de error

    def _get_service_token(self):
        # Obtener token de autenticación de servicio
        return "service-auth-token"
```

## 6. REST API

### 6.1 Endpoints y Headers Estándar

Todas las API REST entre Agent Orchestrator Service y Tool Registry Service siguen el estándar global de comunicación con los siguientes headers:

| Header | Descripción | Obligatorio |
|--------|-------------|-------------|
| `Authorization` | Bearer token para autenticación de servicio | Sí |
| `X-Tenant-ID` | Identificador del tenant | Sí |
| `X-Correlation-ID` | ID para correlacionar peticiones relacionadas | Sí |
| `X-Schema-Version` | Versión del esquema de comunicación | Sí |
| `X-Trace-ID` | ID de trazabilidad para observabilidad | Sí |
| `X-Source-Service` | Servicio que origina la solicitud | Sí |
| `Content-Type` | Tipo de contenido, siempre `application/json` | Sí |

### 6.2 APIs que Consume el Orchestrator

| Endpoint | Método | Domain | Action | Propósito |
|----------|--------|--------|--------|----------|
| `/api/v1/tools` | `GET` | `tool` | `list` | Listar herramientas disponibles |
| `/api/v1/tools/{tool_id}` | `GET` | `tool` | `get` | Obtener detalles de herramienta |
| `/api/v1/tools/execute` | `POST` | `tool` | `execute` | Ejecutar herramienta sincrónica |
| `/api/v1/tools/async-execute` | `POST` | `tool` | `async_execute` | Ejecutar herramienta asincrónica |

### 6.3 APIs que Expone el Orchestrator para el Tool Registry

| Endpoint | Método | Domain | Action | Propósito |
|----------|--------|--------|--------|----------|
| `/api/v1/orchestrator/tool-callbacks` | `POST` | `tool` | `callback` | Recibir resultados de ejecución |
| `/api/v1/orchestrator/service-auth/validate` | `POST` | `auth` | `validate` | Validar autenticación de servicio |

### 6.4 Ejemplos de Llamadas

#### Ejecución Sincrónica de Herramienta

```http
POST /api/v1/tools/execute HTTP/1.1
Host: tool-registry.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
X-Tenant-ID: tenant-identifier
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440001
X-Schema-Version: 1.1
X-Trace-ID: trace-abc123
X-Source-Service: orchestrator

{
  "type": {
    "domain": "tool",
    "action": "execute"
  },
  "message_id": "550e8400-e29b-41d4-a716-446655440020",
  "metadata": {
    "agent_id": "math-tutor",
    "session_id": "session-123"
  },
  "payload": {
    "tool_id": "calculator-v1",
    "parameters": {
      "expression": "2*(3+4)"
    }
  }
}
```

**Respuesta:**

```json
{
  "type": {
    "domain": "tool",
    "action": "result"
  },
  "message_id": "550e8400-e29b-41d4-a716-446655440021",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "created_at": "2025-06-03T17:12:45.123Z",
  "schema_version": "1.1",
  "metadata": {
    "trace_id": "trace-abc123",
    "execution_time_ms": 25
  },
  "payload": {
    "task_id": "task-789",
    "status": "completed",
    "result": {
      "value": 14,
      "formatted_value": "14"
    }
  }
}
```

#### Solicitud de Herramientas Disponibles

```http
GET /api/v1/tools?agent_id=research-assistant&types=rag,external_api HTTP/1.1
Host: tool-registry.nooble.internal
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Tenant-ID: tenant-identifier
X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440030
X-Schema-Version: 1.1
X-Trace-ID: trace-xyz456
X-Source-Service: orchestrator
```

**Respuesta:**

```json
{
  "type": {
    "domain": "tool",
    "action": "list"
  },
  "message_id": "550e8400-e29b-41d4-a716-446655440031",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440030",
  "created_at": "2025-06-03T17:14:22.456Z",
  "schema_version": "1.1",
  "metadata": {
    "trace_id": "trace-xyz456",
    "count": 2,
    "total": 2
  },
  "payload": {
    "tools": [
      {
        "tool_id": "document-search",
        "tool_name": "Buscador de Documentos",
        "tool_type": "rag",
        "description": "Busca información en documentos del usuario",
        "version": "2.1.0",
        "parameters_schema": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Consulta de búsqueda"
            },
            "limit": {
              "type": "integer",
              "default": 5
            }
          },
          "required": ["query"]
        }
      },
      {
        "tool_id": "weather-api",
        "tool_name": "Weather API",
        "tool_type": "external_api",
        "description": "Obtiene información meteorológica actualizada",
        "version": "1.0.0",
        "parameters_schema": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "Ciudad o coordenadas"
            },
            "units": {
              "type": "string",
              "default": "metric",
              "enum": ["metric", "imperial"]
            }
          },
          "required": ["location"]
        }
      }
    ],
    "pagination": {
      "total": 2,
      "page": 1,
      "limit": 20
    }
  }
}
```

### 6.5 Ejemplo de Implementación de Cliente Python

```python
import httpx
import uuid
from datetime import datetime

class ToolRegistryClient:
    def __init__(self, base_url, tenant_id, service_token):
        self.base_url = base_url
        self.tenant_id = tenant_id
        self.service_token = service_token
        self.source_service = "orchestrator"
        self.schema_version = "1.1"
        
    async def execute_tool(self, tool_id, parameters, agent_id=None, session_id=None, timeout_ms=30000):
        """Ejecuta una herramienta de forma sincrónica"""
        # Crear headers estándar
        correlation_id = str(uuid.uuid4())
        trace_id = f"trace-{uuid.uuid4().hex[:8]}"
        
        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "Content-Type": "application/json",
            "X-Tenant-ID": self.tenant_id,
            "X-Correlation-ID": correlation_id,
            "X-Schema-Version": self.schema_version,
            "X-Trace-ID": trace_id,
            "X-Source-Service": self.source_service
        }
        
        # Crear mensaje con formato domain/action
        request_data = {
            "type": {
                "domain": "tool",
                "action": "execute"
            },
            "message_id": str(uuid.uuid4()),
            "metadata": {
                "agent_id": agent_id,
                "session_id": session_id,
                "timeout_ms": timeout_ms
            },
            "payload": {
                "tool_id": tool_id,
                "parameters": parameters
            }
        }
        
        # Ejecutar solicitud HTTP
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/tools/execute",
                headers=headers,
                json=request_data,
                timeout=timeout_ms/1000
            )
            
            # Procesar respuesta
            if response.status_code == 200:
                result = response.json()
                
                # Validar formato domain/action
                if (result.get("type", {}).get("domain") == "tool" and 
                    result.get("type", {}).get("action") == "result"):
                    
                    return result.get("payload", {})
                
                # Manejar error
                elif result.get("type", {}).get("action") == "error":
                    error = result.get("error", {})
                    raise ToolExecutionError(
                        f"Error ejecutando herramienta: {error.get('message')}",
                        code=error.get("code"),
                        details=error.get("details")
                    )
                    
            # Error HTTP
            response.raise_for_status()
            
    # Otros métodos del cliente...
```

## 7. Gestión de Errores

### 7.1 Estrategias de Manejo de Fallos

| Tipo de Error | Estrategia | Implementación |
|---------------|------------|----------------|
| **Error en API Externa** | Reintentos configurables | El Orchestrator reintenta la ejecución de herramientas con problemas temporales |

### 7.2 Códigos de Error

| Código | Descripción | Severidad | ¿Reintentar? |
|---------|-------------|-----------|-------------|
| `tool.get.not_found` | Herramienta no encontrada | Alto | No |
| `tool.execute.invalid_parameters` | Parámetros inválidos | Medio | Solo con corrección |
| `tool.execute.internal_error` | Error durante ejecución | Alto | Sí - 3 intentos |
| `tool.execute.rate_limit_exceeded` | Límite de API excedido | Medio | Sí - con backoff |
| `tool.execute.timeout` | Timeout en API externa | Medio | Sí - 3 intentos |
| `tool.execute.permission_denied` | Permiso denegado | Alto | No |
| `tool.register.duplicate` | Herramienta ya registrada | Medio | No |
| `auth.validate.invalid_token` | Token de autenticación inválido | Alto | No |

### 7.3 Estructura de Error en Respuestas HTTP

```json
{
  "type": {
    "domain": "tool",
    "action": "error"
  },
  "message_id": "550e8400-e29b-41d4-a716-446655440025",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
  "created_at": "2025-06-03T17:16:28.765Z",
  "schema_version": "1.1",
  "source_service": "tool_registry",
  "target_service": "orchestrator",
  "metadata": {
    "trace_id": "trace-xyz123",
    "http_status": 400
  },
  "error": {
    "code": "tool.execute.invalid_parameters",
    "message": "Los parámetros proporcionados son inválidos",
    "details": "El parámetro 'location' no puede estar vacío para la herramienta weather-api",
    "severity": "warning",
    "context": {
      "parameter": "location",
      "reason": "empty_value",
      "tool_id": "weather-api",
      "retryable": true,
      "retry_after": 0
    }
  }
}
```

### 7.4 Circuito de Recuperación

La gestión de errores entre Agent Orchestrator Service y Tool Registry Service implementa un patrón robusto:

1. **Detección y clasificación**: Los errores son clasificados según su dominio, acción y tipo específico.

2. **Estrategia de recuperación**: Cada tipo de error implementa una estrategia de recuperación específica:
   - Para errores con `"context.retryable": true`, se aplica el patrón de reintento.
   - Si `"context.retry_after" > 0`, se implementa espera antes del siguiente intento.
   - Para errores permanentes, se notifica inmediatamente al consumidor.

3. **Registro y monitoreo**: Los errores son registrados y monitoreados utilizando el identificador `correlation_id` y `trace_id` para mantener trazabilidad completa.

4. **Notificación**: Se utilizan los canales apropiados (mensajería, WebSocket, API) según el contexto del error.

### 7.5 Circuit Breaker

El Agent Orchestrator implementa un Circuit Breaker para el Tool Registry Service:

```python
class ToolServiceCircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_time_seconds=30, window_seconds=60):
        self.failure_threshold = failure_threshold  # Fallos necesarios para abrir
        self.recovery_time_seconds = recovery_time_seconds  # Tiempo hasta semi-abierto
        self.window_seconds = window_seconds  # Período para contar fallos
        
        self.failures = []  # Lista de timestamps de fallos
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.opened_at = None  # Cuándo se abrió el circuit breaker
    
    def record_failure(self, error_code):
        """Registra un fallo y actualiza el estado"""
        current_time = datetime.now()
        
        # Eliminar fallos fuera de la ventana de tiempo
        self.failures = [t for t in self.failures 
                        if (current_time - t).total_seconds() <= self.window_seconds]
        
        # Añadir nuevo fallo
        self.failures.append(current_time)
        
        # Verificar si se debe abrir el circuito
        if len(self.failures) >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = current_time
            logger.warning(f"Circuit breaker ABIERTO para Tool Registry. Error: {error_code}")
    
    def allow_request(self):
        """Determina si una petición debe ser permitida"""
        current_time = datetime.now()
        
        if self.state == "CLOSED":
            return True
            
        elif self.state == "OPEN":
            # Verificar si es hora de probar recuperación
            elapsed = (current_time - self.opened_at).total_seconds()
            if elapsed >= self.recovery_time_seconds:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker pasando a estado HALF_OPEN")
                return True
            return False
            
        elif self.state == "HALF_OPEN":
            # En estado semi-abierto, solo se permite una petición
            return True
            
        return False
    
    def record_success(self):
        """Registra una llamada exitosa"""
        if self.state == "HALF_OPEN":
            # Restaurar el circuito si una llamada es exitosa en estado semi-abierto
            self.state = "CLOSED"
            self.failures = []
            self.opened_at = None
            logger.info("Circuit breaker restaurado a estado CLOSED")
```

### 7.6 Política de Reintentos

| Código | Estrategia | Max Intentos | Backoff Inicial | Backoff Máximo |
|---------|------------|-------------|----------------|----------------|
| `tool.execute.timeout` | Exponencial | 3 | 1s | 8s |
| `tool.execute.rate_limit_exceeded` | Fijo | 5 | según retry_after | según retry_after |
| `tool.execute.invalid_parameters` | Ninguna | 0 | N/A | N/A |
| `tool.execute.internal_error` | Exponencial | 2 | 2s | 8s |

### 7.7 Ejemplo de Implementación de Manejo de Error

```python
async def handle_tool_error(error):
    """Maneja un error de herramienta según su código"""
    error_code = error.get("code", "")
    context = error.get("context", {})
    retryable = context.get("retryable", False)
    retry_after = context.get("retry_after", 0)
    
    # Registrar el error
    logger.error(
        f"Error de herramienta: {error_code}", 
        extra={
            "trace_id": error.get("metadata", {}).get("trace_id"),
            "correlation_id": error.get("correlation_id"),
            "tool_id": context.get("tool_id")
        }
    )
    
    # Verificar si se puede reintentar
    if not retryable:
        # Error irrecuperable, notificar inmediatamente
        await notify_error_to_consumer(error)
        return
    
    # Aplicar estrategia de reintento según el tipo de error
    if error_code == "tool.execute.rate_limit_exceeded":
        # Reintento con tiempo fijo
        await retry_with_fixed_delay(context.get("tool_id"), retry_after)
    
    elif error_code == "tool.execute.timeout":
        # Reintento con backoff exponencial
        await retry_with_exponential_backoff(context.get("tool_id"), max_attempts=3)
    
    elif error_code == "tool.execute.internal_error":
        # Reintento con backoff más agresivo
        await retry_with_exponential_backoff(context.get("tool_id"), 
                                          initial_backoff=2,
                                          max_attempts=2)
```

---

## Registro de Cambios

| Versión | Fecha | Autor | Descripción |
|---------|-------|-------|-------------|
| 1.0.0 | 2025-06-03 | Equipo Nooble Backend | Versión inicial |
