"""
Modelos para WebSocket (sin cambios del original).
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class WebSocketMessageType(str, Enum):
    """Tipos de mensajes WebSocket."""
    AGENT_RESPONSE = "agent_response"
    TASK_UPDATE = "task_update"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    CONNECTION_ACK = "connection_ack"
    TYPING_INDICATOR = "typing_indicator"

class ConnectionStatus(str, Enum):
    """Estados de conexión WebSocket."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"

class WebSocketMessage(BaseModel):
    """Mensaje estándar para WebSocket."""
    
    type: WebSocketMessageType = Field(..., description="Tipo de mensaje")
    data: Dict[str, Any] = Field(..., description="Datos del mensaje")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp del mensaje")
    
    # Identificadores
    task_id: Optional[str] = Field(None, description="ID de la tarea relacionada")
    session_id: Optional[str] = Field(None, description="ID de la sesión")
    tenant_id: Optional[str] = Field(None, description="ID del tenant")
    
    # Metadatos
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales")

class ConnectionInfo(BaseModel):
    """Información de una conexión WebSocket."""
    
    connection_id: str = Field(..., description="ID único de la conexión")
    tenant_id: str = Field(..., description="ID del tenant")
    session_id: str = Field(..., description="ID de la sesión")
    user_id: Optional[str] = Field(None, description="ID del usuario")
    
    # Estado de la conexión
    status: ConnectionStatus = Field(ConnectionStatus.CONNECTED, description="Estado de la conexión")
    connected_at: datetime = Field(default_factory=datetime.now, description="Timestamp de conexión")
    last_ping: Optional[datetime] = Field(None, description="Último ping recibido")
    
    # Metadatos
    user_agent: Optional[str] = Field(None, description="User agent del cliente")
    ip_address: Optional[str] = Field(None, description="IP del cliente")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadatos adicionales")