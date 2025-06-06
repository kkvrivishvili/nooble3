"""
Endpoints WebSocket (sin cambios significativos del original).
"""

import logging
import json
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState
from datetime import datetime

from models.websocket_models import WebSocketMessage, WebSocketMessageType
from services.websocket_manager import WebSocketManager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/{tenant_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    session_id: str,
    user_id: str = Query(None)
):
    """
    Endpoint WebSocket para recibir respuestas de agentes en tiempo real.
    Acceso público sin JWT - la contabilización se hace por tenant_id del agente.
    
    Args:
        websocket: Conexión WebSocket
        tenant_id: ID del tenant propietario del agente
        session_id: ID de la sesión
        user_id: ID del usuario (opcional, sin autenticación)
    """
    ws_manager = WebSocketManager()
    connection_id = None
    
    try:
        # Aceptar conexión
        await websocket.accept()
        logger.info(f"WebSocket conectado: {tenant_id}/{session_id}")
        
        # Registrar conexión
        connection_id = await ws_manager.connect(
            websocket=websocket,
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
            user_agent=websocket.headers.get("user-agent"),
            ip_address=websocket.client.host if websocket.client else None
        )
        
        # Enviar confirmación de conexión
        await ws_manager.send_message(
            connection_id=connection_id,
            message=WebSocketMessage(
                type=WebSocketMessageType.CONNECTION_ACK,
                data={
                    "connection_id": connection_id,
                    "message": "Conexión establecida exitosamente",
                    "tenant_id": tenant_id,
                    "session_id": session_id
                },
                session_id=session_id,
                tenant_id=tenant_id
            )
        )
        
        # Loop para mantener conexión y manejar mensajes
        while True:
            try:
                # Esperar mensajes del cliente
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                    await ws_manager.handle_client_message(
                        connection_id=connection_id,
                        message_data=message_data
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Mensaje JSON inválido recibido: {data}")
                    await ws_manager.send_error(
                        connection_id=connection_id,
                        error="Formato de mensaje inválido"
                    )
                except Exception as e:
                    logger.error(f"Error procesando mensaje del cliente: {str(e)}")
                    await ws_manager.send_error(
                        connection_id=connection_id,
                        error="Error procesando mensaje"
                    )
                    
            except WebSocketDisconnect:
                logger.info(f"Cliente desconectado: {connection_id}")
                break
            except Exception as e:
                logger.error(f"Error en loop WebSocket: {str(e)}")
                break
    
    except Exception as e:
        logger.error(f"Error en WebSocket endpoint: {str(e)}")
        
        # Intentar enviar error si la conexión está activa
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Error interno del servidor"},
                    "timestamp": datetime.now().isoformat()
                }))
            except:
                pass
    
    finally:
        # Limpiar conexión
        if connection_id:
            await ws_manager.disconnect(connection_id)
            logger.info(f"Conexión limpiada: {connection_id}")

@router.get("/connections")
async def get_active_connections():
    """
    Obtiene estadísticas de conexiones activas.
    Solo para monitoring/debugging.
    """
    ws_manager = WebSocketManager()
    stats = await ws_manager.get_connection_stats()
    
    return {
        "success": True,
        "data": stats
    }

# ===== services/__init__.py =====
"""
Servicios del Agent Orchestrator.
"""

from .websocket_manager import WebSocketManager

__all__ = ['WebSocketManager']