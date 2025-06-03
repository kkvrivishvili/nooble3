# Fase 7: Sistema de Colas de Trabajo con Celery, RabbitMQ e Integración con call_service

## Visión General

Esta fase implementa un sistema de colas de trabajo asíncrono utilizando Celery y RabbitMQ para optimizar las comunicaciones entre el frontend y backend, así como entre los servicios más demandados. Este enfoque reemplaza las conexiones directas HTTP por un sistema de trabajos encolados con WebSockets para notificaciones en tiempo real, aprovechando la función estandarizada `call_service` para todas las comunicaciones HTTP entre servicios.

## Índice

1. [Arquitectura del Sistema](#1-arquitectura-del-sistema)
2. [Integrando call_service en el Sistema de Colas](#2-integrando-call_service-en-el-sistema-de-colas)
3. [Implementación del Núcleo del Sistema](#3-implementación-del-núcleo-del-sistema)
4. [WebSocket Manager](#4-websocket-manager)
5. [Implementación en Agent Service](#5-implementación-en-agent-service)
6. [Cliente JavaScript](#6-cliente-javascript)
7. [Ejemplos de Uso](#7-ejemplos-de-uso)
8. [Estrategia de Migración](#8-estrategia-de-migración)

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

## 2. Integrando call_service en el Sistema de Colas

### 2.1 Descripción de call_service

La función `call_service` es el método centralizado y estandarizado para toda comunicación HTTP entre servicios en nuestra plataforma, proporcionando:

- **Propagación automática de contexto**: Tenant ID, Agent ID, Conversation ID y Collection ID
- **Reintentos con backoff exponencial**: Manejo inteligente de fallos temporales
- **Circuit breaker**: Prevención de cascadas de fallos
- **Timeouts específicos** según el tipo de operación
- **Soporte para caché**: Caché de respuestas configurable
- **Manejo estandarizado de errores**: Errores tipo y mensajes consistentes
- **Tracing y observabilidad**: Logs unificados con metadatos de contexto

### 2.2 Tipos de Operación para WorkQueueService

Para aprovechar al máximo las capacidades de `call_service`, el sistema de colas define tipos específicos de operaciones con sus timeouts y TTLs recomendados:

| Tipo de Operación | Descripción | Timeout | TTL Recomendado |
|-------------------|-------------|---------|----------------|
| `queue_job_create` | Creación de nuevo trabajo | 15.0s | 300 (5 min) |
| `queue_job_status` | Consulta de estado de trabajo | 5.0s | 60 (1 min) |
| `queue_job_update` | Actualización de estado | 10.0s | 0 (no cachear) |
| `queue_job_list` | Listado de trabajos | 20.0s | 300 (5 min) |
| `queue_job_cancel` | Cancelación de trabajo | 10.0s | 0 (no cachear) |
| `queue_notification` | Notificaciones de eventos | 5.0s | 0 (no cachear) |
| `queue_metrics` | Consulta de métricas | 15.0s | 300 (5 min) |
| `agent_execution_queue` | Encolar ejecución de agente | 30.0s | 0 (no cachear) |
| `websocket_handshake` | Operaciones WebSocket | 5.0s | 0 (no cachear) |
| `batch_job` | Operaciones por lotes | 120.0s | 1800 (30 min) |

### 2.3 Beneficios de Integración

1. **Mayor resiliencia**:
   - Reintentos automáticos en caso de fallos temporales
   - Prevención de cascadas de fallos mediante circuit breaker
   - Timeouts apropiados para diferentes tipos de operaciones

2. **Mejor observabilidad**:
   - Logs estructurados consistentes
   - Propagación de contexto para correlacionar operaciones
   - Formato de errores estandarizado

3. **Reducción de código duplicado**:
   - Eliminación de implementaciones personalizadas de HTTP
   - Manejo centralizado de reintentos y timeouts
   - Gestión unificada de errores

4. **Integración con sistema de caché**:
   - Aprovechamiento de cache-aside para resultados frecuentes
   - TTLs apropiados para diferentes tipos de datos

## 3. Implementación del Núcleo del Sistema

### 3.1 Configuración de Celery con RabbitMQ

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

### 3.2 Decorador para Preservar Contexto

```python
def create_context_task(queue_name):
    """
    Decorador para crear tareas Celery que preservan el contexto multitenancy.
    
    Maneja la propagación completa del contexto entre servicios y asegura el
    correcto seguimiento de trabajos. Integra con call_service para comunicación
    estándar entre servicios.
    
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
```

### 3.3 WorkQueueService con call_service

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
from ..utils.http import call_service
from ..utils.metrics import track_performance_metric
from ..config import get_settings

logger = logging.getLogger(__name__)

class WorkQueueServiceHealth:
    """
    Componente para verificar la salud de servicios relacionados con WorkQueueService.
    Implementa cache de estado y circuit breaker usando call_service.
    """
    
    _service_status_cache = {}  # Cache de estado de servicios
    
    @staticmethod
    async def check_service_health(service_url, service_name):
        """Verifica la salud de un servicio usando call_service con circuit breaker"""
        # Evitar verificaciones demasiado frecuentes (cada 30 segundos máximo)
        cache_key = f"health:{service_name}"
        cached_status = WorkQueueServiceHealth._service_status_cache.get(cache_key)
        
        if cached_status and (time.time() - cached_status["timestamp"] < 30):
            return cached_status["healthy"]
            
        try:
            result = await call_service(
                url=f"{service_url}/health",
                data={},
                method="GET",
                operation_type="health_check",
                max_retries=1,  # Solo un intento para health checks
                custom_timeout=2.0
            )
            
            is_healthy = result.get("success", False)
            WorkQueueServiceHealth._service_status_cache[cache_key] = {
                "healthy": is_healthy,
                "timestamp": time.time()
            }
            return is_healthy
            
        except Exception as e:
            logger.warning(f"Error verificando salud de {service_name}: {str(e)}")
            WorkQueueServiceHealth._service_status_cache[cache_key] = {
                "healthy": False,
                "timestamp": time.time()
            }
            return False

class WorkQueueService:
    """
    Gestiona la integración entre Celery, caché y WebSockets.
    Utiliza call_service para comunicación estándar entre servicios.
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
        
        # Registrar trabajo en servicio de historial usando call_service
        try:
            history_result = await call_service(
                url=f"{self.settings.history_service_url}/internal/jobs/register",
                data={
                    "job_id": job_id,
                    "job_type": job_type,
                    "params": params,
                    "status": "queued"
                },
                tenant_id=tenant_id,
                agent_id=ctx.get_agent_id() if ctx else None,
                conversation_id=ctx.get_conversation_id() if ctx else None,
                collection_id=ctx.get_collection_id() if ctx else None,
                operation_type="queue_job_create"
            )
            
            if not history_result.get("success", False):
                logger.warning(
                    f"Error registrando trabajo en historial: {history_result.get('error')}"
                )
        except Exception as e:
            # No fallar si el servicio de historial no está disponible
            logger.warning(f"Error registrando trabajo en historial: {str(e)}")
        
        # Registrar en métricas
        await track_performance_metric(
            metric_type="work_queue_job_registered",
            value=1,
            tenant_id=tenant_id,
            metadata={"job_type": job_type}
        )
        
        return {
            "job_id": job_id,
            "status": "queued"
        }
        
    async def update_job_status(self, job_id, status, result=None, error=None):
        """
        Actualiza el estado de un trabajo y notifica vía WebSocket.
        Utiliza call_service para comunicación estandarizada con otros servicios.
        
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
        
        # Actualizar estado local
        job_metadata["status"] = status
        job_metadata["updated_at"] = datetime.now().isoformat()
        
        if result:
            job_metadata["result"] = result
        
        if error:
            job_metadata["error"] = error
        
        # 1. Actualizar en caché local
        await CacheManager.set(
            data_type="job_metadata",
            resource_id=job_id,
            value=job_metadata,
            tenant_id=tenant_id,
            ttl=3600
        )
        
        # 2. Comunicar actualización al servicio de historial
        # Usando call_service para comunicación consistente
        history_result = await call_service(
            url=f"{self.settings.history_service_url}/internal/jobs/update",
            data={
                "job_id": job_id,
                "status": status,
                "result": result,
                "error": error,
                "updated_at": job_metadata["updated_at"]
            },
            tenant_id=tenant_id,
            operation_type="queue_job_update",
            use_cache=False  # No cachear actualizaciones
        )
        
        if not history_result.get("success", False):
            logger.warning(f"Error actualizando historial para job_id={job_id}: {history_result.get('error')}")
        
        # 3. Si es completado, guardar en caché por job_type y params
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
        
        # 4. Notificar vía WebSocket si está disponible
        if self.websocket_manager:
            await self._notify_status_update(job_id, status, result, error)
        
        # 5. Registrar en métricas
        await track_performance_metric(
            metric_type=f"work_queue_job_{status}",
            value=1,
            tenant_id=tenant_id,
            metadata={"job_type": job_type}
        )
        
        return True

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
```

## 4. WebSocket Manager

### 4.1 Implementación del Gestor de WebSockets

```python
# common/websocket/manager.py
import logging
import asyncio
from typing import Dict, Set, Any, Optional
import json
from ..utils.http import call_service

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Gestiona conexiones WebSocket y distribución de mensajes.
    Integra call_service para notificaciones a servicios externos.
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
        
        # Notificar registro de conexión con call_service (opcional)
        try:
            from ..config import get_settings
            settings = get_settings()
            
            await call_service(
                url=f"{settings.metrics_service_url}/internal/websocket/connection",
                data={
                    "client_id": client_id,
                    "connection_type": "register",
                    "timestamp": asyncio.get_event_loop().time()
                },
                tenant_id=tenant_id,
                operation_type="websocket_handshake",
                use_cache=False
            )
        except Exception as e:
            # No fallar si no se puede notificar
            logger.debug(f"No se pudo notificar conexión WebSocket: {str(e)}")
    
    async def unregister_connection(self, client_id):
        """
        Elimina una conexión WebSocket.
        
        Args:
            client_id: ID del cliente
        """
        tenant_id = None
        if client_id in self.connections:
            tenant_id = self.connections[client_id].get("tenant_id")
            del self.connections[client_id]
        
        # Limpiar suscripciones
        for job_id, subscribers in list(self.job_subscribers.items()):
            if client_id in subscribers:
                subscribers.remove(client_id)
                
                # Si no quedan suscriptores, eliminar entrada
                if not subscribers:
                    del self.job_subscribers[job_id]
        
        logger.info(f"Conexión WebSocket eliminada: client_id={client_id}")
        
        # Notificar desconexion con call_service (opcional)
        if tenant_id:
            try:
                from ..config import get_settings
                settings = get_settings()
                
                await call_service(
                    url=f"{settings.metrics_service_url}/internal/websocket/connection",
                    data={
                        "client_id": client_id,
                        "connection_type": "unregister",
                        "timestamp": asyncio.get_event_loop().time()
                    },
                    tenant_id=tenant_id,
                    operation_type="websocket_handshake",
                    use_cache=False
                )
            except Exception as e:
                # No fallar si no se puede notificar
                logger.debug(f"No se pudo notificar desconexión WebSocket: {str(e)}")
    
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

## 5. Implementación en Agent Service

### 5.1 Tareas de Celery para Agentes

```python
# agent-service/tasks/agent_tasks.py
from common.queue.celery_app import create_context_task, celery_app
from common.queue.work_queue import WorkQueueService
from common.websocket.manager import WebSocketManager
from common.utils.http import call_service
from common.config import get_settings
import asyncio

# Crear instancia del servicio de colas
websocket_manager = WebSocketManager()
work_queue = WorkQueueService(websocket_manager)
settings = get_settings()

@create_context_task("agent_tasks")
def execute_agent(agent_id, input_text, collection_id=None, use_auto_federation=False, ctx=None):
    """
    Tarea de ejecución de agente usando call_service para comunicación estandarizada.
    
    Args:
        agent_id: ID del agente
        input_text: Texto de entrada
        collection_id: ID de colección opcional
        use_auto_federation: Si usar federación automática
        ctx: Contexto
        
    Returns:
        Resultado de la ejecución del agente
    """
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
        
        # Obtener tenant_id del contexto
        tenant_id = ctx.get_tenant_id() if ctx else None
        conversation_id = ctx.get_conversation_id() if ctx else None
        
        # Ejecutar agente usando call_service para llamada estandarizada
        response_future = asyncio.run_coroutine_threadsafe(
            call_service(
                url=f"{settings.agent_service_url}/internal/execute",
                data={
                    "agent_id": agent_id,
                    "input_text": input_text,
                    "collection_id": collection_id,
                    "use_auto_federation": use_auto_federation
                },
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                operation_type="agent_execution"
            ),
            loop
        )
        
        # Obtener resultado
        response = response_future.result()
        
        if response.get("success", False):
            result = response.get("data", {})
            
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
        else:
            # Falló la ejecución
            error_msg = response.get("error", {}).get("message", "Error desconocido")
            
            # Actualizar estado a "failed"
            asyncio.run_coroutine_threadsafe(
                work_queue.update_job_status(
                    job_id=celery_app.current_task.request.id,
                    status="failed",
                    error=error_msg
                ),
                loop
            ).result()
            
            raise Exception(f"Error en ejecución de agente: {error_msg}")
            
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
# agent-service/routes/websocket.py
from fastapi import APIRouter, WebSocket, Depends, Body, HTTPException
from fastapi.responses import JSONResponse
from common.context import Context, with_context
from common.queue.work_queue import WorkQueueService
from common.websocket.manager import WebSocketManager
from common.errors.handlers import handle_errors
from common.utils.http import call_service
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
    Utiliza el sistema de colas para procesamiento asíncrono.
    
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
```

## 6. Cliente JavaScript

```javascript
// frontend/src/services/JobClient.js
class JobClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.websockets = {};
    this.callbacks = {};
    this.reconnectTimers = {};
    this.reconnectAttempts = {};
  }

  /**
   * Ejecuta un agente de forma asíncrona a través del sistema de colas
   * @param {string} agentId - ID del agente
   * @param {string} input - Texto de entrada para el agente
   * @param {object} options - Opciones adicionales
   * @returns {Promise<object>} - Información del trabajo creado
   */
  async executeAgent(agentId, input, options = {}) {
    const url = `${this.baseUrl}/jobs/agent/${agentId}/execute`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': options.tenantId || localStorage.getItem('tenant_id')
      },
      body: JSON.stringify({
        input,
        collection_id: options.collectionId,
        use_auto_federation: options.useAutoFederation || false
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Error ejecutando agente');
    }

    const jobInfo = await response.json();
    
    // Suscribirse automáticamente a actualizaciones si hay callback
    if (options.onUpdate) {
      this.subscribeToJob(jobInfo.job_id, options.onUpdate);
    }
    
    return jobInfo;
  }

  /**
   * Obtiene el estado actual de un trabajo
   * @param {string} jobId - ID del trabajo
   * @returns {Promise<object>} - Estado actual del trabajo
   */
  async getJobStatus(jobId) {
    const url = `${this.baseUrl}/jobs/${jobId}/status`;
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': localStorage.getItem('tenant_id')
      }
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Error obteniendo estado del trabajo');
    }

    return await response.json();
  }

  /**
   * Suscribe a actualizaciones de un trabajo vía WebSocket
   * @param {string} jobId - ID del trabajo
   * @param {function} callback - Función a llamar cuando hay actualizaciones
   */
  subscribeToJob(jobId, callback) {
    // Guardar callback
    this.callbacks[jobId] = callback;
    
    // Iniciar conexión WebSocket
    const wsUrl = `${this.baseUrl.replace('http', 'ws')}/ws/jobs/${jobId}`;
    
    try {
      const socket = new WebSocket(wsUrl);
      
      socket.onopen = () => {
        console.log(`WebSocket conectado para job_id=${jobId}`);
        // Resetear intentos de reconexión al conectar exitosamente
        this.reconnectAttempts[jobId] = 0;
      };
      
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Llamar al callback con los datos recibidos
          if (this.callbacks[jobId]) {
            this.callbacks[jobId](data);
          }
          
          // Si es un mensaje de finalización, cerrar conexión
          if (data.type === 'job_completed' || data.type === 'job_error') {
            this.unsubscribeFromJob(jobId);
          }
        } catch (e) {
          console.error('Error procesando mensaje WebSocket:', e);
        }
      };
      
      socket.onclose = () => {
        console.log(`WebSocket desconectado para job_id=${jobId}`);
        // Intentar reconexión si no fue cerrado intencionalmente
        if (this.callbacks[jobId]) {
          this._scheduleReconnect(jobId);
        }
      };
      
      socket.onerror = (error) => {
        console.error(`Error en WebSocket para job_id=${jobId}:`, error);
      };
      
      // Guardar referencia al socket
      this.websockets[jobId] = socket;
      
    } catch (e) {
      console.error(`Error creando WebSocket para job_id=${jobId}:`, e);
      this._scheduleReconnect(jobId);
    }
  }

  /**
   * Cancela la suscripción a actualizaciones de un trabajo
   * @param {string} jobId - ID del trabajo
   */
  unsubscribeFromJob(jobId) {
    // Cancelar cualquier temporizador de reconexión
    if (this.reconnectTimers[jobId]) {
      clearTimeout(this.reconnectTimers[jobId]);
      delete this.reconnectTimers[jobId];
    }
    
    // Cerrar socket si existe
    if (this.websockets[jobId]) {
      if (this.websockets[jobId].readyState === WebSocket.OPEN) {
        this.websockets[jobId].close();
      }
      delete this.websockets[jobId];
    }
    
    // Eliminar callback
    delete this.callbacks[jobId];
    delete this.reconnectAttempts[jobId];
  }

  /**
   * Programa un reintento de conexión con backoff exponencial
   * @param {string} jobId - ID del trabajo
   * @private
   */
  _scheduleReconnect(jobId) {
    if (!this.reconnectAttempts[jobId]) {
      this.reconnectAttempts[jobId] = 0;
    }
    
    // Incrementar contador de intentos
    this.reconnectAttempts[jobId]++;
    
    // Backoff exponencial con máximo de 30 segundos
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts[jobId], 30000);
    
    // Máximo 5 intentos
    if (this.reconnectAttempts[jobId] <= 5) {
      console.log(`Reintentando conexión para job_id=${jobId} en ${delay}ms`);
      
      this.reconnectTimers[jobId] = setTimeout(() => {
        if (this.callbacks[jobId]) {
          this.subscribeToJob(jobId, this.callbacks[jobId]);
        }
      }, delay);
    } else {
      console.error(`Máximo de intentos alcanzado para job_id=${jobId}`);
      delete this.callbacks[jobId];
    }
  }
}

export default JobClient;
```

## 7. Ejemplos de Uso

### 7.1 Ejemplo de Ejecución Asíncrona de Agente

```javascript
// frontend/src/components/AgentChat.js
import React, { useState } from 'react';
import JobClient from '../services/JobClient';

const jobClient = new JobClient('http://localhost:8000/api');

function AgentChat({ agentId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(null);

  const sendMessage = async () => {
    if (!input.trim()) return;
    
    // Añadir mensaje del usuario
    const userMessage = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setProgress('Enviando solicitud...');
    
    try {
      // Ejecutar agente vía trabajo asíncrono
      const jobInfo = await jobClient.executeAgent(agentId, input, {
        onUpdate: handleJobUpdate
      });
      
      setProgress(`Trabajo encolado con ID: ${jobInfo.job_id}`);
      
    } catch (error) {
      console.error('Error ejecutando agente:', error);
      setMessages(prev => [...prev, {
        sender: 'system',
        text: `Error: ${error.message || 'Error desconocido'}`
      }]);
      setIsLoading(false);
      setProgress(null);
    }
  };
  
  const handleJobUpdate = (data) => {
    console.log('Actualización de trabajo:', data);
    
    switch (data.type) {
      case 'status_update':
        setProgress(`Estado: ${data.status}`);
        break;
        
      case 'job_completed':
        // Añadir respuesta del agente
        const agentResponse = {
          sender: 'agent',
          text: data.result.answer,
          metadata: data.result.metadata
        };
        setMessages(prev => [...prev, agentResponse]);
        setIsLoading(false);
        setProgress(null);
        break;
        
      case 'job_error':
        setMessages(prev => [...prev, {
          sender: 'system',
          text: `Error: ${data.error}`
        }]);
        setIsLoading(false);
        setProgress(null);
        break;
    }
  };

  return (
    <div className="agent-chat">
      <div className="message-container">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.sender}`}>
            {msg.text}
          </div>
        ))}
        
        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <div className="progress-text">{progress}</div>
          </div>
        )}
      </div>
      
      <div className="input-container">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={isLoading}
          placeholder="Escribe un mensaje..."
          onKeyPress={e => e.key === 'Enter' && sendMessage()}
        />
        <button onClick={sendMessage} disabled={isLoading || !input.trim()}>
          Enviar
        </button>
      </div>
    </div>
  );
}

export default AgentChat;
```

### 7.2 Ejemplo de Integración en Backend con call_service

```python
# Ejemplo de integración con otros servicios usando call_service
async def query_and_execute_agent(query_text, tenant_id, ctx=None):
    """Realiza una consulta RAG y ejecuta un agente con el resultado"""
    from common.config import get_settings
    from common.utils.http import call_service
    
    settings = get_settings()
    
    # 1. Consulta al servicio de queries usando call_service
    query_result = await call_service(
        url=f"{settings.query_service_url}/internal/query",
        data={
            "query": query_text,
            "top_k": 5
        },
        tenant_id=tenant_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        conversation_id=ctx.get_conversation_id() if ctx else None,
        operation_type="rag_query",
        use_cache=True,  # Usar caché para queries recurrentes
        cache_ttl=3600   # 1 hora
    )
    
    if not query_result.get("success", False):
        logger.error(f"Error en consulta RAG: {query_result.get('error')}")
        return None
    
    # 2. Obtener resultados
    documents = query_result.get("data", {}).get("documents", [])
    context = "\n\n".join([doc.get("content", "") for doc in documents])
    
    # 3. Ejecutar agente con el contexto obtenido
    agent_result = await call_service(
        url=f"{settings.agent_service_url}/internal/enqueue_agent",
        data={
            "agent_id": ctx.get_agent_id(),
            "input_text": f"Pregunta: {query_text}\n\nContexto: {context}",
            "priority": "high"
        },
        tenant_id=tenant_id,
        agent_id=ctx.get_agent_id() if ctx else None,
        conversation_id=ctx.get_conversation_id() if ctx else None,
        operation_type="agent_execution_queue"
    )
    
    if not agent_result.get("success", False):
        logger.error(f"Error encolando agente: {agent_result.get('error')}")
        return None
        
    return agent_result.get("data")
```

## 8. Estrategia de Migración

### 8.1 Enfoque de Implementación Progresiva

Para facilitar la migración del sistema actual al nuevo sistema que utiliza `call_service` de manera consistente, se recomienda un enfoque por fases:

1. **Fase 1: Refactorización de comunicaciones HTTP directas**
   - Reemplazar todas las llamadas HTTP directas por `call_service`
   - Añadir tipos de operación específicos en `common/utils/http.py`
   - Mantener compatibilidad con código existente

2. **Fase 2: Reforzar mecanismos de resiliencia**
   - Implementar health checks y circuit breaker
   - Añadir reintentos inteligentes
   - Mejorar manejo de errores

3. **Fase 3: Optimizar sistema de caché**
   - Integrar caché de `call_service` con CacheManager
   - Implementar estrategias de invalidación
   - Definir TTLs apropiados para diferentes tipos de datos

4. **Fase 4: Mejorar observabilidad**
   - Añadir logs estructurados y trazas
   - Implementar métricas para monitoreo
   - Configurar dashboards de observabilidad

### 8.2 Plan de Pruebas

Se recomienda el siguiente plan de pruebas para validar la migración:

1. **Pruebas unitarias** para `call_service` y `WorkQueueService`
2. **Pruebas de integración** entre servicios usando el nuevo enfoque
3. **Pruebas de carga** para verificar rendimiento bajo presión
4. **Pruebas de resiliencia** con fallas simuladas para validar circuit breaker y reintentos
5. **Pruebas de validación de caché** para verificar hit rates y TTLs

### 8.3 Checklist de Migración

✅ Actualizar `get_timeout_for_operation` con nuevos tipos para WorkQueueService  
✅ Refactorizar `WorkQueueService` para usar `call_service`  
✅ Actualizar `WebSocketManager` para notificaciones con context propagation  
✅ Modificar tareas Celery para aprovechar `call_service`  
✅ Implementar mejoras en la gestión de caché  
✅ Actualizar endpoints REST para interactuar con el sistema de colas  
✅ Mejorar cliente JavaScript con soporte para WebSockets y reconexión  
✅ Actualizar documentación con ejemplos de uso del nuevo sistema
