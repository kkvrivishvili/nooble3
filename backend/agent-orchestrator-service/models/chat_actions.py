"""
Acciones del dominio Chat.
"""

from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import Field
from models.base_actions import BaseAction

class ChatSendMessageAction(BaseAction):
    """Acción para enviar mensaje de chat."""
    
    action_type: str = Field("chat.send_message", description="Tipo de acción")
    
    # Datos específicos del chat
    agent_id: UUID = Field(..., description="ID del agente a usar")
    session_id: str = Field(..., description="ID de la sesión")
    message: str = Field(..., description="Mensaje del usuario")
    message_type: str = Field("text", description="Tipo de mensaje")
    
    # Información del usuario (sin autenticación)
    user_info: Dict[str, Any] = Field(default_factory=dict, description="Info del usuario")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contexto adicional")
    
    # Configuración
    timeout: Optional[int] = Field(None, description="Timeout personalizado")
    priority: str = Field("normal", description="Prioridad de la tarea")
    
    def get_domain(self) -> str:
        return "chat"
    
    def get_action_name(self) -> str:
        return "send_message"
    
    def get_priority(self) -> str:
        return self.priority

class ChatGetStatusAction(BaseAction):
    """Acción para obtener estado de una tarea."""
    
    action_type: str = Field("chat.get_status", description="Tipo de acción")
    
    # Datos específicos
    task_id: str = Field(..., description="ID de la tarea a consultar")
    
    def get_domain(self) -> str:
        return "chat"
    
    def get_action_name(self) -> str:
        return "get_status"

class ChatCancelTaskAction(BaseAction):
    """Acción para cancelar una tarea."""
    
    action_type: str = Field("chat.cancel_task", description="Tipo de acción")
    
    # Datos específicos
    task_id: str = Field(..., description="ID de la tarea a cancelar")
    
    def get_domain(self) -> str:
        return "chat"
    
    def get_action_name(self) -> str:
        return "cancel_task"