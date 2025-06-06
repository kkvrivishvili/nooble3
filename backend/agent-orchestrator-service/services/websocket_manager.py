"""
Gestor de conexiones WebSocket (sin cambios del original).
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4
from fastapi import WebSocket

from models.websocket_models import (
    WebSocketMessage, WebSocketMessageType, 
    ConnectionInfo, ConnectionStatus
)
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class WebSocketManager:
    """Gestor de conexiones WebSocket."""
    
    def __init__(self):
        # Conexiones activas: connection_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Información de conexiones: connection_id -> ConnectionInfo
        self.connections_info: Dict[str, ConnectionInfo] = {}
        
        # Mapeo por sesión: (tenant_id, session_id) -> List[connection_id]
        self.session_connections: Dict[tuple, List[str]] = {}
        
        # Mapeo por tenant: tenant_id -> List[connection_id]
        self.tenant_connections: Dict[str, List[str]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Registra una nueva conexión WebSocket.
        
        Args:
            websocket: Objeto WebSocket
            tenant_id: ID del tenant
            session_id: ID de la sesión
            user_id: ID del usuario (opcional)
            user_agent: User agent del cliente
            ip_address: IP del cliente
            
        Returns:
            str: ID de la conexión
        """
        connection_id = str(uuid4())
        
        # Verificar límite de conexiones
        if len(self.active_connections) >= settings.max_websocket_connections:
            logger.warning("Límite de conexiones WebSocket alcanzado")
            raise Exception("Límite de conexiones alcanzado")
        
        # Registrar conexión
        self.active_connections[connection_id] = websocket
        
        # Crear información de conexión
        connection_info = ConnectionInfo(
            connection_id=connection_id,
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
            status=ConnectionStatus.CONNECTED,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        self.connections_info[connection_id] = connection_info
        
        # Mapeo por sesión
        session_key = (tenant_id, session_id)
        if session_key not in self.session_connections:
            self.session_connections[session_key] = []
        self.session_connections[session_key].append(connection_id)
        
        # Mapeo por tenant
        if tenant_id not in self.tenant_connections:
            self.tenant_connections[tenant_id] = []
        self.tenant_connections[tenant_id].append(connection_id)
        
        logger.info(f"Nueva conexión WebSocket registrada: {connection_id}")
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """
        Desconecta y limpia una conexión WebSocket.
        
        Args:
            connection_id: ID de la conexión
        """
        if connection_id not in self.active_connections:
            return
        
        # Obtener información de la conexión
        connection_info = self.connections_info.get(connection_id)
        
        # Limpiar mapeos
        if connection_info:
            tenant_id = connection_info.tenant_id
            session_id = connection_info.session_id
            
            # Limpiar mapeo por sesión
            session_key = (tenant_id, session_id)
            if session_key in self.session_connections:
                if connection_id in self.session_connections[session_key]:
                    self.session_connections[session_key].remove(connection_id)
                if not self.session_connections[session_key]:
                    del self.session_connections[session_key]
            
            # Limpiar mapeo por tenant
            if tenant_id in self.tenant_connections:
                if connection_id in self.tenant_connections[tenant_id]:
                    self.tenant_connections[tenant_id].remove(connection_id)
                if not self.tenant_connections[tenant_id]:
                    del self.tenant_connections[tenant_id]
        
        # Eliminar conexión
        del self.active_connections[connection_id]
        if connection_id in self.connections_info:
            del self.connections_info[connection_id]
        
        logger.info(f"Conexión WebSocket desconectada: {connection_id}")
    
    async def send_message(
        self,
        connection_id: str,
        message: WebSocketMessage
    ) -> bool:
        """
        Envía un mensaje a una conexión específica.
        
        Args:
            connection_id: ID de la conexión
            message: Mensaje a enviar
            
        Returns:
            bool: True si se envió exitosamente
        """
        if connection_id not in self.active_connections:
            logger.warning(f"Conexión no encontrada: {connection_id}")
            return False
        
        websocket = self.active_connections[connection_id]
        
        try:
            message_data = message.dict()
            # Convertir datetime a string para JSON
            message_data["timestamp"] = message_data["timestamp"].isoformat()
            
            await websocket.send_text(json.dumps(message_data))
            return True
            
        except Exception as e:
            logger.error(f"Error enviando mensaje WebSocket: {str(e)}")
            # Desconectar conexión problemática
            await self.disconnect(connection_id)
            return False
    
    async def send_to_session(
        self,
        tenant_id: str,
        session_id: str,
        message: WebSocketMessage
    ) -> int:
        """
        Envía un mensaje a todas las conexiones de una sesión.
        
        Args:
            tenant_id: ID del tenant
            session_id: ID de la sesión
            message: Mensaje a enviar
            
        Returns:
            int: Número de conexiones que recibieron el mensaje
        """
        session_key = (tenant_id, session_id)
        if session_key not in self.session_connections:
            logger.warning(f"No hay conexiones para sesión: {tenant_id}/{session_id}")
            return 0
        
        connection_ids = self.session_connections[session_key].copy()
        sent_count = 0
        
        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                sent_count += 1
        
        return sent_count
    
    async def send_to_tenant(
        self,
        tenant_id: str,
        message: WebSocketMessage
    ) -> int:
        """
        Envía un mensaje a todas las conexiones de un tenant.
        
        Args:
            tenant_id: ID del tenant
            message: Mensaje a enviar
            
        Returns:
            int: Número de conexiones que recibieron el mensaje
        """
        if tenant_id not in self.tenant_connections:
            logger.warning(f"No hay conexiones para tenant: {tenant_id}")
            return 0
        
        connection_ids = self.tenant_connections[tenant_id].copy()
        sent_count = 0
        
        for connection_id in connection_ids:
            if await self.send_message(connection_id, message):
                sent_count += 1
        
        return sent_count
    
    async def send_error(
        self,
        connection_id: str,
        error: str,
        task_id: Optional[str] = None
    ):
        """
        Envía un mensaje de error a una conexión.
        
        Args:
            connection_id: ID de la conexión
            error: Mensaje de error
            task_id: ID de la tarea relacionada (opcional)
        """
        error_message = WebSocketMessage(
            type=WebSocketMessageType.ERROR,
            data={
                "error": error,
                "timestamp": datetime.now().isoformat()
            },
            task_id=task_id
        )
        
        await self.send_message(connection_id, error_message)
    
    async def handle_client_message(
        self,
        connection_id: str,
        message_data: Dict[str, Any]
    ):
        """
        Maneja mensajes recibidos del cliente.
        
        Args:
            connection_id: ID de la conexión
            message_data: Datos del mensaje
        """
        try:
            message_type = message_data.get("type")
            
            if message_type == "ping":
                # Responder con pong
                pong_message = WebSocketMessage(
                    type=WebSocketMessageType.PONG,
                    data={"message": "pong"}
                )
                await self.send_message(connection_id, pong_message)
                
                # Actualizar último ping
                if connection_id in self.connections_info:
                    self.connections_info[connection_id].last_ping = datetime.now()
            
            else:
                logger.info(f"Mensaje del cliente no manejado: {message_type}")
                
        except Exception as e:
            logger.error(f"Error manejando mensaje del cliente: {str(e)}")
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de las conexiones activas.
        
        Returns:
            Dict con estadísticas
        """
        return {
            "total_connections": len(self.active_connections),
            "total_sessions": len(self.session_connections),
            "total_tenants": len(self.tenant_connections),
            "connections_by_tenant": {
                tenant_id: len(connections) 
                for tenant_id, connections in self.tenant_connections.items()
            }
        }
    
    async def cleanup_stale_connections(self):
        """
        Limpia conexiones obsoletas (para ser llamado periódicamente).
        """
        current_time = datetime.now()
        stale_connections = []
        
        for connection_id, connection_info in self.connections_info.items():
            if connection_info.last_ping:
                time_since_ping = current_time - connection_info.last_ping
                if time_since_ping.total_seconds() > settings.websocket_ping_timeout * 3:
                    stale_connections.append(connection_id)
        
        for connection_id in stale_connections:
            logger.info(f"Limpiando conexión obsoleta: {connection_id}")
            await self.disconnect(connection_id)