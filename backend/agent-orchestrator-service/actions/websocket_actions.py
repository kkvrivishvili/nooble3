"""
Handler para acciones de WebSocket.
"""

import logging
import time
from typing import Dict, Any, List

from models.base_actions import ActionHandler, ActionResult
from models.websocket_actions import WebSocketSendAction, WebSocketBroadcastAction
from models.websocket_models import WebSocketMessage, WebSocketMessageType
from services.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)

class WebSocketActionHandler(ActionHandler):
    """Handler para acciones de WebSocket."""
    
    def __init__(self):
        self.websocket_manager = WebSocketManager()
    
    async def execute(self, action) -> ActionResult:
        """Ejecuta acción de WebSocket según el tipo."""
        
        if isinstance(action, WebSocketSendAction):
            return await self._handle_send_message(action)
        elif isinstance(action, WebSocketBroadcastAction):
            return await self._handle_broadcast(action)
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
    
    async def _handle_send_message(self, action: WebSocketSendAction) -> ActionResult:
        """Maneja envío de mensaje WebSocket a sesión específica."""
        start_time = time.time()
        
        try:
            # Crear mensaje WebSocket
            ws_message = WebSocketMessage(
                type=WebSocketMessageType(action.message_type),
                data=action.message_data,
                task_id=action.metadata.get("task_id"),
                session_id=action.session_id,
                tenant_id=action.tenant_id,
                metadata=action.metadata
            )
            
            # Enviar a sesión específica
            sent_count = await self.websocket_manager.send_to_session(
                tenant_id=action.tenant_id,
                session_id=action.session_id,
                message=ws_message
            )
            
            if sent_count > 0:
                logger.info(f"Mensaje WebSocket enviado a {sent_count} conexiones - Sesión: {action.session_id}")
            else:
                logger.warning(f"No hay conexiones WebSocket activas para sesión: {action.session_id}")
            
            return ActionResult(
                action_id=action.action_id,
                success=True,
                result={
                    "sent_to_connections": sent_count,
                    "session_id": action.session_id,
                    "message_type": action.message_type
                },
                execution_time=time.time() - start_time,
                metadata={
                    "websocket_delivery": sent_count > 0
                }
            )
            
        except Exception as e:
            logger.error(f"Error enviando mensaje WebSocket: {str(e)}")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=time.time() - start_time
            )
    
    async def _handle_broadcast(self, action: WebSocketBroadcastAction) -> ActionResult:
        """Maneja broadcast WebSocket a múltiples conexiones."""
        start_time = time.time()
        
        try:
            # Crear mensaje WebSocket
            ws_message = WebSocketMessage(
                type=WebSocketMessageType(action.message_type),
                data=action.message_data,
                tenant_id=action.tenant_id,
                metadata=action.metadata
            )
            
            sent_count = 0
            
            if action.target_sessions:
                # Enviar a sesiones específicas
                for session_id in action.target_sessions:
                    count = await self.websocket_manager.send_to_session(
                        tenant_id=action.tenant_id,
                        session_id=session_id,
                        message=ws_message
                    )
                    sent_count += count
            else:
                # Broadcast a todo el tenant
                sent_count = await self.websocket_manager.send_to_tenant(
                    tenant_id=action.tenant_id,
                    message=ws_message
                )
            
            logger.info(f"Broadcast WebSocket enviado a {sent_count} conexiones - Tenant: {action.tenant_id}")
            
            return ActionResult(
                action_id=action.action_id,
                success=True,
                result={
                    "sent_to_connections": sent_count,
                    "target_sessions": action.target_sessions,
                    "message_type": action.message_type
                },
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error en broadcast WebSocket: {str(e)}")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=time.time() - start_time
            )
    
    def can_handle(self, action_type: str) -> bool:
        """Verifica si puede manejar este tipo de acción."""
        return action_type in self.get_supported_actions()
    
    def get_supported_actions(self) -> List[str]:
        """Retorna lista de acciones soportadas."""
        return [
            "websocket.send_message",
            "websocket.broadcast"
        ]