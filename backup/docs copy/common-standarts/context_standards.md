# Estándares de Gestión de Contexto

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Arquitectura de Contexto](#2-arquitectura-de-contexto)
3. [Contexto de Solicitud](#3-contexto-de-solicitud)
4. [Contexto de Tenant](#4-contexto-de-tenant)
5. [Contexto de Usuario](#5-contexto-de-usuario)
6. [Propagación de Contexto](#6-propagación-de-contexto)
7. [Middleware y Dependencias](#7-middleware-y-dependencias)
8. [Implementación en Servicios](#8-implementación-en-servicios)

## 1. Introducción

Este documento establece los estándares para la gestión de contexto en todos los microservicios de la plataforma Nooble AI. El objetivo es garantizar un manejo uniforme de la información contextual (tenant, usuario, sesión) a lo largo de toda la plataforma, permitiendo un comportamiento consistente, seguro y trazable.

### 1.1 Principios Generales

- **Consistencia**: Manejo uniforme del contexto en todos los servicios
- **Aislamiento**: Garantizar la separación estricta entre tenants
- **Trazabilidad**: Mantener información para seguimiento de operaciones
- **Eficiencia**: Acceso optimizado al contexto en cualquier punto
- **Seguridad**: Validación adecuada de contexto para prevenir accesos no autorizados

## 2. Arquitectura de Contexto

### 2.1 Componentes del Módulo

```
common/context/
├── __init__.py       # Exporta funciones principales
├── vars.py           # Variables contextuales y accesores
├── middleware.py     # Middleware para extracción y validación
└── models.py         # Modelos de datos de contexto
```

### 2.2 Componentes Clave

- **RequestContext**: Datos asociados a una solicitud específica
- **TenantContext**: Información del tenant actual
- **UserContext**: Información del usuario actual
- **SessionContext**: Datos de la sesión actual
- **ContextMiddleware**: Middleware para procesamiento de contexto

## 3. Contexto de Solicitud

### 3.1 Estructura Estándar

Cada solicitud debe asociarse con un `RequestContext` que incluye:

```python
class RequestContext:
    """Contexto asociado a una solicitud."""
    
    def __init__(self):
        self.request_id = str(uuid.uuid4())
        self.timestamp = datetime.now(UTC)
        self.correlation_id = None
        self.source = None
        self.tenant = None
        self.user = None
        self.session = None
        self.trace_info = {}
```

### 3.2 Campos Obligatorios

| Campo | Tipo | Descripción |
|-------|------|-------------|
| request_id | uuid | Identificador único de la solicitud |
| timestamp | datetime | Momento de creación del contexto |
| correlation_id | uuid | ID para correlacionar solicitudes relacionadas |
| tenant | TenantContext | Contexto del tenant (obligatorio) |

### 3.3 Campos Opcionales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| user | UserContext | Información del usuario actual |
| session | SessionContext | Información de la sesión actual |
| trace_info | dict | Información adicional para trazabilidad |
| source | str | Origen de la solicitud (app, api, system) |

## 4. Contexto de Tenant

### 4.1 Estructura Estándar

Información específica del tenant:

```python
class TenantContext:
    """Contexto asociado a un tenant."""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.plan = None
        self.settings = {}
        self.features = {}
        self.limits = {}
```

### 4.2 Campos Obligatorios

| Campo | Tipo | Descripción |
|-------|------|-------------|
| tenant_id | uuid | Identificador único del tenant |

### 4.3 Campos Opcionales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| plan | str | Plan de suscripción del tenant |
| settings | dict | Configuraciones específicas del tenant |
| features | dict | Características habilitadas para el tenant |
| limits | dict | Límites de uso específicos del tenant |

## 5. Contexto de Usuario

### 5.1 Estructura Estándar

Información específica del usuario:

```python
class UserContext:
    """Contexto asociado a un usuario."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.roles = []
        self.permissions = []
        self.preferences = {}
```

### 5.2 Campos Obligatorios

| Campo | Tipo | Descripción |
|-------|------|-------------|
| user_id | uuid | Identificador único del usuario |
| roles | list | Roles asignados al usuario |

### 5.3 Campos Opcionales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| permissions | list | Permisos específicos del usuario |
| preferences | dict | Preferencias del usuario |
| metadata | dict | Metadatos adicionales del usuario |

## 6. Propagación de Contexto

### 6.1 Entre Servicios Síncronos (HTTP)

Para propagar el contexto entre servicios vía HTTP:

1. **Cabeceras Estándar**:
   - `X-Request-ID`: ID único de la solicitud
   - `X-Correlation-ID`: ID para correlacionar solicitudes
   - `X-Tenant-ID`: ID del tenant
   - `X-User-ID`: ID del usuario (opcional)
   - `X-Session-ID`: ID de la sesión (opcional)

2. **Middleware HTTP**:
   ```python
   async def context_propagation_middleware(request: Request, call_next):
       # Extraer y validar IDs de las cabeceras
       request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
       correlation_id = request.headers.get("X-Correlation-ID")
       tenant_id = request.headers.get("X-Tenant-ID")
       
       # Establecer el contexto
       with context.set_request_context(request_id=request_id):
           with context.set_correlation_id(correlation_id):
               with context.set_tenant_id(tenant_id):
                   # Continuar con el procesamiento
                   response = await call_next(request)
                   
                   # Añadir cabeceras de contexto a la respuesta
                   response.headers["X-Request-ID"] = request_id
                   return response
   ```

### 6.2 Entre Servicios Asíncronos (Colas/Eventos)

Para propagar contexto en mensajes asíncronos:

1. **Encabezado de Mensaje Estándar**:
   ```json
   {
     "message_id": "msg-uuid",
     "tenant_id": "tenant-123",
     "correlation_id": "corr-uuid", 
     "timestamp": "2025-06-03T12:34:56Z",
     "source": "service-name",
     "context": {
       "user_id": "user-456",
       "session_id": "session-789"
     },
     "payload": {
       // Contenido específico del mensaje
     }
   }
   ```

2. **Reconstrucción de Contexto**:
   ```python
   async def process_message(message: dict):
       tenant_id = message.get("tenant_id")
       correlation_id = message.get("correlation_id")
       
       # Reconstruir contexto a partir del mensaje
       with context.set_tenant_id(tenant_id):
           with context.set_correlation_id(correlation_id):
               # Procesar el mensaje
               await process_message_payload(message["payload"])
   ```

## 7. Middleware y Dependencias

### 7.1 Middleware Principal

```python
class ContextMiddleware:
    """Middleware para establecer el contexto de la solicitud."""
    
    async def __call__(self, request: Request, call_next: Callable):
        # Extraer información de las cabeceras y tokens JWT
        tenant_id = self._extract_tenant_id(request)
        user_data = self._extract_user_data(request)
        
        # Validar tenant_id
        if not tenant_id:
            raise MissingTenantError("Se requiere un ID de tenant válido")
        
        # Establecer el contexto para la solicitud
        with context.set_request_context():
            with context.set_tenant_id(tenant_id):
                if user_data:
                    with context.set_user_context(user_data):
                        response = await call_next(request)
                else:
                    response = await call_next(request)
                
                return response
```

### 7.2 Dependencias FastAPI

```python
def get_tenant_id() -> str:
    """Dependencia FastAPI para obtener el tenant_id actual."""
    tenant_id = context.get_tenant_id()
    if not tenant_id:
        raise MissingTenantError("No se encontró tenant_id en el contexto")
    return tenant_id

def get_user_id() -> str:
    """Dependencia FastAPI para obtener el user_id actual."""
    user_id = context.get_user_id()
    if not user_id:
        raise AuthenticationError("No se encontró user_id en el contexto")
    return user_id
```

## 8. Implementación en Servicios

### 8.1 Configuración en FastAPI

Cada servicio debe configurar el middleware de contexto:

```python
from fastapi import FastAPI
from common.context.middleware import ContextMiddleware

app = FastAPI()

# Registrar middleware de contexto
app.add_middleware(ContextMiddleware)
```

### 8.2 Uso del Contexto en Controladores

```python
from fastapi import APIRouter, Depends
from common.context import get_tenant_id, get_user_id

router = APIRouter()

@router.post("/resources")
async def create_resource(
    data: ResourceCreate,
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id)
):
    """Crea un nuevo recurso usando el contexto actual."""
    resource = await resource_service.create(
        tenant_id=tenant_id,
        created_by=user_id,
        data=data
    )
    return resource
```

### 8.3 Acceso al Contexto en Lógica de Negocio

```python
from common.context import get_context, get_tenant_id

async def process_business_logic():
    """Accede al contexto desde la lógica de negocio."""
    # Obtener el contexto actual completo
    current_context = get_context()
    
    # O acceder a elementos específicos
    tenant_id = get_tenant_id()
    
    logger.info(
        "Procesando lógica de negocio", 
        extra={
            "tenant_id": tenant_id,
            "request_id": current_context.request_id
        }
    )
    
    # Lógica específica usando el contexto...
```

### 8.4 Variables Contextuales para Trazabilidad

```python
import logging
from common.context import get_context

def setup_contextual_logger():
    """Configura el logger para incluir variables contextuales."""
    logger = logging.getLogger("app")
    
    class ContextFilter(logging.Filter):
        def filter(self, record):
            context = get_context()
            if context:
                record.tenant_id = context.tenant.tenant_id if context.tenant else "unknown"
                record.request_id = context.request_id
                record.correlation_id = context.correlation_id
            return True
    
    logger.addFilter(ContextFilter())
    return logger
```
