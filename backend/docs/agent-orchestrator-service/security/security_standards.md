# Estándares de Seguridad - Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Estándares de Seguridad - Agent Orchestrator Service](#estándares-de-seguridad---agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Autenticación y Autorización](#2-autenticación-y-autorización)
  - [3. Seguridad de Datos](#3-seguridad-de-datos)
  - [4. Seguridad en Comunicaciones](#4-seguridad-en-comunicaciones)
  - [5. Protección contra Vulnerabilidades](#5-protección-contra-vulnerabilidades)
  - [6. Auditoría](#6-auditoría)
  - [7. Implementación](#7-implementación)

## 1. Introducción

Este documento define los estándares de seguridad para el Agent Orchestrator Service, componente crítico que coordina la comunicación entre todos los servicios de la plataforma Nooble. La posición central del orquestador requiere medidas de seguridad estrictas para proteger datos sensibles, prevenir accesos no autorizados y garantizar la integridad de las comunicaciones.

## 2. Autenticación y Autorización

### 2.1 Autenticación de Clientes

El Orchestrator Service implementa múltiples niveles de autenticación:

1. **Autenticación JWT (Clientes)**:
   - Tokens JWT firmados por el Auth Service
   - Verificación de firma, expiración y audiencia
   - Rotación de tokens cada 15 minutos con refresh tokens

2. **Autenticación de Servicios Internos**:
   - Certificados mutuos TLS para servicios de Nivel 2
   - Tokens de servicio con permisos específicos
   - Verificación de IP contra rangos permitidos

### 2.2 Modelo de Autorización

El modelo de autorización sigue estos principios:

- **RBAC (Role-Based Access Control)**:
  - Roles: `admin`, `operator`, `reader`
  - Permisos granulares por recurso y operación

- **Autorización Multi-tenant**:
  - Estricto aislamiento entre tenants
  - Validación de tenant_id en cada operación

```python
# middleware/auth.py
from fastapi import Header, HTTPException, Depends
from services.auth import verify_token, get_permissions

async def verify_tenant_access(
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Header(...),
):
    """Verifica que el token tenga acceso al tenant especificado"""
    token = authorization.replace("Bearer ", "")
    claims = await verify_token(token)
    
    # Verificar acceso al tenant
    if "admin" not in claims.get("roles", []) and tenant_id not in claims.get("tenants", []):
        raise HTTPException(status_code=403, detail="Acceso denegado a este tenant")
    
    return claims

async def require_permission(permission: str):
    """Middleware para requerir un permiso específico"""
    def dependency(claims: dict = Depends(verify_tenant_access)):
        user_permissions = get_permissions(claims)
        if permission not in user_permissions:
            raise HTTPException(status_code=403, detail=f"Permiso requerido: {permission}")
        return claims
    
    return dependency
```

### 2.3 Gestión de Tokens

- **Almacenamiento Seguro**:
  - Tokens nunca almacenados en logs
  - Tokens efímeros en memoria o Redis con TTL

- **Validación Completa**:
  - Verificación de firma, emisor, audiencia
  - Verificación de tiempo de expiración
  - Lista negra de tokens revocados

## 3. Seguridad de Datos

### 3.1 Cifrado en Reposo

- **Datos Persistentes**:
  - Cifrado AES-256 para datos sensibles en Redis
  - Rotación de claves de cifrado cada 90 días

- **Metadatos Sensibles**:
  - PII (Personal Identifiable Information) cifrado
  - Claves almacenadas en HashiCorp Vault

### 3.2 Sanitización de Datos

- **Validación de Inputs**:
  - Validación de esquema con Pydantic
  - Sanitización de strings para evitar XSS
  - Validación de límites y tamaños

```python
# models/session.py
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional
import re

class SessionCreate(BaseModel):
    tenant_id: str
    user_id: str
    agent_id: str
    initial_context: Optional[Dict[str, Any]] = None
    
    @validator("tenant_id", "user_id", "agent_id")
    def sanitize_ids(cls, v):
        if not re.match(r'^[a-zA-Z0-9_\-\.]{3,64}$', v):
            raise ValueError("ID contiene caracteres no permitidos o longitud inválida")
        return v
```

### 3.3 Políticas de Retención

- **Datos de Sesión**:
  - TTL configurable por tenant (default: 30 días)
  - Eliminación automática de datos expirados

- **Datos de Auditoría**:
  - Retención de 90 días para logs operativos
  - Retención de 365 días para eventos de seguridad

## 4. Seguridad en Comunicaciones

### 4.1 TLS Mutuo

Todo el tráfico entre el Agent Orchestrator y servicios de Nivel 2 usa TLS mutuo:

1. **Certificados**:
   - Generados y firmados por PKI interna
   - Rotación cada 90 días
   - Mínimo TLS 1.2, preferido TLS 1.3

2. **Validación**:
   - Verificación completa de cadena de certificados
   - Comprobación de revocaciones (OCSP)

### 4.2 Securización de WebSockets

- **Autenticación**:
  - Token inicial de handshake
  - Verificación continua en mensajes
  
- **Protección de Datos**:
  - Siempre sobre WSS (WebSocket Secure)
  - Mensajes sensibles cifrados end-to-end

```python
# websocket/security.py
async def authenticate_websocket(websocket: WebSocket):
    """Autentica una conexión WebSocket"""
    try:
        # Obtener token del query param
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="No token provided")
            return False
        
        # Verificar token
        claims = await verify_token(token)
        if not claims:
            await websocket.close(code=4003, reason="Invalid token")
            return False
        
        # Almacenar claims en el estado del websocket
        websocket.state.claims = claims
        websocket.state.tenant_id = claims.get("tenant_id")
        return True
        
    except Exception as e:
        logger.error(f"Error en autenticación WebSocket: {str(e)}")
        await websocket.close(code=4500, reason="Authentication error")
        return False
```

### 4.3 Protección de APIs

- **Rate Limiting**:
  - Por IP, tenant y endpoint
  - Límites configurables por nivel de cliente
  - Penalización por exceso de intentos

```python
# middleware/rate_limit.py
from fastapi import Request, HTTPException
import redis
import time

async def rate_limit_middleware(request: Request, call_next):
    tenant_id = request.headers.get("X-Tenant-ID", "anonymous")
    client_ip = request.client.host
    path = request.url.path
    
    # Clave única para rate limiting
    rate_key = f"rate:orchestrator:{path}:{tenant_id}:{client_ip}"
    
    # Verificar límite
    current = await redis_client.get(rate_key)
    limit = get_rate_limit(tenant_id, path)
    
    if current and int(current) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests")
        
    # Incrementar contador
    pipe = redis_client.pipeline()
    pipe.incr(rate_key)
    pipe.expire(rate_key, 60)  # 1 minuto de ventana
    await pipe.execute()
    
    return await call_next(request)
```

## 5. Protección contra Vulnerabilidades

### 5.1 Protección contra Inyecciones

- **Prevención SQL Injection**:
  - ORM con parámetros parametrizados
  - Validación de inputs antes de consultas

- **Prevención NoSQL Injection**:
  - Validación de operadores y filtros
  - Sanitización de consultas a Redis/MongoDB

### 5.2 Protección DoS/DDoS

- **Circuit Breakers**:
  - Para limitar cascada de fallos
  - Timeouts adaptativos por servicio

- **Monitoreo de Patrones**:
  - Detección de patrones anómalos
  - Bloqueo automático de IPs maliciosas

### 5.3 Escaneo y Testing

- **CI/CD Pipeline**:
  - Análisis estático (SonarQube)
  - Escaneo de dependencias (OWASP)
  - Tests de penetración automatizados

## 6. Auditoría

### 6.1 Eventos Auditables

El Agent Orchestrator registra estos eventos de seguridad:

1. **Eventos de Autenticación**:
   - Login/logout exitosos y fallidos
   - Cambios de permisos

2. **Eventos de Recursos**:
   - Creación/eliminación de sesiones
   - Acceso a recursos sensibles

3. **Eventos de Administración**:
   - Cambios en configuración
   - Actualizaciones de políticas

```python
# services/audit.py
async def audit_log(
    event_type: str,
    tenant_id: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    status: str,
    details: dict = None
):
    """Registra un evento de auditoría"""
    audit_event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "status": status,
        "details": details or {},
        "source_ip": get_client_ip(),
        "service": "agent-orchestrator"
    }
    
    # Registrar en log seguro
    security_logger.info("Audit event", extra=audit_event)
    
    # Almacenar en cola de auditoría para procesamiento asíncrono
    await redis_client.rpush("orchestrator:audit:events", json.dumps(audit_event))
```

### 6.2 Proceso de Revisión

- **Alertas**:
  - Detección de patrones sospechosos
  - Alertas automatizadas para revisión

- **Reportes**:
  - Reportes diarios de actividad
  - Dashboard de seguridad en tiempo real

## 7. Implementación

### 7.1 Middleware de Seguridad

```python
# main.py
from fastapi import FastAPI
from middleware.auth import auth_middleware
from middleware.rate_limit import rate_limit_middleware
from middleware.security import security_headers_middleware

app = FastAPI()

# Configuración de middleware de seguridad
app.middleware("http")(security_headers_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)
```

### 7.2 Seguridad en Headers HTTP

```python
# middleware/security.py
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Añadir headers de seguridad
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    return response
```

### 7.3 Manejo de Fallos de Seguridad

```python
# middleware/auth.py
async def auth_middleware(request: Request, call_next):
    try:
        # Procesar request
        return await call_next(request)
    except SecurityException as e:
        # Auditar fallo de seguridad
        await audit_log(
            event_type="security_violation",
            tenant_id=e.tenant_id,
            user_id=e.user_id,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            action=e.action,
            status="blocked",
            details={"reason": str(e), "code": e.code}
        )
        
        # Responder con error
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": True,
                "code": e.code,
                "message": "Security violation detected"
            }
        )
```
