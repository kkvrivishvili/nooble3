# Fase 7: Sistema de Colas de Trabajo con Celery y RabbitMQ

## Visión General

Esta fase implementa un sistema de colas de trabajo asíncrono utilizando Celery y RabbitMQ para optimizar las comunicaciones entre el frontend y backend, así como entre los servicios más demandados. Este enfoque reemplaza las conexiones directas HTTP por un sistema de trabajos encolados con WebSockets para notificaciones en tiempo real.

## 7.1 Arquitectura del Sistema de Colas

### 7.1.1 Componentes Principales

```
                                  +----------------+
                                  |                |
                                  |  RabbitMQ      |
                                  |  Message Broker|
                                  |                |
                                  +--------+-------+
                                           |
                                           |
                +-------------+   +--------+-------+   +--------------+
                |             |   |                |   |              |
                | Frontend    |   | Celery Workers |   | WebSocket    |
                | Web App     +-->|                +-->| Server       |
                |             |   |                |   |              |
                +-------------+   +----------------+   +--------------+
                      |                                       |
                      +---------------------------------------+
                               WebSocket Connection
```

### 7.1.2 Flujo de Operación

1. Cliente realiza petición HTTP al backend
2. Backend crea y registra una tarea en Celery
3. Backend devuelve un job_id al cliente
4. Cliente establece una conexión WebSocket usando el job_id
5. Celery procesa la tarea asíncronamente
6. Al completarse, se notifica a través del WebSocket al cliente

## 7.2 Implementación del Servicio de RabbitMQ

### 7.2.1 Configuración de Docker-Compose

```yaml
version: '3.8'

services:
  rabbitmq:
    image: rabbitmq:3.9-management
    ports:
      - "5672:5672"   # AMQP protocol
      - "15672:15672" # Management interface
    environment:
      - RABBITMQ_DEFAULT_USER=nooble
      - RABBITMQ_DEFAULT_PASS=nooble_password
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - nooble_network
    healthcheck:
      test: ["CMD", "rabbitmqctl", "status"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  rabbitmq_data:

networks:
  nooble_network:
    external: true
```

### 7.2.2 Módulo Central de Configuración

```python
# common/queue/settings.py
from common.config.settings import get_settings

def get_celery_config():
    """
    Obtiene configuración centralizada para Celery.
    """
    settings = get_settings()
    
    return {
        "broker_url": settings.RABBITMQ_URI,
        "result_backend": settings.REDIS_URI,
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "enable_utc": True,
        "worker_concurrency": settings.CELERY_CONCURRENCY,
        "task_time_limit": 3600,  # 1 hora
        "task_soft_time_limit": 3500,
        "worker_prefetch_multiplier": 1,
        "task_acks_late": True,
        "task_reject_on_worker_lost": True,
        "task_routes": {
            "agent_tasks.*": {"queue": "agent_queue"},
            "embedding_tasks.*": {"queue": "embedding_queue"},
            "query_tasks.*": {"queue": "query_queue"},
            "ingestion_tasks.*": {"queue": "ingestion_queue"}
        }
    }
```

## 7.3 Celery Task Manager

### 7.3.1 Clase Centralizada para Tareas

```python
# common/queue/celery_app.py
from celery import Celery
from common.queue.settings import get_celery_config
from common.context import current_tenant_id, Context
import functools
import uuid

# Crear instancia de Celery
celery_app = Celery("nooble")
celery_app.config_from_object(get_celery_config())

def create_context_task(queue_name):
    """
    Decorador para crear tareas Celery que preservan el contexto multitenancy.
    
    Maneja la propagación completa del contexto entre servicios y asegura el
    tracking de uso, manejo de errores y caché coherente con el resto del sistema.
    
    Args:
        queue_name: Nombre de la cola en RabbitMQ
        
    Returns:
        Decorador para funciones
    """
    def decorator(func):
        @celery_app.task(name=f"{queue_name}.{func.__name__}", bind=True)
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Restaurar contexto de los kwargs
            ctx_data = kwargs.pop("_context", {})
            ctx = Context()
            
            # Reconstruir contexto completo
            if "tenant_id" in ctx_data:
                ctx.set_tenant_id(ctx_data["tenant_id"])
            if "agent_id" in ctx_data:
                ctx.set_agent_id(ctx_data["agent_id"])
            if "conversation_id" in ctx_data:
                ctx.set_conversation_id(ctx_data["conversation_id"])
            if "collection_id" in ctx_data:
                ctx.set_collection_id(ctx_data["collection_id"])
            if "user_id" in ctx_data:
                ctx.set_user_id(ctx_data["user_id"])
            if "request_id" in ctx_data:
                ctx.set_request_id(ctx_data["request_id"])
                
            # Configurar logger con detalles de contexto
            request_id = ctx.get_request_id() or str(uuid.uuid4())
            structlog.contextvars.bind_contextvars(
                tenant_id=ctx.get_tenant_id(),
                request_id=request_id
            )
            
            # Añadir contexto a kwargs
            kwargs["ctx"] = ctx
            
            try:
                # Ejecutar tarea con tracking
                start_time = time.time()
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                logger.info(
                    f"Tarea {func.__name__} completada",
                    extra={
                        "duration_ms": duration_ms,
                        "task": func.__name__,
                        "queue": queue_name
                    }
                )
                
                return result
            except Exception as e:
                # Manejo consistente de errores
                logger.error(
                    f"Error en tarea {func.__name__}",
                    extra={
                        "error": str(e),
                        "task": func.__name__,
                        "queue": queue_name,
                        "tenant_id": ctx.get_tenant_id()
                    }
                )
                raise
        
        # Añadir método para facilitar la llamada con contexto
        @functools.wraps(func)
        def apply_async_with_context(ctx=None, *args, **kwargs):
            """
            Ejecuta la tarea con propagación automática del contexto.
            
            Args:
                ctx: Objeto de contexto (opcional)
                *args: Argumentos posicionales para la tarea
                **kwargs: Argumentos nombrados para la tarea
                
            Returns:
                Resultado de AsyncResult de Celery
            """
            # Serializar contexto completo
            ctx_data = {}
            if ctx:
                if tenant_id := ctx.get_tenant_id():
                    ctx_data["tenant_id"] = tenant_id
                if agent_id := ctx.get_agent_id():
                    ctx_data["agent_id"] = agent_id
                if conversation_id := ctx.get_conversation_id():
                    ctx_data["conversation_id"] = conversation_id
                if collection_id := ctx.get_collection_id():
                    ctx_data["collection_id"] = collection_id
                if user_id := ctx.get_user_id():
                    ctx_data["user_id"] = user_id
                if request_id := ctx.get_request_id():
                    ctx_data["request_id"] = request_id
            else:
                # Capturar contexto global si no se proporciona
                tenant_id = structlog.contextvars.get_contextvars().get("tenant_id")
                request_id = structlog.contextvars.get_contextvars().get("request_id")
                if tenant_id:
                    ctx_data["tenant_id"] = tenant_id
                if request_id:
                    ctx_data["request_id"] = request_id
            
            # Añadir datos de contexto a kwargs
            task_kwargs = kwargs.copy()
            task_kwargs["_context"] = ctx_data
            
            # Generar task_id que incluya información de tenant para facilitar el debug
            tenant_prefix = ctx_data.get("tenant_id", "")[:8]
            task_id = f"{tenant_prefix}-{str(uuid.uuid4())}"
            
            logger.debug(
                f"Encolando tarea {func.__name__}",
                extra={
                    "queue": queue_name,
                    "task": func.__name__,
                    "task_id": task_id,
                    "tenant_id": ctx_data.get("tenant_id")
                }
            )
            
            # Llamar a apply_async original con mejoras
            return wrapper.apply_async(
                args=args, 
                kwargs=task_kwargs, 
                task_id=task_id,
                # Permitir establecer prioridades por tenant
                priority=kwargs.pop("priority", None)
            )
        
        wrapper.with_context = apply_async_with_context
        return wrapper
    
    return decorator
```

### 7.3.2 WorkQueue Service

```python
# common/queue/work_queue.py
from common.cache import CacheManager
from common.tracking.metrics import track_performance_metric
from datetime import datetime
import asyncio
import logging
import json
import hashlib

logger = logging.getLogger(__name__)

class WorkQueueService:
    """
    Gestiona la integración entre Celery, caché y WebSockets.
    """
    
    def __init__(self, websocket_manager):
        """
        Inicializa el servicio de colas de trabajo.
        
        Args:
            websocket_manager: Gestor de WebSockets
        """
        self.websocket_manager = websocket_manager
    
    async def register_job(self, tenant_id, job_type, params, task, ctx=None, ttl=None):
        """
        Registra un nuevo trabajo en la cola de trabajos con soporte de caché.
        
        Este método implementa el patrón Cache-Aside estándar usado en el Embedding Service (Fase 3)
        para garantizar la coherencia en todo el sistema. Verifica primero si hay resultados
        en caché para la combinación de tenant, tipo de trabajo y parámetros antes de registrar
        un nuevo trabajo.
        
        Args:
            tenant_id: ID del tenant
            job_type: Tipo de trabajo (ej. "agent_execution", "embedding_generation")
            params: Parámetros para la ejecución, diccionario serializable
            task: Nombre de la tarea de Celery a ejecutar
            ctx: Contexto existente (opcional), si no se proporciona se crea uno nuevo
            ttl: Tiempo de vida en segundos para la caché (opcional)
            
        Returns:
            Dict con job_id y estado, y resultado si estaba en caché
        """
        # Usar TTL por defecto si no se proporciona
        ttl = ttl or 3600  # 1 hora por defecto
        
        # Generar clave de caché usando el patrón unificado
        cache_key = self._generate_cache_key(tenant_id, job_type, params)
        
        # Verificar si existe en caché usando el patrón Cache-Aside (Fase 3)
        # Esto es equivalente a la función get_with_cache_aside pero para resultados de trabajos
        cached_result = await CacheManager.get(
            data_type="job_result",
            resource_id=cache_key,
            tenant_id=tenant_id
        )
        
        if cached_result and "result" in cached_result:
            job_id = cached_result.get("job_id")
            logger.info(
                f"Cache hit para job_type={job_type}", 
                extra={
                    "tenant_id": tenant_id,
                    "cache_key": cache_key,
                    "from_cache": True
                }
            )
            
            # Registrar métricas de caché de manera consistente con Fase 3
            await track_performance_metric(
                metric_type="work_queue_cache_hit",
                value=1,
                tenant_id=tenant_id,
                metadata={
                    "job_type": job_type,
                    "cache_ttl": ttl
                }
            )
            
            return {
                "job_id": job_id,
                "status": "completed",
                "from_cache": True,
                "result": cached_result.get("result")
            }
        
        # Crear/reutilizar contexto para la tarea
        if not ctx:
            from common.context import Context
            ctx = Context()
            ctx.set_tenant_id(tenant_id)
        
        # Iniciar tarea de Celery
        task_result = task.with_context(ctx=ctx, **params)
        job_id = task_result.task_id
        
        # Guardar metadata del trabajo (se estandarizará según Fase 8)
        job_metadata = {
            "tenant_id": tenant_id,
            "job_type": job_type,
            "params": params,  # En Fase 8, estos parámetros tendrán metadatos estandarizados
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "job_id": job_id,
            "source_framework": params.get("source_framework", "unknown")  # Tracking del framework de origen
        }
        
        # Guardar en caché
        await CacheManager.set(
            data_type="job_metadata",
            resource_id=job_id,
            value=job_metadata,
            tenant_id=tenant_id,
            ttl=3600
        )
        
        # Registrar en métricas
        await track_performance_metric(
            metric_type="work_queue_job_created",
            value=1,
            tenant_id=tenant_id,
            metadata={"job_type": job_type}
        )
        
        return {
            "job_id": job_id,
            "status": "pending"
        }
    
    async def update_job_status(self, job_id, status, result=None, error=None):
        """
        Actualiza el estado de un trabajo y notifica vía WebSocket.
        
        Args:
            job_id: ID del trabajo
            status: Nuevo estado
            result: Resultado opcional
            error: Error opcional
        """
        # Obtener metadata del trabajo
        job_metadata = await CacheManager.get(
            data_type="job_metadata",
            resource_id=job_id
        )
        
        if not job_metadata:
            logger.error(f"No se encontró metadata para job_id={job_id}")
            return False
        
        tenant_id = job_metadata.get("tenant_id")
        job_type = job_metadata.get("job_type")
        
        # Actualizar estado
        job_metadata["status"] = status
        job_metadata["updated_at"] = datetime.now().isoformat()
        
        if result:
            job_metadata["result"] = result
        
        if error:
            job_metadata["error"] = error
        
        # Guardar en caché
        await CacheManager.set(
            data_type="job_metadata",
            resource_id=job_id,
            value=job_metadata,
            tenant_id=tenant_id,
            ttl=3600
        )
        
        # Si es completado, guardar en caché por job_type y params
        if status == "completed" and result:
            cache_key = self._generate_cache_key(
                tenant_id, 
                job_type, 
                job_metadata.get("params", {})
            )
            
            # Guardar resultado en caché
            await CacheManager.set(
                data_type="job_result",
                resource_id=cache_key,
                value={
                    "job_id": job_id,
                    "result": result,
                    "created_at": datetime.now().isoformat()
                },
                tenant_id=tenant_id,
                ttl=3600
            )
        
        # Notificar vía WebSocket
        await self._notify_status_update(job_id, status, result, error)
        
        # Registrar en métricas
        await track_performance_metric(
            metric_type=f"work_queue_job_{status}",
            value=1,
            tenant_id=tenant_id,
            metadata={"job_type": job_type}
        )
        
        return True
    
    async def _notify_status_update(self, job_id, status, result=None, error=None):
        """
        Notifica actualización de estado vía WebSocket.
        
        Args:
            job_id: ID del trabajo
            status: Estado actualizado
            result: Resultado opcional
            error: Error opcional
        """
        message = {
            "type": "status_update",
            "job_id": job_id,
            "status": status
        }
        
        if status == "completed" and result:
            message["type"] = "job_completed"
            message["result"] = result
        
        if status == "failed" and error:
            message["type"] = "job_error"
            message["error"] = error
        
        await self.websocket_manager.send_to_job_subscribers(job_id, message)
    
    def _generate_cache_key(self, tenant_id, job_type, params):
        """
        Genera una clave de caché consistente para resultados de trabajos.
        
        Implementa la misma estrategia de caché usada en el Embedding Service (Fase 3)
        para garantizar la coherencia en todo el sistema.
        
        Args:
            tenant_id: ID del tenant
            job_type: Tipo de trabajo (por ejemplo, "agent_execution" o "embedding_generation")
            params: Parámetros del trabajo, debe ser un diccionario serializable
            
        Returns:
            Clave de caché única compatible con el patrón Cache-Aside estándar
        """
        # Normalizar y ordenar parámetros para garantizar consistencia
        # Usamos el mismo enfoque que en Fase 3 (Embedding Service)
        if not isinstance(params, dict):
            params = {"value": str(params)}
            
        # Serialización consistente con common.cache.serialize_for_cache
        try:
            # Ordenar claves para tener hash consistente independientemente del orden
            sorted_params = json.dumps(params, sort_keys=True, default=str)
        except TypeError:
            # Fallback para objetos no serializables
            sorted_params = str(params)
            
        # Generar un hash consistente
        params_hash = hashlib.md5(sorted_params.encode()).hexdigest()
        
        # Formato consistente con el resto del sistema
        return f"{tenant_id}:{job_type}:{params_hash}"
```

## 7.4 WebSocket Manager

### 7.4.1 Implementación del Gestor de WebSockets

```python
# common/websocket/manager.py
import logging
import asyncio
from typing import Dict, Set, Any, Optional
import json

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Gestiona conexiones WebSocket y distribución de mensajes.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WebSocketManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if self.initialized:
            return
            
        self.connections = {}
        self.job_subscribers = {}
        self.initialized = True
        
        logger.info("WebSocket Manager inicializado")
    
    async def register_connection(self, websocket, client_id, tenant_id=None):
        """
        Registra una nueva conexión WebSocket.
        
        Args:
            websocket: Conexión WebSocket
            client_id: ID único del cliente
            tenant_id: ID del tenant
        """
        self.connections[client_id] = {
            "websocket": websocket,
            "tenant_id": tenant_id,
            "created_at": asyncio.get_event_loop().time()
        }
        
        logger.info(f"Conexión WebSocket registrada: client_id={client_id}, tenant_id={tenant_id}")
    
    async def unregister_connection(self, client_id):
        """
        Elimina una conexión WebSocket.
        
        Args:
            client_id: ID del cliente
        """
        if client_id in self.connections:
            del self.connections[client_id]
        
        # Limpiar suscripciones
        for job_id, subscribers in list(self.job_subscribers.items()):
            if client_id in subscribers:
                subscribers.remove(client_id)
                
                # Si no quedan suscriptores, eliminar entrada
                if not subscribers:
                    del self.job_subscribers[job_id]
        
        logger.info(f"Conexión WebSocket eliminada: client_id={client_id}")
    
    async def subscribe_to_job(self, client_id, job_id):
        """
        Suscribe un cliente a actualizaciones de un trabajo específico.
        
        Args:
            client_id: ID del cliente
            job_id: ID del trabajo
        """
        if job_id not in self.job_subscribers:
            self.job_subscribers[job_id] = set()
        
        self.job_subscribers[job_id].add(client_id)
        
        logger.debug(f"Cliente {client_id} suscrito a trabajo {job_id}")
    
    async def send_to_job_subscribers(self, job_id, data):
        """
        Envía datos a todos los suscriptores de un trabajo.
        
        Args:
            job_id: ID del trabajo
            data: Datos a enviar
        """
        if job_id not in self.job_subscribers:
            logger.debug(f"No hay suscriptores para el trabajo {job_id}")
            return
        
        subscribers = list(self.job_subscribers[job_id])
        send_count = 0
        
        for client_id in subscribers:
            if client_id in self.connections:
                try:
                    websocket = self.connections[client_id]["websocket"]
                    await websocket.send_json(data)
                    send_count += 1
                except Exception as e:
                    logger.error(f"Error enviando a {client_id}: {str(e)}")
                    await self.unregister_connection(client_id)
        
        logger.debug(f"Mensaje enviado a {send_count}/{len(subscribers)} suscriptores del trabajo {job_id}")
        
        # Si los datos indican finalización, limpiar suscripciones
        if data.get("type") in ["job_completed", "job_error"]:
            if job_id in self.job_subscribers:
                del self.job_subscribers[job_id]

## 7.5 Implementación en Agent Service

### 7.5.1 Tareas de Celery para Agentes

```python
# agent-service/tasks/agent_tasks.py
from common.queue.celery_app import create_context_task, celery_app
from common.queue.work_queue import WorkQueueService
from common.websocket.manager import WebSocketManager
import asyncio

# Crear instancia del servicio de colas
websocket_manager = WebSocketManager()
work_queue = WorkQueueService(websocket_manager)

@create_context_task("agent_tasks")
def execute_agent(agent_id, input_text, collection_id=None, use_auto_federation=False, ctx=None):
    """
    Tarea de ejecución de agente.
    
    Args:
        agent_id: ID del agente
        input_text: Texto de entrada
        collection_id: ID de colección opcional
        use_auto_federation: Si usar federación automática
        ctx: Contexto
        
    Returns:
        Resultado de la ejecución del agente
    """
    from agent_service.service import agent_service
    
    # Configurar bucle de eventos asyncio para ejecutar código asíncrono
    loop = asyncio.get_event_loop()
    
    try:
        # Actualizar estado a "processing"
        job_id = asyncio.run_coroutine_threadsafe(
            work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="processing"
            ),
            loop
        ).result()
        
        # Ejecutar agente (código asíncrono)
        response = asyncio.run_coroutine_threadsafe(
            agent_service.execute_agent(
                input_text=input_text,
                collection_id=collection_id,
                use_auto_federation=use_auto_federation,
                ctx=ctx
            ),
            loop
        ).result()
        
        # Extraer resultado
        result = {
            "answer": response.answer,
            "metadata": response.metadata
        }
        
        # Actualizar estado a "completed"
        asyncio.run_coroutine_threadsafe(
            work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="completed",
                result=result
            ),
            loop
        ).result()
        
        return result
        
    except Exception as e:
        # Actualizar estado a "failed"
        asyncio.run_coroutine_threadsafe(
            work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="failed",
                error=str(e)
            ),
            loop
        ).result()
        
        raise

### 7.5.2 Endpoint para Registro de Trabajos

```python
# agent-service/routes/websocket.py
from fastapi import APIRouter, WebSocket, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from common.context import Context, with_context
from common.queue.work_queue import WorkQueueService
from common.websocket.manager import WebSocketManager
from common.errors.handlers import handle_errors
from agent_service.tasks.agent_tasks import execute_agent
import uuid

router = APIRouter()
websocket_manager = WebSocketManager()
work_queue = WorkQueueService(websocket_manager)

@router.post("/jobs/agent/{agent_id}/execute", response_model=None)
@with_context(tenant=True, agent=True, conversation=True)
@handle_errors(error_type="api", log_traceback=True)
async def create_agent_job(
    agent_id: str,
    request: AgentExecuteRequest = Body(...),
    ctx: Context = None
):
    """
    Endpoint para crear un trabajo de ejecución de agente.
    
    Args:
        agent_id: ID del agente
        request: Parámetros de la petición
        ctx: Contexto
        
    Returns:
        ID de trabajo y estado
    """
    if not ctx:
        raise ValueError("Contexto requerido para create_agent_job")
    
    tenant_id = ctx.get_tenant_id()
    
    # Parámetros para la tarea
    params = {
        "agent_id": agent_id,
        "input_text": request.input,
        "collection_id": request.collection_id,
        "use_auto_federation": request.use_auto_federation
    }
    
    # Registrar trabajo
    result = await work_queue.register_job(
        tenant_id=tenant_id,
        job_type="agent_execution",
        params=params,
        task=execute_agent
    )
    
    # Comprobar si se ha obtenido de caché
    if result.get("status") == "cached":
        return {
            "success": True,
            "message": "Resultado obtenido de caché",
            "data": {
                "job_id": result["job_id"],
                "status": "completed",
                "result": result["result"],
                "from_cache": True,
                "websocket_url": f"/ws/jobs/{result['job_id']}"
            }
        }
    
    # Respuesta normal
    return {
        "success": True,
        "message": "Trabajo registrado correctamente",
        "data": {
            "job_id": result["job_id"],
            "status": result["status"],
            "websocket_url": f"/ws/jobs/{result['job_id']}"
        }
    }

@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_endpoint(
    websocket: WebSocket,
    job_id: str
):
    """
    Endpoint WebSocket para suscribirse a actualizaciones de un trabajo.
    
    Args:
        websocket: Conexión WebSocket
        job_id: ID del trabajo
    """
    await websocket.accept()
    
    # Generar ID único para esta conexión
    client_id = str(uuid.uuid4())
    
    try:
        # Registrar conexión
        await websocket_manager.register_connection(websocket, client_id)
        
        # Suscribir a actualizaciones del trabajo
        await websocket_manager.subscribe_to_job(client_id, job_id)
        
        # Mantener conexión abierta y esperar mensajes
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Procesar comandos del cliente (cancel, etc)
            if message.get("type") == "cancel_job":
                # Implementar cancelación
                pass
    except Exception as e:
        logger.error(f"Error en WebSocket para job {job_id}: {str(e)}")
    finally:
        # Limpiar conexión
        await websocket_manager.unregister_connection(client_id)

## 7.6 Integración con Frontend

### 7.6.1 Cliente JavaScript

```javascript
class JobClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.websockets = {};
    this.callbacks = {};
  }

  async executeAgent(agentId, input, options = {}) {
    const jobType = "agent_execution";
    
    // Registrar callbacks
    this.callbacks[jobType] = options.callbacks || {};
    
    // Enviar solicitud HTTP para registrar el trabajo
    const response = await fetch(`${this.baseUrl}/jobs/agent/${agentId}/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.getAuthToken()}`
      },
      body: JSON.stringify({
        input: input,
        collection_id: options.collectionId,
        use_auto_federation: options.useAutoFederation || false
      })
    });
    
    const data = await response.json();
    
    if (!data.success) {
      if (this.callbacks[jobType].onError) {
        this.callbacks[jobType].onError(data.message);
      }
      return null;
    }
    
    const jobData = data.data;
    const jobId = jobData.job_id;
    
    // Si el resultado ya está en caché, manejarlo inmediatamente
    if (jobData.from_cache && jobData.result) {
      if (this.callbacks[jobType].onComplete) {
        this.callbacks[jobType].onComplete(jobId, jobData.result);
      }
      return {
        jobId,
        fromCache: true,
        result: jobData.result
      };
    }
    
    // Conectar WebSocket para recibir actualizaciones
    this.connectToJobWebSocket(jobId, jobType);
    
    return {
      jobId,
      fromCache: false
    };
  }
  
  connectToJobWebSocket(jobId, jobType) {
    // Crear conexión WebSocket
    const wsUrl = `${this.baseUrl.replace('http', 'ws')}/ws/jobs/${jobId}`;
    const socket = new WebSocket(wsUrl);
    
    // Guardar referencia
    this.websockets[jobId] = socket;
    
    const callbacks = this.callbacks[jobType] || {};
    
    // Configurar handlers
    socket.onopen = () => {
      console.log(`WebSocket conectado para job ${jobId}`);
      
      if (callbacks.onConnected) {
        callbacks.onConnected(jobId);
      }
    };
    
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      switch (message.type) {
        case 'status_update':
          if (callbacks.onStatusUpdate) {
            callbacks.onStatusUpdate(jobId, message.status);
          }
          break;
          
        case 'job_completed':
          if (callbacks.onComplete) {
            callbacks.onComplete(jobId, message.result);
          }
          
          // Cerrar WebSocket después de completado
          this.closeJobWebSocket(jobId);
          break;
          
        case 'job_error':
          if (callbacks.onError) {
            callbacks.onError(jobId, message.error);
          }
          
          // Cerrar WebSocket después de error
          this.closeJobWebSocket(jobId);
          break;
      }
    };
    
    socket.onerror = (error) => {
      console.error(`Error en WebSocket para job ${jobId}:`, error);
      
      if (callbacks.onError) {
        callbacks.onError(jobId, 'Error de conexión WebSocket');
      }
    };
    
    socket.onclose = () => {
      console.log(`WebSocket cerrado para job ${jobId}`);
      
      // Limpiar referencias
      delete this.websockets[jobId];
    };
  }
  
  closeJobWebSocket(jobId) {
    const socket = this.websockets[jobId];
    if (socket) {
      socket.close();
      delete this.websockets[jobId];
    }
  }
  
  cancelJob(jobId) {
    // Enviar comando de cancelación por WebSocket
    const socket = this.websockets[jobId];
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'cancel_job',
        job_id: jobId
      }));
    }
  }
  
  getAuthToken() {
    return localStorage.getItem('authToken');
  }
}

## 7.7 Integración con Otros Servicios

### 7.7.1 Embedding Service

Integrar tareas de Celery para generación de embeddings, permitiendo procesamiento asíncrono optimizado con caché.

### 7.7.2 Query Service

Implementar tareas de Celery para consultas complejas, reduciendo tiempos de espera en el frontend y mejorando la experiencia del usuario.

## Tareas Pendientes

- [ ] Configurar contenedor Docker para RabbitMQ 
- [ ] Implementar WorkQueueService con soporte para Celery
- [ ] Crear WebSocketManager para comunicación en tiempo real
- [ ] Definir tareas de Celery para cada servicio
- [ ] Implementar endpoints de registro de trabajos
- [ ] Desarrollar cliente JavaScript para integración con frontend
- [ ] Implementar sistema de monitoreo de trabajos