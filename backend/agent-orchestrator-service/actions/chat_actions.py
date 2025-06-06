"""
Handler para acciones de chat.
"""

import logging
import time
from typing import Dict, Any, List
from uuid import uuid4

from models.base_actions import ActionHandler, ActionResult
from models.chat_actions import ChatSendMessageAction, ChatGetStatusAction, ChatCancelTaskAction
from domain.queue_manager import DomainQueueManager
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ChatActionHandler(ActionHandler):
    """Handler para acciones de chat."""
    
    def __init__(self):
        self.queue_manager = DomainQueueManager()
    
    async def execute(self, action) -> ActionResult:
        """Ejecuta acción de chat según el tipo."""
        
        if isinstance(action, ChatSendMessageAction):
            return await self._handle_send_message(action)
        elif isinstance(action, ChatGetStatusAction):
            return await self._handle_get_status(action)
        elif isinstance(action, ChatCancelTaskAction):
            return await self._handle_cancel_task(action)
        else:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": "UnsupportedAction",
                    "message": f"Acción no soportada: {action.action_type}"
                },
                execution_time=0.0
            )
    
    async def _handle_send_message(self, action: ChatSendMessageAction) -> ActionResult:
        """Maneja envío de mensaje de chat."""
        start_time = time.time()
        
        try:
            # Validar mensaje no vacío
            if not action.message.strip():
                raise ValueError("El mensaje no puede estar vacío")
            
            # Crear acción para Agent Execution Service
            # Reutilizamos la misma acción pero la enviamos al dominio 'agent'
            agent_action = ChatSendMessageAction(
                action_id=action.action_id,  # Mantener mismo ID para tracking
                tenant_id=action.tenant_id,
                agent_id=action.agent_id,
                session_id=action.session_id,
                message=action.message,
                message_type=action.message_type,
                user_info=action.user_info,
                context=action.context,
                timeout=action.timeout,
                priority=action.priority,
                metadata={
                    **action.metadata,
                    "callback_domain": "orchestrator",
                    "callback_action": "websocket_send",
                    "source": "chat_api"
                }
            )
            
            # Encolar en el dominio 'agent' para Agent Execution Service
            success = await self.queue_manager.enqueue_action(
                action=agent_action,
                target_domain="agent"  # Enviar al Agent Execution Service
            )
            
            if not success:
                raise Exception("Error encolando tarea en Agent Execution Service")
            
            # Establecer estado inicial
            await self.queue_manager.set_action_status(
                action_id=action.action_id,
                tenant_id=action.tenant_id,
                status="queued",
                metadata={
                    "agent_id": str(action.agent_id),
                    "session_id": action.session_id,
                    "enqueued_at": time.time()
                }
            )
            
            # Estimar tiempo de procesamiento (simplificado)
            estimated_time = self._estimate_processing_time()
            
            return ActionResult(
                action_id=action.action_id,
                success=True,
                result={
                    "task_id": action.action_id,
                    "status": "queued",
                    "session_id": action.session_id,
                    "agent_id": str(action.agent_id),
                    "estimated_time": estimated_time,
                    "message": "Mensaje enviado y en cola de procesamiento"
                },
                execution_time=time.time() - start_time,
                metadata={
                    "action_type": "chat.send_message",
                    "enqueued_to": "agent"
                }
            )
            
        except Exception as e:
            logger.error(f"Error procesando mensaje de chat: {str(e)}")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=time.time() - start_time
            )
    
    async def _handle_get_status(self, action: ChatGetStatusAction) -> ActionResult:
        """Maneja consulta de estado de tarea."""
        start_time = time.time()
        
        try:
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
            
            return ActionResult(
                action_id=action.action_id,
                success=True,
                result={
                    "task_id": action.task_id,
                    "status": status_info["status"],
                    "updated_at": status_info["updated_at"],
                    "metadata": status_info.get("metadata", {})
                },
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            logger