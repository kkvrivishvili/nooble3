# Seguridad - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Seguridad - Agent Management Service](#seguridad---agent-management-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Autenticación y Autorización](#2-autenticación-y-autorización)
    - [2.1 Modelo de Autenticación](#21-modelo-de-autenticación)
    - [2.2 Gestión de Tokens](#22-gestión-de-tokens)
    - [2.3 Niveles de Autorización](#23-niveles-de-autorización)
  - [3. Aislamiento Multi-Tenant](#3-aislamiento-multi-tenant)
  - [4. Protección de Datos](#4-protección-de-datos)
  - [5. Rate Limiting y Protección contra Abusos](#5-rate-limiting-y-protección-contra-abusos)
  - [6. Auditoría y Logs de Seguridad](#6-auditoría-y-logs-de-seguridad)
  - [7. Registro de Cambios](#7-registro-de-cambios)

## 1. Visión General

Este documento detalla las medidas de seguridad implementadas en el Agent Management Service para proteger los datos, garantizar el acceso apropiado y proporcionar un entorno seguro y aislado para cada tenant.

## 2. Autenticación y Autorización

### 2.1 Modelo de Autenticación

El Agent Management Service utiliza autenticación basada en JWT (JSON Web Tokens) con las siguientes características:

- Los tokens son emitidos por el Identity Service
- Cada token contiene: `sub` (sujeto), `tenant_id`, `roles`, `scope`, `exp` (expiración)
- Se admiten dos tipos de tokens:
  - **User Tokens**: Para usuarios humanos interactuando a través del frontend
  - **Service Tokens**: Para comunicación entre servicios como el mostrado en la notificación WebSocket

**Validación de token para WebSockets**:

```python
# Del ejemplo en el README - websocket/notifier.py
async def connect(self):
    """Establece conexión con orquestrador con reconexión automática"""
    while True:
        try:
            logger.info(f"Conectando a {self.orchestrator_url}")
            async with websockets.connect(self.orchestrator_url) as ws:
                # Autenticarse como servicio usando token JWT
                await ws.send(json.dumps({
                    "service_token": self.service_token,
                    "service_name": self.service_name
                }))
                
                # Esperar confirmación
                auth_response = await ws.recv()
                auth_data = json.loads(auth_response)
                if auth_data.get("status") != "authenticated":
                    logger.error(f"Fallo en la autenticación WebSocket: {auth_data.get('error')}")
                    raise Exception("Authentication failed")
                
                logger.info(f"Conexión WebSocket establecida para {self.service_name}")
                # Conexión establecida con seguridad garantizada
                self.reconnect_delay = 1.0  # reset backoff
                self.websocket = ws
                self.connected = True
                
                # Registrar canales específicos de tenant
                # Solo se recibirán notificaciones de los tenants asignados
                await self._register_tenant_channels()
```

### 2.2 Gestión de Tokens

- **Tiempo de vida**: Tokens de usuario: 1 hora, Tokens de servicio: 24 horas
- **Rotación**: Los tokens se rotan automáticamente cada 45 minutos (usuarios) o 12 horas (servicios)
- **Revocación**: Lista negra centralizada en Redis para tokens revocados
- **Refresh**: Mecanismo de refresh token para renovar sesiones sin requerir nueva autenticación

### 2.3 Niveles de Autorización

| Rol | Permisos | Descripción |
|-----|----------|-------------|
| `viewer` | Solo lectura | Puede ver agentes pero no modificarlos |
| `editor` | Lectura/Escritura | Puede crear y modificar agentes |
| `admin` | Control total | Puede publicar, eliminar y gestionar todos los agentes |
| `service` | API completa | Acceso programático completo (solo para servicios internos) |

**Ejemplo de verificación de permisos**:

```python
@router.post("/agents", status_code=201)
async def create_agent(
    agent: AgentCreate,
    token: TokenClaims = Depends(get_token_claims)
):
    # Verificar permisos
    if not has_permission(token, "agents:create"):
        raise HTTPException(
            status_code=403,
            detail={"error": {
                "code": "AMS-204",
                "message": "Insufficient permissions to create agents"
            }}
        )
    
    # Continuar con la creación del agente
    return await agent_service.create_agent(agent, token.tenant_id)
```

## 3. Aislamiento Multi-Tenant

El servicio implementa un estricto aislamiento por tenant mediante:

- **Segmentación por tenant en colas**: Siguiendo el formato `agent-management.{tipo}.{tenant_id}`
- **Filtrado por tenant en base de datos**: Todas las consultas incluyen `tenant_id`
- **Notificación por tenant**: Canales específicos por tenant para WebSocket
- **Separación lógica**: Datos de cada tenant se mantienen separados en todas las etapas

**Ejemplo de notificación a canal específico de tenant con seguridad reforzada**:

```python
# Del ejemplo en el README - websocket/notifier.py (versión actualizada)
async def notify_agent_change(task_id, tenant_id, agent_data, event_type, global_task_id=None):
    """Notifica sobre cambios en la configuración de agentes con seguridad por tenant"""
    try:
        # Verificar validez del tenant_id antes de enviar notificaciones
        if not await self._validate_tenant_access(tenant_id):
            logger.error(f"Intento de notificación para tenant no autorizado: {tenant_id}")
            return
            
        # Obtener conexión autenticada al orquestador usando pool de conexiones
        ws = await self._get_authenticated_connection()
        
        # Crear firma de mensaje para verificar integridad
        timestamp = datetime.utcnow().isoformat()
        signature = self._generate_message_signature(tenant_id, event_type, timestamp)
        
        notification = {
            "event": event_type,  # agent_created, agent_updated, agent_deleted
            "service": "agent-management",
            "task_id": task_id,
            "global_task_id": global_task_id,
            "tenant_id": tenant_id,
            "timestamp": timestamp,
            "signature": signature,
            "data": {
                "agent_id": agent_data["agent_id"],
                "agent_name": agent_data["agent_name"],
                "version": agent_data.get("version", "1.0")
            }
        }
        
        # Envío con cifrado punto a punto
        await ws.send(json.dumps(notification))
        
        # También publicar en Redis PubSub como respaldo
        await self.redis_pubsub.publish(
            f"agent-management.notifications.{tenant_id}",
            json.dumps(notification)
        )
        
        # Registrar notificación para auditoría
        await self.audit_logger.log_notification(notification)
        
    except Exception as e:
        logger.error(f"Error al notificar cambio de agente: {e}")
        # Añadir a cola de reintentos para garantizar entrega
        await self.retry_queue.add({
            "type": "agent_notification",
            "payload": {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "event_type": event_type,
                "data": agent_data
            },
            "attempts": 0,
            "max_attempts": 3
        })
```

## 4. Protección de Datos

- **Datos en tránsito**: TLS 1.3 para todas las comunicaciones
- **Datos en reposo**: Cifrado de base de datos con AES-256
- **Secretos**: Almacenados en AWS Secrets Manager / HashiCorp Vault
- **Sanitización**: Limpieza de datos sensibles en logs y reportes de error
- **Retención**: Política de retención de datos configurable por tenant

## 5. Rate Limiting y Protección contra Abusos

El servicio implementa límites de tasa basados en:

- **IP de origen**: Prevención de ataques DDoS
- **Token/Usuario**: Limitar solicitudes por usuario
- **Tenant**: Límites por tenant según su tier

**Configuración de rate limits**:

| Tier | Solicitudes API (RPM) | Creación de Agentes (por día) | Actualización de Agentes (por hora) |
|------|----------------------|-------------------------------|-----------------------------------|
| Free | 60 | 5 | 20 |
| Pro | 300 | 20 | 100 |
| Enterprise | 1000 | Ilimitado | Ilimitado |

## 6. Auditoría y Logs de Seguridad

Se registran los siguientes eventos de seguridad:

- Inicio/cierre de sesión exitoso
- Intentos de autenticación fallidos
- Cambios en roles o permisos
- Creación/eliminación de agentes
- Accesos a datos entre tenants (bloqueados)
- Violaciones de rate limit
- Cambios en la configuración del servicio

**Formato de log de auditoría**:

```json
{
  "timestamp": "2025-06-03T14:25:36.123Z",
  "event_type": "agent.create",
  "level": "INFO",
  "tenant_id": "tenant-abc",
  "user_id": "user-123",
  "source_ip": "192.168.1.1",
  "resource": "agent-456",
  "action": "CREATE",
  "status": "SUCCESS",
  "request_id": "req-789",
  "details": {
    "agent_name": "New Agent",
    "agent_type": "customer_support"
  }
}
```

## 7. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
