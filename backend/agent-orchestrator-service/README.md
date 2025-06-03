# Agent Orchestrator Service

## Descripción
Servicio central que coordina las interacciones entre el usuario y los diferentes servicios del sistema. Actúa como un punto de entrada unificado para gestionar el flujo de las solicitudes, mantener el estado de las sesiones, y orquestar la comunicación entre los múltiples microservicios de la plataforma.

## Estructura
```
agent-orchestrator-service/
├── config/
│   ├── __init__.py
│   ├── settings.py              # AgentOrchestratorSettings
│   └── constants.py             # Timeouts, rate limits
├── models/
│   ├── __init__.py
│   ├── chat.py                  # ChatRequest, ChatResponse
│   ├── session.py               # Session, SessionState
│   ├── orchestration.py         # OrchestrationPlan, ServiceCall
│   └── batch.py                 # BatchRequest, BatchResponse
├── routes/
│   ├── __init__.py
│   ├── chat.py                  # Endpoint principal de chat
│   ├── sessions.py              # Gestión de sesiones
│   ├── batch.py                 # Procesamiento en lote
│   ├── internal.py              # APIs internas
│   └── health.py
├── services/
│   ├── __init__.py
│   ├── orchestrator.py          # Orquestador principal
│   ├── session_manager.py       # Gestión de sesiones
│   ├── service_coordinator.py   # Coordinación entre servicios
│   └── rate_limiter.py          # Rate limiting
├── middleware/
│   ├── __init__.py
│   ├── auth.py                  # Autenticación
│   ├── rate_limit.py            # Rate limiting middleware
│   └── context.py               # Context propagation
├── queue/                       # Sistema de cola de trabajo
│   ├── __init__.py
│   ├── consumer.py              # Consumidor de tareas
│   ├── producer.py              # Productor de tareas
│   └── tasks/
│       ├── __init__.py
│       ├── chat_tasks.py         # Tareas de procesamiento de chat
│       └── orchestration_tasks.py # Tareas de orquestación
├── websocket/                   # Comunicación en tiempo real
│   ├── __init__.py
│   ├── connection_manager.py    # Gestión de conexiones WebSocket
│   ├── events.py                # Definición de eventos
│   └── handlers.py              # Manejadores de eventos
├── main.py
├── requirements.txt
├── Dockerfile
└── README.md
```

## Funciones Clave
1. Punto de entrada unificado para solicitudes de usuarios
2. Orquestación de flujos de trabajo entre servicios
3. Gestión de sesiones y mantenimiento de estado
4. Coordinación de respuestas en tiempo real

## Sistema de Cola de Trabajo
- **Tareas**: Procesamiento de solicitudes complejas, coordinación de flujos asíncronos
- **Implementación**: Redis Queue con sistema de prioridades y retorno de resultados
- **Procesamiento**: Manejo de solicitudes de larga duración y operaciones por lotes

## Comunicación Asíncrona y WebSockets

### Arquitectura de Comunicación Asíncrona

El Agent Orchestrator Service implementa un sistema centralizado de comunicación asíncrona para coordinar operaciones de larga duración:

```
                 [1. Solicitud HTTP inicial]
 Cliente ------> Agent Orchestrator Service --------+
    ^                                               |
    |                                               v
    |                                     [2. Solicitud de tarea]
    |                                               |
    |                                               v
    |                                       Query Service
    |                                          o
    |                                    Embedding Service
    |                                               |
    |      [4. Actualización WebSocket]             |
    +------ Agent Orchestrator <--- [3. Notificación WebSocket] 
```

### Flujo del Proceso Asíncrono

1. **Recepción de Solicitudes**:
   - Agent Orchestrator recibe solicitud HTTP del cliente
   - Valida permisos, rate limits y contexto del tenant

2. **Delegación de Trabajo**:
   - Envía solicitud HTTP al servicio apropiado (Query/Embedding Service)
   - Recibe un `job_id` inmediatamente sin esperar resultados
   - Almacena el ID de trabajo y lo asocia con la sesión del cliente

3. **Servidor WebSocket para Notificaciones**:
   - Expone un endpoint WebSocket en `ws://agent-orchestrator:8000/ws/task_updates`
   - Recibe notificaciones de finalización de tareas de los servicios
   - Estructura de mensaje recibido:

```json
{
  "event": "job_completed",
  "service": "query|embedding",
  "job_id": "uuid-string",
  "tenant_id": "tenant-id",
  "agent_id": "agent-id-opcional",
  "result": { /* resultado de la operación */ }
}
```

4. **Procesamiento de Notificaciones**:
   - Valida que el `job_id` corresponda a una tarea en curso
   - Actualiza el estado de la sesión con los resultados
   - Notifica al cliente vía WebSocket del cliente

### Implementación del Servidor WebSocket

```python
# websocket/server.py
from fastapi import WebSocket, APIRouter, Depends
from services.task_registry import TaskRegistry

router = APIRouter()
task_registry = TaskRegistry()

@router.websocket("/ws/task_updates")
async def task_update_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # Recibir notificación del servicio (Query/Embedding)
            data = await websocket.receive_json()
            
            # Validar datos básicos
            if "job_id" not in data or "event" not in data:
                continue
                
            # Procesar notificación de finalización de tarea
            if data["event"] == "job_completed":
                job_id = data["job_id"]
                result = data.get("result")
                tenant_id = data.get("tenant_id")
                
                # Procesar resultado y notificar al cliente
                await task_registry.complete_task(job_id, result, tenant_id)
    except Exception as e:
        # Manejar desconexiones y errores
        pass
```

### Integración con el Flujo de Trabajo General

- **Seguimiento de Tareas**: Todas las tareas asíncronas se registran en `TaskRegistry`
- **Timeout Handling**: Detección automática de tareas expiradas
- **Multi-tenant**: Validación de permisos en cada notificación
- **Manejo de Errores**: Proceso de recuperación para conexiones interrumpidas

## Integración con otros Servicios
El Agent Orchestrator Service coordina con todos los demás servicios:
1. Conversation Service: Para gestionar el historial de conversaciones
2. Agent Management Service: Para obtener configuraciones de agentes
3. Agent Execution Service: Para ejecutar agentes
4. Workflow Engine Service: Para flujos de trabajo complejos
5. Tool Registry Service: Para acceder a herramientas disponibles
6. Query Service: Como ÚNICO punto de contacto para procesamiento LLM y operaciones RAG
7. Embedding Service: Como ÚNICO punto de contacto para generación de embeddings

## Papel Central en la Arquitectura

El Agent Orchestrator Service actúa como el único punto de contacto para:

1. **Query Service**: Todas las solicitudes de procesamiento LLM y RAG
2. **Embedding Service**: Todas las solicitudes de embeddings (exceptuando Ingestion Service)

Esta centralización garantiza:
- Seguimiento consistente del uso de tokens
- Aplicación de políticas de rate limiting
- Consistencia en el manejo de caché
- Orquestación correcta de operaciones complejas
- Trazabilidad completa de las solicitudes