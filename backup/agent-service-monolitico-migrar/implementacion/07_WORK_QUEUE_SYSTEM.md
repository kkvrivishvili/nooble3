# Fase 7: Sistema de Colas de Trabajo con Celery, RabbitMQ e Integración con call_service

## Visión General

Esta fase implementa un sistema de colas de trabajo asíncrono utilizando Celery y RabbitMQ para optimizar las comunicaciones entre el frontend y backend, así como entre los servicios más demandados. Este enfoque reemplaza las conexiones directas HTTP por un sistema de trabajos encolados con WebSockets para notificaciones en tiempo real, aprovechando la función estandarizada `call_service` para todas las comunicaciones HTTP entre servicios.

## Índice

1. [Arquitectura del Sistema](#1-arquitectura-del-sistema)
2. [Configuración Básica](#2-configuración-básica)
3. [Implementación del Núcleo del Sistema](#3-implementación-del-núcleo-del-sistema)
4. [WebSocket Manager](#4-websocket-manager)
5. [Implementación en Agent Service](#5-implementación-en-agent-service)
6. [Cliente JavaScript](#6-cliente-javascript)
7. [Integración con call_service](#7-integración-con-call_service)
8. [Ejemplos de Uso](#8-ejemplos-de-uso)
9. [Estrategia de Migración](#9-estrategia-de-migración)

## 1. Arquitectura del Sistema

### 1.1 Diagrama de Componentes

```
┌────────────────┐   REST API   ┌─────────────────┐     ┌───────────────┐
│                │◄────────────►│                 │     │               │
│    Frontend    │              │  Agent Service  │◄────┤   RabbitMQ    │
│                │◄──WebSocket──┤                 │     │               │
└────────────────┘              └─────────────────┘     └───────────────┘
                                        │                      ▲
                                        │                      │
                                        ▼                      │
                                ┌─────────────────┐     ┌───────────────┐
                                │                 │     │               │
                                │  Work Queue     │◄────┤ Celery Worker │
                                │  Service        │     │               │
                                └─────────────────┘     └───────────────┘
                                        │
                                        │ call_service
                                        ▼
                               ┌───────────────────┐
                               │                   │
                               │ Otros Servicios   │
                               │                   │
                               └───────────────────┘
```

### 1.2 Flujo de Trabajo

1. **Frontend envía una solicitud** al API del Agent Service
2. **Agent Service registra un trabajo** en el sistema de colas
3. **Cliente recibe un ID de trabajo** e inmediatamente establece una conexión WebSocket
4. **Tarea es procesada** por un worker de Celery
5. **Actualizaciones de estado** son enviadas al cliente vía WebSocket
6. **Comunicación entre servicios** ocurre a través de la función `call_service`

### 1.3 Componentes Principales

- **Celery**: Gestión de tareas asíncronas y distribución de carga
- **RabbitMQ**: Broker de mensajes para manejo de colas
- **WebSocket**: Canal de comunicación en tiempo real con el cliente
- **Redis**: Almacenamiento de estado de trabajos y caché
- **call_service**: Función estandarizada para toda comunicación HTTP entre servicios

## 2. Configuración Básica

### 2.1 Instalación de Dependencias

```bash
# Instalar dependencias para RabbitMQ, Celery y WebSockets
pip install celery==5.2.7 redis==4.3.4 aioredis==2.0.1 websockets==10.3 httpx==0.23.0
```

### 2.2 Configuración de Celery

```python
# common/queue/celery_app.py
import os
import functools
from celery import Celery
import json
import asyncio
from typing import Dict, Any, Optional

from ..context.vars import (
    get_current_tenant_id, get_current_agent_id,
    get_current_conversation_id, get_current_collection_id,
    set_current_tenant_id, set_current_agent_id,
    set_current_conversation_id, set_current_collection_id
)
from ..config import get_settings

# Configuración de Celery
settings = get_settings()
celery_app = Celery(
    'work_queue',
    broker=settings.rabbitmq_url,
    backend=settings.redis_url
)

# Configuraciones generales
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,  # Confirmar tareas solo después de completarse con éxito
    worker_prefetch_multiplier=1,  # Control de carga más predecible
    task_track_started=True,  # Rastrear cuando las tareas comienzan
    task_routes={
        'agent_tasks.*': {'queue': 'agent_tasks'},
        'embedding_tasks.*': {'queue': 'embedding_tasks'},
        'query_tasks.*': {'queue': 'query_tasks'}
    }
)
```

### 2.3 Configuración de RabbitMQ

La configuración para el despliegue en producción debe incluir:

- **Usuarios dedicados** para autenticación segura
- **Colas virtuales** para aislar entornos (desarrollo, pruebas, producción)
- **Límites de tareas** para evitar saturación
- **Alta disponibilidad** con configuración en clúster

```python
# Ejemplo de configuración en settings.py
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}"
```

## 3. Implementación del Núcleo del Sistema

### 3.1 Decorador para Preservar Contexto

Este decorador es fundamental para preservar el contexto multitenancy entre procesos:

```python
def create_context_task(queue_name):
    """
    Decorador para crear tareas Celery que preservan el contexto multitenancy.
    
    Maneja la propagación completa del contexto entre servicios y asegura el
    correcto seguimiento de trabajos.
    
    Args:
        queue_name: Nombre de la cola para esta tarea
        
    Returns:
        Decorador que configura la tarea con contexto
    """
    def decorator(func):
        @celery_app.task(name=f"{queue_name}.{func.__name__}", bind=True)
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Restaurar contexto de los kwargs
            ctx_data = kwargs.pop('_context_data', {})
            tenant_id = ctx_data.get('tenant_id')
            agent_id = ctx_data.get('agent_id')
            conversation_id = ctx_data.get('conversation_id')
            collection_id = ctx_data.get('collection_id')
            
            # Establecer contexto para esta tarea
            if tenant_id:
                set_current_tenant_id(tenant_id)
            if agent_id:
                set_current_agent_id(agent_id)
            if conversation_id:
                set_current_conversation_id(conversation_id)
            if collection_id:
                set_current_collection_id(collection_id)
                
            try:
                # Ejecutar la función real
                return func(*args, **kwargs)
            finally:
                # Limpiar contexto al finalizar
                set_current_tenant_id(None)
                set_current_agent_id(None)
                set_current_conversation_id(None)
                set_current_collection_id(None)
        
        # Método para aplicar tarea con contexto
        def apply_async_with_context(ctx=None, *args, **kwargs):
            """
            Ejecuta la tarea con propagación automática del contexto.
            
            Args:
                ctx: Objeto de contexto opcional
                *args, **kwargs: Argumentos para la tarea
                
            Returns:
                AsyncResult: Resultado de la tarea
            """
            # Recopilar contexto
            ctx_data = {}
            
            # Del objeto contexto si está disponible
            if ctx:
                ctx_data['tenant_id'] = ctx.get_tenant_id()
                ctx_data['agent_id'] = ctx.get_agent_id()
                ctx_data['conversation_id'] = ctx.get_conversation_id()
                ctx_data['collection_id'] = ctx.get_collection_id()
            else:
                # Del contexto actual si no se proporciona objeto
                ctx_data['tenant_id'] = get_current_tenant_id()
                ctx_data['agent_id'] = get_current_agent_id()
                ctx_data['conversation_id'] = get_current_conversation_id()
                ctx_data['collection_id'] = get_current_collection_id()
            
            # Incluir datos de contexto en kwargs
            task_kwargs = kwargs.copy()
            task_kwargs['_context_data'] = ctx_data
            
            # Encolar la tarea con el contexto
            return wrapper.apply_async(args=args, kwargs=task_kwargs)
            
        # Adjuntar método al wrapper
        wrapper.apply_async_with_context = apply_async_with_context
        return wrapper
    
    return decorator

### 3.2 Implementación de WorkQueueService

```python
# common/queue/work_queue.py
import logging
import json
import hashlib
from datetime import datetime
import asyncio
from typing import Dict, Any, Optional, List

from ..context.vars import get_current_tenant_id, get_current_agent_id
from ..context.vars import get_current_conversation_id, get_current_collection_id
from ..cache.manager import CacheManager
from ..config import get_settings

logger = logging.getLogger(__name__)

class WorkQueueService:
    """
    Gestiona la integración entre Celery, caché y WebSockets.
    """
    
    def __init__(self, websocket_manager=None):
        """
        Inicializa el servicio de colas de trabajo.
        
        Args:
            websocket_manager: Gestor de WebSockets opcional
        """
        from ..config import get_settings
        self.settings = get_settings()
        self.websocket_manager = websocket_manager
        
    async def register_job(self, tenant_id, job_type, params, ctx=None):
        """
        Registra un nuevo trabajo en la cola.
        
        Args:
            tenant_id: ID del tenant
            job_type: Tipo de trabajo
            params: Parámetros del trabajo
            ctx: Contexto opcional
            
        Returns:
            Dict: Información del trabajo registrado
        """
        # Generar ID único para el trabajo
        import uuid
        job_id = str(uuid.uuid4())
        
        # Guardar metadata del trabajo
        job_metadata = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "job_type": job_type,
            "params": params,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Guardar en caché
        await CacheManager.set(
            data_type="job_metadata",
            resource_id=job_id,
            value=job_metadata,
            tenant_id=tenant_id,
            ttl=3600  # 1 hora
        )
        
        # Registrar en métricas
        try:
            from ..utils.metrics import track_performance_metric
            await track_performance_metric(
                metric_type="work_queue_job_registered",
                value=1,
                tenant_id=tenant_id,
                metadata={"job_type": job_type}
            )
        except ImportError:
            logger.debug("Módulo de métricas no disponible")
        
        return {
            "job_id": job_id,
            "status": "queued"
        }
    
    async def get_job_status(self, job_id, tenant_id=None):
        """
        Obtiene el estado actual de un trabajo.
        
        Args:
            job_id: ID del trabajo
            tenant_id: ID del tenant (opcional)
            
        Returns:
            Dict: Estado actual del trabajo o None si no existe
        """
        # Obtener metadata del trabajo
        job_metadata = await CacheManager.get(
            data_type="job_metadata",
            resource_id=job_id,
            tenant_id=tenant_id
        )
        
        if not job_metadata:
            return None
            
        # Extraer datos importantes
        return {
            "job_id": job_id,
            "status": job_metadata.get("status", "unknown"),
            "created_at": job_metadata.get("created_at"),
            "updated_at": job_metadata.get("updated_at"),
            "result": job_metadata.get("result"),
            "error": job_metadata.get("error")
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
        if self.websocket_manager:
            await self._notify_status_update(job_id, status, result, error)
        
        # Registrar en métricas
        try:
            from ..utils.metrics import track_performance_metric
            await track_performance_metric(
                metric_type=f"work_queue_job_{status}",
                value=1,
                tenant_id=tenant_id,
                metadata={"job_type": job_type}
            )
        except ImportError:
            logger.debug("Módulo de métricas no disponible")
        
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
        
        Args:
            tenant_id: ID del tenant
            job_type: Tipo de trabajo
            params: Parámetros del trabajo, debe ser un diccionario serializable
            
        Returns:
            Clave de caché única compatible con el patrón Cache-Aside estándar
        """
        # Normalizar y ordenar parámetros para garantizar consistencia
        if not isinstance(params, dict):
            params = {"value": str(params)}
            
        # Serialización consistente
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

## 4. WebSocket Manager

### 4.1 Implementación del Gestor de WebSockets

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
```

### 4.2 Endpoint WebSocket para Suscripciones

```python
# agent-service/routes/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from common.websocket.manager import WebSocketManager
from common.errors.handlers import handle_errors
import uuid
import logging

router = APIRouter()
websocket_manager = WebSocketManager()
logger = logging.getLogger(__name__)

@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_endpoint(websocket: WebSocket, job_id: str):
    """
    Endpoint WebSocket para suscribirse a actualizaciones de un trabajo.
    
    Args:
        websocket: Conexión WebSocket
        job_id: ID del trabajo a monitorear
    """
    client_id = str(uuid.uuid4())
    tenant_id = None
    
    # Extraer tenant_id de los headers
    try:
        tenant_id = websocket.headers.get("x-tenant-id")
    except Exception as e:
        logger.warning(f"No se pudo extraer tenant_id de headers: {str(e)}")
    
    # Aceptar conexión
    await websocket.accept()
    
    # Registrar cliente
    await websocket_manager.register_connection(websocket, client_id, tenant_id)
    
    # Suscribir a actualizaciones del trabajo
    await websocket_manager.subscribe_to_job(client_id, job_id)
    
    # Enviar mensaje inicial de confirmación
    await websocket.send_json({
        "type": "connection_established",
        "job_id": job_id,
        "client_id": client_id
    })
    
    try:
        # Mantener conexión abierta hasta que el cliente se desconecte
        while True:
            # Esperar mensajes (principalmente heartbeats)
            data = await websocket.receive_text()
            
            # Procesar mensajes especiales del cliente
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        # Cliente desconectado
        logger.info(f"Cliente {client_id} desconectado del trabajo {job_id}")
    except Exception as e:
        # Error en la conexión
        logger.error(f"Error en WebSocket para job_id={job_id}, client_id={client_id}: {str(e)}")
    finally:
        # Limpiar conexión
        await websocket_manager.unregister_connection(client_id)
```

## 5. Implementación en Agent Service

### 5.1 Tareas de Celery para Agentes

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
```

### 5.2 Endpoint para Registro de Trabajos

```python
# agent-service/routes/jobs.py
from fastapi import APIRouter, WebSocket, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from common.context import Context, with_context
from common.queue.work_queue import WorkQueueService
from common.websocket.manager import WebSocketManager
from common.errors.handlers import handle_errors
from agent_service.tasks.agent_tasks import execute_agent
from agent_service.schemas.agent import AgentExecuteRequest
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
        ctx=ctx
    )
    
    # Encolar tarea asíncrona
    task = execute_agent.apply_async_with_context(
        ctx=ctx,
        args=[
            agent_id,
            request.input,
            request.collection_id,
            request.use_auto_federation
        ]
    )
    
    # Devolver información del trabajo
    return {
        "job_id": result["job_id"],
        "status": "queued",
        "task_id": task.id
    }

@router.get("/jobs/{job_id}/status", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="api")
async def get_job_status(job_id: str, ctx: Context = None):
    """
    Endpoint para consultar el estado actual de un trabajo.
    
    Args:
        job_id: ID del trabajo
        ctx: Contexto
        
    Returns:
        Estado actual del trabajo
    """
    tenant_id = ctx.get_tenant_id() if ctx else None
    
    # Obtener estado
    status = await work_queue.get_job_status(job_id, tenant_id=tenant_id)
    
    if not status:
        raise HTTPException(status_code=404, detail=f"Trabajo no encontrado: {job_id}")
        
    return status
```

## 6. Implementación con call_service

Esta sección describe cómo integrar el sistema de colas de trabajo con la función `call_service` para la comunicación entre servicios, asegurando la propagación de contexto, manejo de errores y caché.

### 6.1 Refactorización de WorkQueueService

```python
# common/queue/work_queue.py
from common.http.call_service import call_service
from common.cache.manager import CacheManager
from common.cache.helpers import get_with_cache_aside
from common.errors.handlers import handle_errors
from common.websocket.manager import WebSocketManager
from common.context import Context
import json
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)

class WorkQueueService:
    def __init__(self, websocket_manager=None):
        self.websocket_manager = websocket_manager or WebSocketManager()
    
    @handle_errors(error_type="service", log_traceback=True)
    async def register_job(self, tenant_id, job_type, params, ctx=None):
        """
        Registra un nuevo trabajo en el sistema de colas utilizando call_service
        para comunicación entre servicios.
        
        Args:
            tenant_id: ID del tenant
            job_type: Tipo de trabajo
            params: Parámetros para el trabajo
            ctx: Contexto de la operación
            
        Returns:
            Información del trabajo registrado
        """
        # Generar ID único para el trabajo
        job_id = str(uuid.uuid4())
        
        # Crear datos del trabajo
        job_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "job_type": job_type,
            "params": params,
            "status": "queued",
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        
        # Guardar en caché con el patrón Cache-Aside
        await CacheManager.set(
            data_type="work_job",
            resource_id=job_id,
            value=job_data,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
        
        # Registrar en base de datos via call_service
        response = await call_service(
            url="agent-service/internal/jobs/register",
            data={
                "job_id": job_id,
                "tenant_id": tenant_id,
                "job_type": job_type,
                "params": params
            },
            method="POST",
            timeout=5,  # Timeout corto para operaciones críticas
            tenant_id=tenant_id,
            context=ctx
        )
        
        if not response.get("success"):
            raise ValueError(f"Error al registrar trabajo: {response.get('message')}")
        
        # Notificar por WebSocket
        if self.websocket_manager:
            await self.websocket_manager.broadcast_to_tenant(
                tenant_id=tenant_id,
                message={
                    "type": "job_update",
                    "data": {
                        "job_id": job_id,
                        "status": "queued",
                        "job_type": job_type
                    }
                }
            )
        
        return {"job_id": job_id, "status": "queued"}
    
    @handle_errors(error_type="service")
    async def get_job_status(self, job_id, tenant_id=None):
        """
        Obtiene el estado actual de un trabajo utilizando el patrón Cache-Aside.
        
        Args:
            job_id: ID del trabajo
            tenant_id: ID del tenant
            
        Returns:
            Estado actual del trabajo
        """
        # Implementar patrón Cache-Aside usando el helper centralizado
        job_data, metrics = await get_with_cache_aside(
            data_type="work_job",
            resource_id=job_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_job_from_db,
            ttl=CacheManager.ttl_short  # TTL corto para datos que cambian frecuentemente
        )
        
        return job_data
    
    async def _fetch_job_from_db(self, resource_id, tenant_id=None):
        """
        Función para obtener datos del trabajo desde la base de datos.
        
        Args:
            resource_id: ID del trabajo
            tenant_id: ID del tenant
            
        Returns:
            Datos del trabajo desde la base de datos
        """
        # Obtener desde el servicio de base de datos usando call_service
        response = await call_service(
            url=f"agent-service/internal/jobs/{resource_id}",
            data={},
            method="GET",
            tenant_id=tenant_id,
            timeout=3,  # Timeout corto para lecturas
            cache_ttl=60,  # Caché de 1 minuto para lecturas repetidas
            use_cache_only_on_error=True,  # Usar caché solo en caso de error
        )
        
        if not response.get("success"):
            logger.warning(f"Error obteniendo trabajo {resource_id}: {response.get('message')}")
            return None
            
        return response.get("data")
    
    @handle_errors(error_type="service", log_traceback=True)  
    async def update_job_status(self, job_id, status, result=None, error=None):
        """
        Actualiza el estado de un trabajo y notifica a clientes vía WebSocket.
        
        Args:
            job_id: ID del trabajo
            status: Nuevo estado
            result: Resultado opcional
            error: Error opcional
            
        Returns:
            ID del trabajo actualizado
        """
        # Obtener datos actuales del trabajo
        job_data = await self.get_job_status(job_id)
        
        if not job_data:
            raise ValueError(f"Trabajo no encontrado: {job_id}")
            
        tenant_id = job_data.get("tenant_id")
        
        # Actualizar estado
        job_data["status"] = status
        job_data["updated_at"] = datetime.datetime.utcnow().isoformat()
        
        if result:
            job_data["result"] = result
        
        if error:
            job_data["error"] = error
        
        # Actualizar en caché primero (Cache-Aside pattern)
        await CacheManager.set(
            data_type="work_job",
            resource_id=job_id,
            value=job_data,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
        
        # Actualizar en base de datos via call_service (con reintentos)
        response = await call_service(
            url=f"agent-service/internal/jobs/{job_id}/status",
            data={
                "status": status,
                "result": result,
                "error": error
            },
            method="PUT",
            tenant_id=tenant_id,
            timeout=5,
            retry_options={"max_retries": 3, "retry_delay": 0.5}  # Reintentos para operaciones críticas
        )
        
        if not response.get("success"):
            logger.error(f"Error al actualizar trabajo {job_id}: {response.get('message')}")
        
        # Notificar por WebSocket
        if self.websocket_manager:
            ws_data = {
                "job_id": job_id,
                "status": status,
                "job_type": job_data.get("job_type")
            }
            
            if result:
                ws_data["result"] = result
                
            if error:
                ws_data["error"] = error
                
            await self.websocket_manager.broadcast_to_tenant(
                tenant_id=tenant_id,
                message={
                    "type": "job_update",
                    "data": ws_data
                }
            )
        
        return job_id
```

### 6.2 Implementación del Endpoint Internal

```python
# agent-service/routes/internal.py
from fastapi import APIRouter, Depends, Body, HTTPException
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.db.supabase import get_supabase_client
from common.models.base import BaseResponse
import datetime

router = APIRouter(prefix="/internal", tags=["internal"])

@router.post("/jobs/register", response_model=BaseResponse)
@with_context(tenant=True)
@handle_errors(error_type="api")
async def register_job_internal(
    data: dict = Body(...),
    ctx: Context = None
):
    """
    Endpoint interno para registrar un trabajo en la base de datos.
    
    Args:
        data: Datos del trabajo
        ctx: Contexto
        
    Returns:
        Respuesta de éxito/fallo
    """
    # Validar datos requeridos
    required_fields = ["job_id", "tenant_id", "job_type", "params"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Campo requerido: {field}")
    
    # Validar tenant_id con contexto
    tenant_id = ctx.get_tenant_id()
    if tenant_id != data["tenant_id"]:
        raise ValueError("El tenant_id no coincide con el contexto")
    
    # Crear datos a insertar
    insert_data = {
        "id": data["job_id"],
        "tenant_id": tenant_id,
        "job_type": data["job_type"],
        "params": data["params"],
        "status": "queued",
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow()
    }
    
    # Obtener cliente Supabase
    supabase = await get_supabase_client()
    
    # Insertar en la base de datos
    result = await supabase.table("jobs").insert(insert_data).execute()
    
    return {"success": True, "message": "Trabajo registrado correctamente"}

@router.get("/jobs/{job_id}", response_model=BaseResponse)
@with_context(tenant=True, validate_tenant=False)
@handle_errors(error_type="api")
async def get_job_internal(job_id: str, ctx: Context = None):
    """
    Endpoint interno para obtener información de un trabajo.
    
    Args:
        job_id: ID del trabajo
        ctx: Contexto
        
    Returns:
        Datos del trabajo
    """
    # Obtener cliente Supabase
    supabase = await get_supabase_client()
    
    # Consultar trabajo
    response = await supabase.table("jobs").select("*").eq("id", job_id).execute()
    
    if not response.data or len(response.data) == 0:
        return {"success": False, "message": f"Trabajo no encontrado: {job_id}"}
    
    job_data = response.data[0]
    
    # Validar tenant si existe contexto
    tenant_id = ctx.get_tenant_id() if ctx else None
    if tenant_id and job_data.get("tenant_id") != tenant_id:
        return {"success": False, "message": "No autorizado para acceder a este trabajo"}
    
    return {"success": True, "data": job_data}

@router.put("/jobs/{job_id}/status", response_model=BaseResponse)
@with_context(tenant=True, validate_tenant=False)
@handle_errors(error_type="api")
async def update_job_status_internal(
    job_id: str,
    data: dict = Body(...),
    ctx: Context = None
):
    """
    Endpoint interno para actualizar el estado de un trabajo.
    
    Args:
        job_id: ID del trabajo
        data: Datos de actualización
        ctx: Contexto
        
    Returns:
        Respuesta de éxito/fallo
    """
    # Validar datos requeridos
    if "status" not in data:
        raise ValueError("Campo requerido: status")
    
    # Obtener trabajo actual
    supabase = await get_supabase_client()
    response = await supabase.table("jobs").select("*").eq("id", job_id).execute()
    
    if not response.data or len(response.data) == 0:
        return {"success": False, "message": f"Trabajo no encontrado: {job_id}"}
    
    job_data = response.data[0]
    
    # Validar tenant si existe contexto
    tenant_id = ctx.get_tenant_id() if ctx else None
    if tenant_id and job_data.get("tenant_id") != tenant_id:
        return {"success": False, "message": "No autorizado para actualizar este trabajo"}
    
    # Preparar datos de actualización
    update_data = {
        "status": data["status"],
        "updated_at": datetime.datetime.utcnow()
    }
    
    if "result" in data and data["result"] is not None:
        update_data["result"] = data["result"]
    
    if "error" in data and data["error"] is not None:
        update_data["error"] = data["error"]
    
    # Actualizar en base de datos
    await supabase.table("jobs").update(update_data).eq("id", job_id).execute()
    
    return {"success": True, "message": "Estado del trabajo actualizado correctamente"}
```

## 7. Cliente JavaScript para Work Queue

### 7.1 Implementación del Cliente

```javascript
// client/src/services/workQueueService.js
import axios from 'axios';
import { API_BASE_URL } from '../config';
import WebSocketService from './websocketService';

class WorkQueueService {
  constructor() {
    this.baseUrl = API_BASE_URL;
    this.websocketService = new WebSocketService();
    this.jobUpdateCallbacks = new Map();
    
    // Suscribirse a actualizaciones de WebSocket
    this.websocketService.subscribe('job_update', this.handleJobUpdate.bind(this));
  }
  
  /**
   * Maneja las actualizaciones de trabajos recibidas por WebSocket
   * @param {Object} data - Datos de actualización del trabajo
   */
  handleJobUpdate(data) {
    const jobId = data.job_id;
    
    // Notificar a los callbacks registrados para este trabajo
    if (this.jobUpdateCallbacks.has(jobId)) {
      const callbacks = this.jobUpdateCallbacks.get(jobId);
      callbacks.forEach(callback => callback(data));
    }
  }
  
  /**
   * Registrar un nuevo trabajo de agente
   * @param {string} agentId - ID del agente a ejecutar
   * @param {Object} params - Parámetros para la ejecución
   * @returns {Promise<Object>} - Información del trabajo registrado
   */
  async executeAgent(agentId, params) {
    try {
      const response = await axios.post(
        `${this.baseUrl}/jobs/agent/${agentId}/execute`,
        params,
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );
      
      return response.data;
    } catch (error) {
      console.error('Error al ejecutar agente:', error);
      throw error;
    }
  }
  
  /**
   * Obtener el estado actual de un trabajo
   * @param {string} jobId - ID del trabajo
   * @returns {Promise<Object>} - Estado actual del trabajo
   */
  async getJobStatus(jobId) {
    try {
      const response = await axios.get(
        `${this.baseUrl}/jobs/${jobId}/status`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );
      
      return response.data;
    } catch (error) {
      console.error('Error al obtener estado del trabajo:', error);
      throw error;
    }
  }
  
  /**
   * Suscribirse a actualizaciones de un trabajo específico
   * @param {string} jobId - ID del trabajo
   * @param {Function} callback - Función a llamar cuando haya actualizaciones
   * @returns {Function} - Función para cancelar la suscripción
   */
  subscribeToJobUpdates(jobId, callback) {
    if (!this.jobUpdateCallbacks.has(jobId)) {
      this.jobUpdateCallbacks.set(jobId, new Set());
    }
    
    this.jobUpdateCallbacks.get(jobId).add(callback);
    
    // Devolver función para cancelar suscripción
    return () => {
      const callbacks = this.jobUpdateCallbacks.get(jobId);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.jobUpdateCallbacks.delete(jobId);
        }
      }
    };
  }
}

export default new WorkQueueService(); // Singleton
```

### 7.2 Ejemplo de Uso del Cliente

```jsx
// client/src/components/AgentExecutionForm.jsx
import React, { useState, useEffect } from 'react';
import workQueueService from '../services/workQueueService';

const AgentExecutionForm = ({ agentId }) => {
  const [input, setInput] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  
  // Efecto para limpiar suscripciones
  useEffect(() => {
    let unsubscribe = null;
    
    // Si tenemos un jobId, nos suscribimos a actualizaciones
    if (jobId) {
      unsubscribe = workQueueService.subscribeToJobUpdates(jobId, (data) => {
        setJobStatus(data.status);
        
        if (data.result) {
          setResult(data.result);
        }
        
        if (data.error) {
          setError(data.error);
        }
        
        // Si el trabajo se completa o falla, dejamos de mostrar loading
        if (data.status === 'completed' || data.status === 'failed') {
          setIsLoading(false);
        }
      });
    }
    
    // Limpiar suscripción al desmontar
    return () => {
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [jobId]);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setResult(null);
    setError(null);
    
    try {
      const response = await workQueueService.executeAgent(agentId, {
        input,
        collection_id: collectionId || undefined,
        use_auto_federation: true
      });
      
      setJobId(response.job_id);
      setJobStatus(response.status);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al ejecutar el agente');
      setIsLoading(false);
    }
  };
  
  return (
    <div className="agent-execution-form">
      <h2>Ejecutar Agente</h2>
      
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Consulta:</label>
          <textarea 
            value={input} 
            onChange={(e) => setInput(e.target.value)}
            required
            placeholder="Ingresa tu consulta aquí..."
          />
        </div>
        
        <div className="form-group">
          <label>Colección (opcional):</label>
          <input 
            type="text" 
            value={collectionId} 
            onChange={(e) => setCollectionId(e.target.value)}
            placeholder="ID de colección"
          />
        </div>
        
        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Procesando...' : 'Ejecutar'}
        </button>
      </form>
      
      {jobStatus && (
        <div className="job-status">
          <h3>Estado del Trabajo:</h3>
          <p><strong>ID:</strong> {jobId}</p>
          <p><strong>Estado:</strong> {jobStatus}</p>
          
          {result && (
            <div className="job-result">
              <h4>Resultado:</h4>
              <div className="response-container">
                <p>{result.answer}</p>
                {result.metadata && (
                  <details>
                    <summary>Metadatos</summary>
                    <pre>{JSON.stringify(result.metadata, null, 2)}</pre>
                  </details>
                )}
              </div>
            </div>
          )}
          
          {error && (
            <div className="error-message">
              <h4>Error:</h4>
              <p>{error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AgentExecutionForm;
```

## 8. Estrategia de Migración y Buenas Prácticas

### 8.1 Plan de Migración Gradual

La migración desde la implementación actual a la nueva con `call_service` debe seguir un enfoque gradual para minimizar el impacto:

1. **Fase 1: Implementación Paralela**
   - Crear las nuevas clases y métodos con soporte para `call_service`
   - Mantener la implementación actual en producción
   - Implementar rutas de prueba para la nueva implementación

2. **Fase 2: Migración de Servicios Internos**
   - Migrar primero las rutas internas a la nueva implementación
   - Utilizar feature flags para controlar la habilitación de la nueva implementación
   - Actualizar las pruebas internas para validar el comportamiento

3. **Fase 3: Migración de Endpoints Públicos**
   - Migrar los endpoints públicos a la nueva implementación gradualmente
   - Comenzar con endpoints no críticos
   - Monitorear métricas de rendimiento y errores

4. **Fase 4: Remoción del Código Antiguo**
   - Una vez validado el funcionamiento, remover la implementación anterior
   - Actualizar toda la documentación
   - Completar pruebas de regresión

### 8.2 Tiempos de Timeout y TTL Recomendados

La configuración de timeouts y TTLs debe seguir estas directrices según el tipo de operación:

| Operación | Timeout | TTL Caché | Retry Options | Justificación |
|------------|---------|-----------|---------------|---------------|
| Registro de trabajo | 5s | Standard (1h) | max_retries: 3, retry_delay: 0.5s | Operación crítica, necesita completarse con éxito |
| Lectura de estado | 3s | Short (5m) | max_retries: 2, retry_delay: 0.3s | Operación frecuente, debe ser rápida |
| Actualización de estado | 5s | Standard (1h) | max_retries: 3, retry_delay: 0.5s | Operación crítica, requiere consistencia |
| Notificación WebSocket | 2s | N/A | max_retries: 1, retry_delay: 0.2s | No crítico, puede fallar con impacto menor |

### 8.3 Buenas Prácticas de Implementación

1. **Manejo de Errores**
   - Utilizar consistentemente el decorador unificado `@handle_errors`
   - Configurar el nivel de detalle adecuado según el tipo de endpoint
   - Mantener contexto enriquecido en cada error

2. **Gestión de Contexto**
   - Aplicar `@with_context` en todos los endpoints
   - Validar explícitamente el tenant_id cuando sea necesario
   - Propagar el contexto completo en llamadas a `call_service`

3. **Patrón Cache-Aside**
   - Usar `get_with_cache_aside` para implementar el patrón
   - Utilizar los TTL estandarizados de `CacheManager`
   - Seguir la jerarquía de claves basada en tenant_id

4. **Comunicación entre Servicios**
   - Utilizar siempre `call_service` para peticiones HTTP
   - Configurar timeouts apropiados según la criticidad
   - Implementar políticas de reintento para operaciones críticas

5. **WebSockets**
   - Gestionar adecuadamente las conexiones y desconexiones
   - Implementar reconexiones automáticas en el cliente
   - Serializar correctamente los mensajes

### 8.4 Métricas y Monitoreo

Se recomienda monitorear las siguientes métricas:

1. **Latencia**
   - Tiempo de registro de trabajos
   - Tiempo de actualización de estado
   - Tiempo total de ejecución de trabajos

2. **Tasas de Error**
   - Errores en registro de trabajos
   - Errores en actualizaciones de estado
   - Errores en conexiones WebSocket

3. **Utilización de Caché**
   - Hit ratio del caché
   - Tamaño promedio de objetos en caché
   - Invalidaciones de caché

4. **Estado de Workers**
   - Cola de trabajos pendientes
   - Trabajos activos
   - Tiempo de procesamiento por tipo de trabajo

## 9. Colas de Trabajo entre Servicios

Esta sección describe la implementación de colas intermedias entre el Agent Service y los servicios especializados (Query Service, Embedding Service, Ingestion Service) para gestionar de manera eficiente las peticiones a APIs externas y optimizar la comunicación entre servicios.

### 9.1 Motivación y Beneficios

La implementación de colas entre servicios ofrece múltiples ventajas:

1. **Desacoplamiento total**: Los servicios pueden operar de forma independiente sin bloqueos mutuos.
2. **Gestión de carga**: Control de peticiones a APIs externas (Groq, OpenAI) para evitar throttling.
3. **Priorización**: Capacidad de priorizar peticiones críticas sobre operaciones en background.
4. **Resiliencia**: Captura de peticiones durante caídas temporales de servicios o APIs externas.
5. **Observabilidad**: Monitoreo detallado del flujo de trabajo entre servicios.

### 9.2 Arquitectura de Colas entre Servicios

```
┌─────────────────┐      ┌──────────────┐      ┌──────────────────┐
│                 │      │              │      │                  │
│   Agent Service ├─────►│  Cola LLM    ├─────►│  Query Service   │
│                 │      │              │      │                  │
│    Orquestador  │      └──────────────┘      │    (Groq API)    │
│                 │                            │                  │
│      Central    │      ┌──────────────┐      └──────────────────┘
│                 │      │              │      
│                 ├─────►│ Cola Embed   ├─────►┌──────────────────┐
│                 │      │              │      │                  │
└─────────────────┘      └──────────────┘      │ Embedding Service│
                                               │                  │
                         ┌──────────────┐      │   (OpenAI API)   │
                         │              │      │                  │
                         │Cola Ingestion├─────►└──────────────────┘
                         │              │      
                         └──────────────┘      ┌──────────────────┐
                                               │                  │
                                               │Ingestion Service │
                                               │                  │
                                               └──────────────────┘
```

### 9.3 Implementación por Fases

#### Fase 1: Extensión del Modelo de Colas

La primera fase consiste en extender el modelo de colas actual para soportar tipos específicos de trabajos para cada servicio:

```python
# common/queue/service_jobs.py
from common.queue.work_queue import WorkQueueService
from common.context import Context

class ServiceQueueManager:
    """Gestor de colas entre servicios"""
    
    def __init__(self, work_queue_service=None):
        self.work_queue = work_queue_service or WorkQueueService()
    
    async def enqueue_llm_request(self, tenant_id, prompt, model, 
                                temperature=0.7, max_tokens=None, ctx=None):
        """Encola una petición LLM al Query Service"""
        params = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        return await self.work_queue.register_job(
            tenant_id=tenant_id,
            job_type="llm_request",
            params=params,
            ctx=ctx,
            priority="high"  # Prioridad alta para peticiones interactivas
        )
    
    async def enqueue_embedding_request(self, tenant_id, text, model, ctx=None):
        """Encola una petición de embedding al Embedding Service"""
        params = {
            "text": text,
            "model": model
        }
        
        return await self.work_queue.register_job(
            tenant_id=tenant_id,
            job_type="embedding_request",
            params=params,
            ctx=ctx,
            priority="medium"  # Prioridad media para embeddings
        )
    
    async def enqueue_document_processing(self, tenant_id, document_id, collection_id, ctx=None):
        """Encola procesamiento de documentos en Ingestion Service"""
        params = {
            "document_id": document_id,
            "collection_id": collection_id
        }
        
        return await self.work_queue.register_job(
            tenant_id=tenant_id,
            job_type="document_processing",
            params=params,
            ctx=ctx,
            priority="low"  # Prioridad baja para procesamiento en background
        )
```

#### Fase 2: Implementación de Trabajadores en Servicios Especializados

En cada servicio especializado, implementar trabajadores dedicados para procesar las tareas de la cola:

```python
# query-service/tasks/llm_tasks.py
from common.queue.celery_app import create_context_task, celery_app
import asyncio
import logging

logger = logging.getLogger(__name__)

@create_context_task("llm_tasks")
def process_llm_request(params, ctx=None):
    """Procesa una petición LLM desde la cola de trabajo"""
    from query_service.service import llm_service
    
    # Configurar bucle de eventos asyncio
    loop = asyncio.get_event_loop()
    
    try:
        # Extraer parámetros
        prompt = params.get("prompt")
        model = params.get("model")
        temperature = params.get("temperature", 0.7)
        max_tokens = params.get("max_tokens")
        
        # Actualizar estado
        job_id = asyncio.run_coroutine_threadsafe(
            celery_app.work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="processing"
            ),
            loop
        ).result()
        
        # Procesar petición LLM
        response = asyncio.run_coroutine_threadsafe(
            llm_service.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                ctx=ctx
            ),
            loop
        ).result()
        
        # Extraer resultado
        result = {
            "text": response.text,
            "model": response.model,
            "usage": response.usage
        }
        
        # Actualizar estado
        asyncio.run_coroutine_threadsafe(
            celery_app.work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="completed",
                result=result
            ),
            loop
        ).result()
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing LLM request: {str(e)}")
        # Actualizar estado
        asyncio.run_coroutine_threadsafe(
            celery_app.work_queue.update_job_status(
                job_id=celery_app.current_task.request.id,
                status="failed",
                error=str(e)
            ),
            loop
        ).result()
        raise
```

#### Fase 3: Endpoints de Procesamiento en Servicios Especializados

Cada servicio debe exponer endpoints para procesar tareas encoladas:

```python
# query-service/routes/internal.py
from fastapi import APIRouter, Body, Depends
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from query_service.tasks.llm_tasks import process_llm_request

router = APIRouter(prefix="/internal", tags=["internal"])

@router.post("/jobs/llm/enqueue", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="api")
async def enqueue_llm_job(data: dict = Body(...), ctx: Context = None):
    """Endpoint para encolar una tarea LLM desde otro servicio"""
    if not ctx:
        raise ValueError("Contexto requerido para enqueue_llm_job")
        
    tenant_id = ctx.get_tenant_id()
    
    # Validar datos
    if "prompt" not in data or "model" not in data:
        raise ValueError("prompt y model son campos requeridos")
    
    # Encolar tarea
    task = process_llm_request.apply_async_with_context(
        ctx=ctx,
        kwargs={"params": data}
    )
    
    return {
        "task_id": task.id,
        "status": "queued"
    }
```

#### Fase 4: Integración con call_service para Comunicación entre Servicios

Modificar el llamado entre servicios para usar el sistema de colas a través de call_service:

```python
# agent-service/services/llm_service.py
from common.http.call_service import call_service
from common.queue.service_jobs import ServiceQueueManager
from common.errors.handlers import handle_errors
from common.context import Context

class AgentLLMService:
    def __init__(self):
        self.service_queue = ServiceQueueManager()
    
    @handle_errors(error_type="service")
    async def generate_text(self, prompt, model, tenant_id, ctx=None, wait=True):
        """Genera texto usando el Query Service a través de la cola de trabajo"""
        # Encolar petición
        job_result = await self.service_queue.enqueue_llm_request(
            tenant_id=tenant_id,
            prompt=prompt,
            model=model,
            ctx=ctx
        )
        
        job_id = job_result["job_id"]
        
        # Si se requiere esperar
        if wait:
            # Esperar hasta 30 segundos por el resultado
            max_attempts = 30
            attempt = 0
            
            while attempt < max_attempts:
                # Verificar estado
                status = await self.service_queue.work_queue.get_job_status(job_id, tenant_id)
                
                if status["status"] == "completed":
                    return status["result"]
                    
                if status["status"] == "failed":
                    raise ValueError(f"LLM request failed: {status.get('error')}")
                    
                # Esperar un segundo antes de verificar nuevamente
                await asyncio.sleep(1)
                attempt += 1
                
            raise TimeoutError("LLM request timed out")
        
        # Si no se requiere esperar, devolver job_id para verificar después
        return {"job_id": job_id, "status": "queued"}
```

### 9.4 Configuración de Colas y Prioridades

La configuración de colas debe ajustarse según las necesidades específicas de cada tipo de operación:

```python
# common/config/queue_settings.py

# Configuración de colas por servicio
QUEUE_SETTINGS = {
    "llm_request": {
        "queue_name": "llm_queue",
        "concurrency": 10,  # Número de trabajadores concurrentes
        "rate_limit": "100/m",  # Límite de tasa (peticiones por minuto)
        "prefetch_count": 1,  # Un trabajo a la vez por trabajador
        "ack_late": True,  # Confirmar después de procesar
        "retry_policy": {
            "max_retries": 3,
            "interval_start": 0.5,  # Segundos antes del primer reintento
            "interval_step": 0.5,  # Incremento entre reintentos
            "interval_max": 5  # Máximo tiempo entre reintentos
        }
    },
    "embedding_request": {
        "queue_name": "embedding_queue",
        "concurrency": 20,  # Mayor concurrencia para embeddings
        "rate_limit": "600/m",  # Límite de tasa más alto
        "prefetch_count": 10,  # Más trabajos por trabajador
        "ack_late": True,
        "retry_policy": {
            "max_retries": 5,
            "interval_start": 0.2,
            "interval_step": 0.3,
            "interval_max": 3
        }
    },
    "document_processing": {
        "queue_name": "ingestion_queue",
        "concurrency": 5,  # Menor concurrencia para procesamiento pesado
        "rate_limit": "50/m",
        "prefetch_count": 1,
        "ack_late": True,
        "retry_policy": {
            "max_retries": 10,  # Más reintentos para procesamientos largos
            "interval_start": 1.0,
            "interval_step": 2.0,
            "interval_max": 30  # Tiempo máximo mayor entre reintentos
        }
    }
}

# Configuración de prioridades
PRIORITY_SETTINGS = {
    "high": 10,    # Mayor prioridad para tareas interactivas
    "medium": 5,  # Prioridad media para tareas normales
    "low": 1      # Baja prioridad para tareas en background
}
```

### 9.5 Patrones de Uso Recomendados

#### Peticiones Síncronas vs. Asíncronas

Existen dos patrones principales para utilizar las colas entre servicios:

**1. Patrón Síncrono** (esperar resultado):
```python
# Para peticiones que necesitan respuesta inmediata (ej: chat interactivo)
try:
    result = await agent_llm_service.generate_text(
        prompt="Resumen este texto: " + user_input,
        model="llama-3-8b",
        tenant_id=tenant_id,
        wait=True  # Esperar resultado
    )
    return result["text"]
except TimeoutError:
    return "Lo siento, la respuesta está tomando más tiempo del esperado. Por favor intenta nuevamente."
```

**2. Patrón Asíncrono** (no esperar resultado):
```python
# Para tareas en segundo plano (ej: procesamiento de documentos)
job_info = await agent_ingestion_service.process_document(
    document_id=doc_id,
    collection_id=coll_id,
    tenant_id=tenant_id,
    wait=False  # No esperar resultado
)

return {
    "message": "Documento en procesamiento",
    "job_id": job_info["job_id"],
    "status_url": f"/api/jobs/{job_info['job_id']}/status"
}
```

#### Selección Dinámica de Cola según Carga

Para optimizar recursos, se puede implementar selección dinámica de colas:

```python
async def select_optimal_queue(job_type, tenant_id):
    """Selecciona la cola óptima basada en carga actual"""
    # Obtener métricas de colas
    queues_metrics = await get_queues_metrics()
    
    # Seleccionar cola menos cargada para el tipo de trabajo
    available_queues = [q for q in queues_metrics if q["type"] == job_type]
    if not available_queues:
        return f"{job_type}_default"  # Cola por defecto
    
    # Ordenar por carga (menos cargada primero)
    sorted_queues = sorted(available_queues, key=lambda q: q["active_tasks"])
    return sorted_queues[0]["name"]
```

### 9.6 Monitoreo y Alertas

Implementar un sistema de monitoreo específico para las colas entre servicios:

```python
# common/monitoring/queue_metrics.py
from common.cache.manager import CacheManager
from datetime import datetime, timedelta
import json

async def track_queue_metrics(queue_name, metric_type, value):
    """Registra métricas de cola para monitoreo"""
    # Clave en caché para la métrica
    cache_key = f"queue_metrics:{queue_name}:{metric_type}"
    
    # Obtener métricas actuales
    metrics = await CacheManager.get("queue_metrics", cache_key) or []
    
    # Añadir nueva métrica con timestamp
    new_metric = {
        "timestamp": datetime.utcnow().isoformat(),
        "value": value
    }
    
    metrics.append(new_metric)
    
    # Mantener solo últimas 100 muestras
    if len(metrics) > 100:
        metrics = metrics[-100:]
    
    # Guardar en caché
    await CacheManager.set(
        data_type="queue_metrics",
        resource_id=cache_key,
        value=metrics,
        ttl=CacheManager.ttl_extended  # 24 horas
    )
    
    # Verificar umbrales para alertas
    if metric_type == "queue_length" and value > 100:
        await trigger_queue_alert(queue_name, "high_queue_length", value)
    
    if metric_type == "processing_time" and value > 30:  # segundos
        await trigger_queue_alert(queue_name, "high_processing_time", value)
```

### 9.7 Recomendaciones para Producción

1. **Dimensionamiento adecuado**:
   - Ajustar número de workers según capacidad de APIs externas
   - Monitorizar constantemente longitud de colas
   - Escalar horizontalmente workers según demanda

2. **Manejo de Fallos**:
   - Implementar circuit breakers para APIs externas
   - Configurar dead-letter queues para tareas fallidas
   - Establecer políticas de retry con backoff exponencial

3. **Optimización de Recursos**:
   - Configurar prefetch_count según características de cada cola
   - Usar acknowledge tardío (ack_late) para tareas críticas
   - Implementar timeouts adaptivos según carga del sistema
