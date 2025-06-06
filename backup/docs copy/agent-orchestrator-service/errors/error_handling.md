# Manejo de Errores - Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Manejo de Errores - Agent Orchestrator Service](#manejo-de-errores---agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Jerarquía de Excepciones](#2-jerarquía-de-excepciones)
  - [3. Códigos de Error](#3-códigos-de-error)
  - [4. Estrategias de Manejo](#4-estrategias-de-manejo)
  - [5. Ejemplos de Implementación](#5-ejemplos-de-implementación)

## 1. Introducción

Este documento define las estrategias y prácticas para el manejo de errores en el Agent Orchestrator Service. Como servicio central de orquestación, es crítico implementar un manejo de errores robusto que permita detectar, reportar y recuperarse de fallos en cualquier punto del proceso.

## 2. Jerarquía de Excepciones

```
OrchestratorBaseError
├── ConfigurationError
├── ServiceConnectionError
│   ├── ServiceTimeoutError
│   └── ServiceUnavailableError
├── SessionError
│   ├── SessionNotFoundError
│   └── SessionValidationError
├── OrchestrationError
│   ├── PlanExecutionError
│   └── ServiceDependencyError
├── AuthenticationError
└── TenantError
```

### Implementación Base

```python
# errors/exceptions.py

class OrchestratorBaseError(Exception):
    """Excepción base para todos los errores del Orchestrator Service"""
    code = "ORCH-000"
    http_status = 500
    
    def __init__(self, message=None, details=None):
        self.message = message or "Error en el servicio de orquestación"
        self.details = details or {}
        super().__init__(self.message)

class ConfigurationError(OrchestratorBaseError):
    """Error en la configuración del servicio"""
    code = "ORCH-001"
    http_status = 500

class ServiceConnectionError(OrchestratorBaseError):
    """Error de conexión con servicios dependientes"""
    code = "ORCH-100"
    http_status = 503

class ServiceTimeoutError(ServiceConnectionError):
    """Timeout en la comunicación con un servicio"""
    code = "ORCH-101"
    http_status = 504

class SessionError(OrchestratorBaseError):
    """Error relacionado con las sesiones"""
    code = "ORCH-200"
    http_status = 400

class SessionNotFoundError(SessionError):
    """Sesión no encontrada"""
    code = "ORCH-201"
    http_status = 404
```

## 3. Códigos de Error

Los códigos de error siguen la estructura `ORCH-XXX` donde:

- **000-099**: Errores internos y de configuración
- **100-199**: Errores de comunicación con servicios
- **200-299**: Errores relacionados con sesiones
- **300-399**: Errores de orquestación y ejecución
- **400-499**: Errores de autenticación y autorización
- **500-599**: Errores relacionados con tenants

### Tabla de Errores Comunes

| Código | Descripción | HTTP Status | Acción Recomendada |
|--------|------------|-------------|-------------------|
| ORCH-001 | Error de configuración | 500 | Verificar variables de entorno y archivos de configuración |
| ORCH-100 | Error de conexión a servicio | 503 | Verificar disponibilidad del servicio y reintentar |
| ORCH-101 | Timeout de servicio | 504 | Aumentar timeout o verificar carga del servicio |
| ORCH-201 | Sesión no encontrada | 404 | Crear nueva sesión |
| ORCH-301 | Error en ejecución de plan | 500 | Revisar logs para diagnóstico detallado |
| ORCH-401 | Token inválido | 401 | Renovar token de autenticación |

## 4. Estrategias de Manejo

### 4.1 Circuit Breaker

Implementar el patrón Circuit Breaker para prevenir fallos en cascada:

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def call_service(service_name, endpoint, data):
    """Llamada a servicio con circuit breaker"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{get_service_url(service_name)}/{endpoint}",
                json=data,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise ServiceTimeoutError(f"Timeout al comunicarse con {service_name}")
    except httpx.HTTPStatusError as e:
        raise ServiceConnectionError(f"Error HTTP {e.response.status_code} al comunicarse con {service_name}")
```

### 4.2 Retry con Backoff Exponencial

Para errores transitorios:

```python
import asyncio
import random

async def retry_with_backoff(func, max_attempts=3, initial_delay=1):
    """Ejecuta una función con reintentos y backoff exponencial"""
    attempt = 0
    while attempt < max_attempts:
        try:
            return await func()
        except (ServiceTimeoutError, ServiceUnavailableError) as e:
            attempt += 1
            if attempt >= max_attempts:
                raise
            
            delay = initial_delay * (2 ** (attempt - 1)) * (0.5 + random.random())
            logger.warning(f"Reintento {attempt}/{max_attempts} tras {delay:.2f}s debido a: {str(e)}")
            await asyncio.sleep(delay)
```

### 4.3 Graceful Degradation

Proporcionar funcionalidad reducida en caso de fallos críticos:

```python
async def get_agent_config(tenant_id, agent_id):
    """Obtiene configuración de agente con fallback"""
    try:
        return await agent_management_client.get_agent_config(tenant_id, agent_id)
    except ServiceUnavailableError:
        logger.error("Agent Management Service no disponible, usando configuración por defecto")
        return get_default_agent_config(agent_id)
```

## 5. Ejemplos de Implementación

### 5.1 Middleware de Manejo de Excepciones FastAPI

```python
# middleware/error_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse
from errors.exceptions import OrchestratorBaseError

async def error_handler_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except OrchestratorBaseError as e:
        logger.error(f"Error controlado: {e.code} - {e.message}", exc_info=True)
        return JSONResponse(
            status_code=e.http_status,
            content={
                "error": True,
                "code": e.code,
                "message": e.message,
                "details": e.details,
                "request_id": request.state.request_id
            }
        )
    except Exception as e:
        logger.critical(f"Error no controlado: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "code": "ORCH-999",
                "message": "Error interno del servidor",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )
```

### 5.2 Gestión de Errores en Procesamiento Asíncrono

```python
async def process_orchestration_task(task_id, tenant_id):
    """Procesa una tarea de orquestación de forma asíncrona"""
    try:
        # Lógica de procesamiento...
        task = await task_repository.get_task(tenant_id, task_id)
        plan = create_orchestration_plan(task)
        result = await execute_plan(plan)
        
        await task_repository.update_task(
            tenant_id, 
            task_id, 
            status="completed", 
            result=result
        )
        
        await notify_completion(tenant_id, task_id, result)
        
    except OrchestrationError as e:
        logger.error(f"Error de orquestación: {e.code} - {e.message}")
        await task_repository.update_task(
            tenant_id, 
            task_id, 
            status="failed", 
            error={
                "code": e.code,
                "message": e.message,
                "details": e.details
            }
        )
        await notify_failure(tenant_id, task_id, e)
        
    except Exception as e:
        logger.critical(f"Error no controlado: {str(e)}", exc_info=True)
        await task_repository.update_task(
            tenant_id, 
            task_id, 
            status="failed", 
            error={
                "code": "ORCH-999",
                "message": "Error interno no esperado",
                "details": {"error": str(e)}
            }
        )
        await notify_failure(tenant_id, task_id, e)
```
