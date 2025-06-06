"""
Acciones del dominio WebSocket.
"""

from typing import Dict, Any, Optional, List
from pydantic import Field
from models.base_actions import BaseAction

class WebSocketSendAction(BaseAction):
    """Acción para enviar mensaje via WebSocket a una sesión específica."""
    
    action_type: str = Field("websocket.send_message", description="Tipo de acción")
    
    # Datos específicos
    session_id: str = Field(..., description="ID de la sesión")
    message_data: Dict[str, Any] = Field(..., description="Datos del mensaje")
    message_type: str = Field("agent_response", description="Tipo de mensaje WS")
    
    def get_domain(self) -> str:
        return "websocket"
    
    def get_action_name(self) -> str:
        return "send_message"
    
    def get_priority(self) -> str:
        return "high"  # WebSocket siempre alta prioridad

class WebSocketBroadcastAction(BaseAction):
    """Acción para broadcast a todas las conexiones de un tenant."""
    
    action_type: str = Field("websocket.broadcast", description="Tipo de acción")
    
    # Datos específicos
    message_data: Dict[str, Any] = Field(..., description="Datos del mensaje")
    message_type: str = Field("broadcast", description="Tipo de mensaje WS")
    target_sessions: Optional[List[str]] = Field(None, description="Sesiones específicas")
    
    def get_domain(self) -> str:
        return "websocket"
    
    def get_action_name(self) -> str:
        return "broadcast"
    
    def get_priority(self) -> str:
        return "high"
