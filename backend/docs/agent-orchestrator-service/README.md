# Agent Orchestrator Service

## Descripción
Servicio central que coordina las interacciones entre el usuario y los diferentes servicios del sistema. Actúa como un punto de entrada unificado para gestionar el flujo de las solicitudes, mantener el estado de las sesiones, y orquestar la comunicación entre los múltiples microservicios de la plataforma.

## 🏗️ Ecosistema de Servicios

La arquitectura se organiza en 3 niveles jerárquicos:

### Nivel 1: Orquestación

- **Agent Orchestrator**: Punto de entrada único, gestión de sesiones y coordinación global

### Nivel 2: Servicios Funcionales

- **Conversation Service**: Historial y contexto de conversaciones
- **Workflow Engine**: Flujos de trabajo complejos multi-etapa
- **Agent Execution**: Lógica específica del agente
- **Tool Registry**: Registro y ejecución de herramientas
- **Agent Management**: Gestión del ciclo de vida de agentes

### Nivel 3: Servicios de Infraestructura

- **Query Service**: Procesamiento RAG y LLM
- **Embedding Service**: Generación de embeddings vectoriales
- **Ingestion Service**: Procesamiento de documentos

> 📌 **Este documento describe el Agent Orchestrator Service**, ubicado en el Nivel 1 como componente central de orquestación

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

## 🚦 Sistema de Colas Multi-tenant

### Mapa de Responsabilidades del Orquestador

```
+----------------------------------------------------------+
|                   AGENT ORCHESTRATOR                     |
+----------------------------------------------------------+
| RESPONSABILIDADES PRINCIPALES:                           |
|                                                          |
| 1. ◆ Punto único de entrada para ejecucion de workflows y conversaciones                |
| 2. ◆ Gestión global de sesiones y contexto               |
| 3. ◆ Orquestación de tareas entre servicios              |
| 4. ◆ Seguimiento del estado de tareas asíncronas         |
| 5. ◆ Servidor WebSocket para notificaciones              |
| 6. ◆ Aplicación de políticas de seguridad y tenancy      |
+----------------------------------------------------------+
```

### Estructura Jerárquica de Colas

```
                  +---------------------------+
                  |    COLAS DE ORQUESTADOR   |
                  +---------------------------+
                               |
         +--------------------+-----------------+
         |                    |                 |
+----------------+  +------------------+  +---------------+
| Nivel Sesión   |  | Nivel Tarea     |  | Nivel Sistema |
+----------------+  +------------------+  +---------------+
|                |  |                  |  |               |
| orchestrator:  |  | orchestrator:    |  | orchestrator: |
| session:       |  | tasks:           |  | system:       |
| {tenant_id}:   |  | {tenant_id}      |  | notifications |
| {session_id}   |  |                  |  |               |
+----------------+  +------------------+  +---------------+
```

### Características Clave

- **Segmentación por tenant**: Completo aislamiento de datos entre tenants
- **IDs únicos para trazabilidad**: Correlación de tareas distribuidas
- **Metadatos de contexto enriquecidos**: Información completa para seguimiento
- **Tracking de estado en tiempo real**: Actualización inmediata de estados

### Estructura y Tipos de Colas

1. **Colas de Nivel Sesión**:
   - `orchestrator:session:{tenant_id}:{session_id}`
   - Propósito: Seguimiento de sesiones activas y su estado
   - Datos: Estado de la conversación, historial, contexto activo

2. **Colas de Nivel Tarea**:
   - `orchestrator:tasks:{tenant_id}`
   - Propósito: Tracking global de todas las tareas del tenant
   - Estructura: Registro central de tareas distribuidas en otros servicios

3. **Colas de Sistema**:
   - `orchestrator:system:notifications`
   - Propósito: Notificaciones internas del sistema

### Formato Estandarizado de Mensajes en Cola

```json
{
  "task_id": "uuid-v4",
  "tenant_id": "tenant-identifier",
  "session_id": "session-identifier",
  "created_at": "ISO-timestamp",
  "status": "pending|processing|completed|failed",
  "type": "query|embedding|workflow|agent_execution",
  "priority": 0-9,
  "delegated_services": [
    {
      "service": "service-name",
      "task_id": "service-specific-task-id"
    }
  ],
  "metadata": {
    "source": "api|scheduled|system",
    "user_id": "optional-user-id",
    "timeout_ms": 30000
  },
  "payload": {
    // Datos específicos de la tarea
  }
}
```

### Flujo de Trabajo Asíncrono Detallado

```
+--------+          +------------------+          +----------------+
|        |  HTTP    |                  | Encolar   |                |
|Cliente | -------> |Agent Orchestrator| -------> | Redis Queue    |
|        |          |                  |          |                |
+--------+          +------------------+          +----------------+
    ^                       |  ^                         |
    |                       |  |                         |
    |     WebSocket         |  |                         |
    +-----Notificación------+  |                         |
                               |                         |
                               |      Workers            |
                               | <--------------------   |
                               |                         |
                             +-v---------+              |
                             |           |              |
                             | Servicios | ------------>+
                             |           | Notificación WebSocket
                             +-----------+
```

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

## Flujos de Trabajo Completos

### Flujo de Conversación Normal

```
1. Cliente → Orchestrator: Nueva consulta
2. Orchestrator → Conversation Service: Almacena mensaje y obtiene contexto
3. Orchestrator → Agent Execution: Procesa consulta con contexto
4. Agent Execution → Query Service: Realiza consulta RAG
5. Query Service → Agent Execution: Devuelve resultado (WebSocket)
6. Agent Execution → Orchestrator: Devuelve respuesta (WebSocket)
7. Orchestrator → Conversation Service: Almacena respuesta
8. Orchestrator → Cliente: Entrega respuesta final
```

### Flujo de Herramientas y Workflow

```
1. Cliente → Orchestrator: Solicitud que requiere herramientas
2. Orchestrator → Workflow Engine: Identifica workflow necesario
3. Workflow Engine → Agent Execution: Delega ejecución de etapas
4. Agent Execution → Tool Registry: Solicita ejecución de herramientas
5. Tool Registry → Agent Execution: Devuelve resultado de herramientas
6. Agent Execution → Query Service: Realiza consulta LLM con resultados
7. [Continúa como flujo normal]
```

### Flujo de Ingestión de Documentos

```
1. Cliente → Orchestrator → Workflow Engine: Inicia ingestión
2. Workflow Engine → Ingestion Service: Procesa documento
3. Ingestion Service → Embedding Service: Solicita embeddings para chunks
4. Embedding Service → Ingestion Service: Devuelve embeddings (WebSocket)
5. Ingestion Service → Workflow Engine: Notifica completado (WebSocket)
6. Workflow Engine → Orchestrator: Notifica completado (WebSocket)
7. Orchestrator → Cliente: Notifica completado
```

## 🔄 Flujos de Trabajo Principales

### 1. Consulta Normal
```
Cliente → Orchestrator → Conversation → Agent Execution → Query → Respuesta
```

### 2. Con Herramientas
```
Cliente → Orchestrator → Workflow Engine → Agent Execution → Tool Registry → Query → Respuesta
```

### 3. Ingestión de Documentos
```
Cliente → Orchestrator → Ingestion Service → Embedding Service → Notificación de completado
```

## Registro Global de Tareas

El Agent Orchestrator Service implementa un `GlobalTaskRegistry` que mantiene el estado de todas las tareas distribuidas:

```python
class GlobalTaskRegistry:
    def __init__(self, redis_conn):
        self.redis_conn = redis_conn
        self.namespace = "orchestrator:tasks"
    
    async def register_task(self, global_task_id, session_id, tenant_id, 
                          service=None, service_task_id=None):
        """Registra una tarea global en el sistema"""
        key = f"{self.namespace}:{tenant_id}:{global_task_id}"
        
        task_data = {
            "global_task_id": global_task_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "status": "processing",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "delegated_services": []
        }
        
        if service and service_task_id:
            task_data["delegated_services"].append({
                "service": service,
                "task_id": service_task_id
            })
            
        await self.redis_conn.hmset(key, task_data)
        await self.redis_conn.expire(key, 86400)  # 24 horas
        
        return task_data
        
    async def update_task(self, global_task_id, tenant_id, 
                         status=None, result=None):
        """Actualiza el estado de una tarea global"""
        key = f"{self.namespace}:{tenant_id}:{global_task_id}"
        
        if not await self.redis_conn.exists(key):
            return None
            
        updates = {"updated_at": datetime.utcnow().isoformat()}
        
        if status:
            updates["status"] = status
            
        if result:
            updates["result"] = json.dumps(result)
            
        await self.redis_conn.hmset(key, updates)
        
        # Si completado o fallido, notificar al cliente
        if status in ["completed", "failed"]:
            await self._notify_completion(global_task_id, tenant_id, status)
            
        return await self.get_task(global_task_id, tenant_id)
        
    async def get_task(self, global_task_id, tenant_id):
        """Obtiene los detalles de una tarea"""
        key = f"{self.namespace}:{tenant_id}:{global_task_id}"
        
        if not await self.redis_conn.exists(key):
            return None
            
        return await self.redis_conn.hgetall(key)
```

## Patrones Estandarizados de Integración

### Caché Centralizada

El Agent Orchestrator implementa y coordina un sistema centralizado de caché:

```python
from common.cache.manager import CacheManager
from common.cache.helpers import get_with_cache_aside

# Ejemplo de uso en el orquestador
async def get_embeddings_with_cache(texts, tenant_id, collection_id=None):
    cache_key = f"embeddings:{tenant_id}:{hash_texts(texts)}"
    
    # Usar patrón Cache-Aside
    embeddings, metrics = await get_with_cache_aside(
        data_type="embedding",
        resource_id=cache_key,
        tenant_id=tenant_id,
        fetch_from_db_func=None,  # No DB lookup
        generate_func=lambda: embedding_service.generate_embeddings(texts, tenant_id),
        collection_id=collection_id,
        ttl_seconds=86400  # 24 horas
    )
    
    # Registrar uso
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=metrics.get("tokens", 0),
        model=metrics.get("model"),
        token_type="embedding",
        operation="generate",
        metadata={"service": "orchestrator"}
    )
    
    return embeddings
```

## 🔌 Sistema de Notificaciones

### WebSockets Centralizados

- Hub central en Agent Orchestrator
- Conexiones bidireccionales con todos los servicios
- Formato estandarizado de mensajes
- Reconexión automática con backoff exponencial

### Eventos Principales

- `task_completed`: Tarea finalizada exitosamente
- `task_status_update`: Actualización de progreso intermedio
- `task_failed`: Error en el procesamiento de la tarea

### Formato Estandarizado de Mensajes WebSocket

Los mensajes WebSocket siguen un formato estandarizado para asegurar consistencia:

```json
{
  "event": "task_completed|task_status_update|task_failed",
  "service": "query|embedding|agent_execution|workflow|...",
  "task_id": "task-uuid",
  "global_task_id": "global-task-uuid",
  "tenant_id": "tenant-id",
  "timestamp": "iso-timestamp",
  "data": {
    // Datos específicos del evento
  },
  "metadata": {
    // Metadatos adicionales específicos del servicio
  }
}
```

### Implementación del Cliente WebSocket

```python
# websocket/notifier.py (implementación para servicios)
import asyncio
import websockets
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class TaskNotifier:
    def __init__(self, service_name, orchestrator_url):
        self.service_name = service_name
        self.orchestrator_url = orchestrator_url
        self.service_token = os.getenv("SERVICE_TOKEN")
        self.reconnect_delay = 1.0  # segundos, con backoff
        self.websocket = None
        
    async def connect(self):
        """Establece conexión con orquestador con reconexión automática"""
        while True:
            try:
                logger.info(f"Conectando a {self.orchestrator_url}")
                async with websockets.connect(self.orchestrator_url) as ws:
                    # Autenticarse como servicio
                    await ws.send(json.dumps({
                        "service_token": self.service_token,
                        "service_name": self.service_name
                    }))
                    
                    # Esperar confirmación
                    auth_response = await ws.recv()
                    if json.loads(auth_response).get("status") != "authenticated":
                        logger.error("Fallo en la autenticación WebSocket")
                        raise Exception("Authentication failed")
                    
                    logger.info(f"Conexión WebSocket establecida para {self.service_name}")
                    # Conexión establecida
                    self.reconnect_delay = 1.0  # reset backoff
                    self.websocket = ws
                    
                    # Mantener conexión abierta
                    while True:
                        # Keep-alive o esperar cierre
                        await asyncio.sleep(30)
                        await ws.ping()
                        
            except Exception as e:
                logger.warning(f"Error en conexión WebSocket: {e}. Reintentando en {self.reconnect_delay}s")
                # Implementar backoff exponencial
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(30.0, self.reconnect_delay * 1.5)

    async def notify_task_status(self, task_id, tenant_id, status, details=None, global_task_id=None):
        """Envía notificación de actualización de estado"""
        try:
            if not self.websocket:
                logger.warning("WebSocket no conectado. No se puede enviar notificación.")
                return
                
            notification = {
                "event": "task_status_update",
                "service": self.service_name,
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "status": status,
                    "details": details or {}
                }
            }
            
            await self.websocket.send(json.dumps(notification))
            logger.debug(f"Notificación enviada: {notification['event']} para tarea {task_id}")
            
        except Exception as e:
            logger.error(f"Error al enviar notificación de estado: {e}")
            # La reconexión se maneja automáticamente

    async def notify_task_completion(self, task_id, tenant_id, result, global_task_id=None):
        """Notifica la finalización exitosa de una tarea"""
        try:
            if not self.websocket:
                logger.warning("WebSocket no conectado. No se puede enviar notificación.")
                return
                
            notification = {
                "event": "task_completed",
                "service": self.service_name,
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": result
            }
            
            await self.websocket.send(json.dumps(notification))
            logger.info(f"Tarea {task_id} completada y notificada")
            
        except Exception as e:
            logger.error(f"Error al notificar finalización de tarea: {e}")
            
    async def notify_task_failure(self, task_id, tenant_id, error, global_task_id=None):
        """Notifica el fallo de una tarea"""
        try:
            if not self.websocket:
                logger.warning("WebSocket no conectado. No se puede enviar notificación.")
                return
                
            notification = {
                "event": "task_failed",
                "service": self.service_name,
                "task_id": task_id,
                "global_task_id": global_task_id,
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "error": str(error),
                    "error_type": error.__class__.__name__ if hasattr(error, "__class__") else "Unknown"
                }
            }
            
            await self.websocket.send(json.dumps(notification))
            logger.warning(f"Tarea {task_id} fallida y notificada: {error}")
            
        except Exception as e:
            logger.error(f"Error al notificar fallo de tarea: {e}")
```