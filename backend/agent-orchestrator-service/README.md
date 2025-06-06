# Agent Orchestrator Service - Domain Actions

## Descripción
Servicio de orquestación refactorizado con Domain Actions que actúa como API Gateway, gestiona tareas asíncronas y mantiene conexiones WebSocket para respuestas en tiempo real.

## Arquitectura Domain Actions

### Estructura de Colas Estandarizada
```
Formato: {domain}:{tenant_id}:{action}:{priority}

Ejemplos:
- agent:tenant-123:execute:normal          # Para Agent Execution Service
- orchestrator:tenant-123:websocket_send:high  # Callbacks internos
- workflow:tenant-123:start:normal         # Futuro Workflow Service
- tool:tenant-123:invoke:normal           # Futuro Tool Registry
```

### Acciones del Dominio Chat
- `chat.send_message` - Enviar mensaje al agente
- `chat.get_status` - Consultar estado de tarea
- `chat.cancel_task` - Cancelar tarea en cola

### Acciones del Dominio WebSocket
- `websocket.send_message` - Enviar a sesión específica
- `websocket.broadcast` - Broadcast a tenant

## Funcionalidades

### Sin Autenticación JWT
- Acceso público a los chats
- Contabilización de tokens por `tenant_id` del agente propietario
- El `agent_id` determina el tenant responsable de los costos

### Domain Action Processor
- Procesamiento centralizado de todas las acciones
- Registry automático de handlers
- Validación automática con Pydantic
- Error handling consistente

### Queue Manager Estandarizado
- Formato de colas compatible con futuros servicios
- Prioridades: high, normal, low
- Status tracking automático
- Cleanup automático con TTL

## APIs

### Chat (Domain Actions)
```bash
# Enviar mensaje
POST /api/v1/chat/message
{
  "tenant_id": "tenant-123",
  "agent_id": "agent-uuid",
  "session_id": "session-456",
  "message": "Hola",
  "user_info": {"user_id": "user-789"},
  "priority": "normal"
}

# Consultar estado (sin JWT)
GET /api/v1/chat/status/task-123?tenant_id=tenant-123

# Cancelar tarea (sin JWT)
POST /api/v1/chat/cancel/task-123?tenant_id=tenant-123
```

### WebSocket (Acceso Público)
```bash
# Conexión sin autenticación
WS /ws/{tenant_id}/{session_id}?user_id=user-789
```

## Flujo de Procesamiento

```
1. Frontend → POST /chat/message → ChatSendMessageAction
2. ChatActionHandler → Enqueue agent:tenant:execute:normal
3. Agent Execution Service procesa
4. Callback → orchestrator:tenant:websocket_send:high
5. ActionWorker → WebSocketSendAction
6. WebSocketActionHandler → Cliente via WebSocket
```

## Configuración

### Variables de Entorno
```bash
ORCHESTRATOR_REDIS_URL=redis://localhost:6379
ORCHESTRATOR_MAX_WEBSOCKET_CONNECTIONS=1000
ORCHESTRATOR_TASK_TIMEOUT_SECONDS=300
ORCHESTRATOR_WORKER_SLEEP_SECONDS=1.0
```

### Ejecución
```bash
cd agent-orchestrator-service
pip install -r requirements.txt
python main.py  # Puerto 8008
```

## Ventajas Domain Actions

### Para Testing
- **Handlers independientes**: Test unitario por acción
- **Mock mínimo**: Solo el handler específico
- **Validación automática**: Pydantic valida inputs
- **Error isolation**: Fallos no afectan otros handlers

### Para Escalabilidad
- **Nuevas acciones**: Solo crear Action + Handler
- **Servicios futuros**: Mismo formato de colas
- **Registry automático**: Auto-discovery de handlers
- **Separation of concerns**: Cada handler una responsabilidad

### Para Mantenimiento
- **Código organizado**: Por dominio y acción
- **Debugging fácil**: Error específico por handler
- **Modificaciones**: Sin impactar otros componentes
- **Reutilización**: Misma acción desde múltiples fuentes

## Preparación para Futuros Servicios

### Workflow Service
```
workflow:tenant-123:start:normal
workflow:tenant-123:step:high
workflow:tenant-123:decision:normal
```

### Tool Registry Service
```
tool:tenant-123:list:low
tool:tenant-123:invoke:normal
tool:tenant-123:validate:high
```

### Conversation Service
```
conversation:tenant-123:create:normal
conversation:tenant-123:append:high
```

La estructura está preparada para añadir estos servicios sin refactorización del Orchestrator.Error obteniendo estado de tarea: {str(e)}")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=time.time() - start_time
            )
    
    async def _handle_cancel_task(self, action: ChatCancelTaskAction) -> ActionResult:
        """Maneja cancelación de tarea."""
        start_time = time.time()
        
        try:
            # Obtener estado actual
            status_info = await self.queue_manager.get_action_status(
                action_id=action.task_id,
                tenant_id=action.tenant_id
            )
            
            if not status_info:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error={
                        "type": "TaskNotFound",
                        "message": "Tarea no encontrada"
                    },
                    execution_time=time.time() - start_time
                )
            
            current_status = status_info.get("status")
            
            # Solo se puede cancelar si está en cola
            if current_status not in ["queued", "pending"]:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error={
                        "type": "CannotCancel",
                        "message": f"No se puede cancelar tarea en estado: {current_status}"
                    },
                    execution_time=time.time() - start_time
                )
            
            # Actualizar estado a cancelado
            await self.queue_manager.set_action_status(
                action_id=action.task_id,
                tenant_id=action.tenant_id,
                status="cancelled",
                metadata={
                    "cancelled_at": time.time(),
                    "cancelled_by": action.user_id or "system"
                }
            )
            
            return ActionResult(
                action_id=action.action_id,
                success=True,
                result={
                    "task_id": action.task_id,
                    "status": "cancelled",
                    "message": "Tarea cancelada exitosamente"
                },
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error cancelando tarea: {str(e)}")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=time.time() - start_time
            )
    
    def _estimate_processing_time(self) -> str:
        """Estima tiempo de procesamiento (simplificado)."""
        # Estimación basada en 3-4 respuestas por segundo de Groq
        avg_time = 8  # segundos promedio
        return f"{avg_time} segundos"
    
    def can_handle(self, action_type: str) -> bool:
        """Verifica si puede manejar este tipo de acción."""
        return action_type in self.get_supported_actions()
    
    def get_supported_actions(self) -> List[str]:
        """Retorna lista de acciones soportadas."""
        return [
            "chat.send_message",
            "chat.get_status", 
            "chat.cancel_task"
        ]
