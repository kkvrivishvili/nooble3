"""
Worker para procesar callbacks y acciones asíncronas usando Domain Actions.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from domain.queue_manager import DomainQueueManager
from domain.action_processor import DomainActionProcessor
from models.websocket_actions import WebSocketSendAction
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class ActionWorker:
    """Worker para procesar callbacks y acciones asíncronas."""
    
    def __init__(self):
        self.queue_manager = DomainQueueManager()
        self.action_processor = DomainActionProcessor()
        self.running = False
    
    async def start(self):
        """Inicia el worker."""
        self.running = True
        logger.info("Iniciando action worker")
        
        try:
            await self._process_actions()
        except Exception as e:
            logger.error(f"Error en action worker: {str(e)}")
        finally:
            self.running = False
    
    async def stop(self):
        """Detiene el worker."""
        self.running = False
        logger.info("Deteniendo action worker")
    
    async def _process_actions(self):
        """Procesa acciones de forma continua."""
        while self.running:
            try:
                # Obtener tenants activos
                active_tenants = await self._get_active_tenants()
                
                if not active_tenants:
                    await asyncio.sleep(settings.worker_sleep_seconds)
                    continue
                
                # Procesar callbacks de websocket
                await self._process_websocket_callbacks(active_tenants)
                
                # Procesar otras acciones pendientes
                await self._process_orchestrator_actions(active_tenants)
                
                # Pequeña pausa
                await asyncio.sleep(settings.worker_sleep_seconds)
                
            except Exception as e:
                logger.error(f"Error procesando acciones: {str(e)}")
                await asyncio.sleep(1)
    
    async def _get_active_tenants(self) -> List[str]:
        """
        Obtiene lista de tenants activos.
        
        Returns:
            Lista de tenant IDs activos
        """
        try:
            await self.queue_manager.connect()
            
            # Buscar colas activas con patrón orchestrator:*
            queue_pattern = "orchestrator:*"
            queue_keys = []
            
            # Usar scan para evitar bloquear Redis con keys()
            cursor = 0
            while True:
                cursor, keys = await self.queue_manager.redis_client.scan(
                    cursor, 
                    match=queue_pattern,
                    count=100
                )
                queue_keys.extend(keys)
                if cursor == 0:
                    break
            
            tenant_ids = set()
            for key in queue_keys:
                # Extraer tenant_id del formato: orchestrator:tenant_id:action:priority
                parts = key.split(":")
                if len(parts) >= 2:
                    tenant_ids.add(parts[1])
            
            return list(tenant_ids)
            
        except Exception as e:
            logger.error(f"Error obteniendo tenants activos: {str(e)}")
            return []
    
    async def _process_websocket_callbacks(self, active_tenants: List[str]):
        """Procesa callbacks para envío via WebSocket."""
        for tenant_id in active_tenants:
            try:
                # Dequeue callback de websocket_send
                callback_data = await self.queue_manager.dequeue_action(
                    domain="orchestrator",
                    tenant_id=tenant_id,
                    action="websocket_send",
                    priority="high",
                    timeout=1
                )
                
                if callback_data:
                    await self._handle_websocket_callback(callback_data)
                    
            except Exception as e:
                logger.error(f"Error procesando callback WebSocket para {tenant_id}: {str(e)}")
    
    async def _process_orchestrator_actions(self, active_tenants: List[str]):
        """Procesa otras acciones del orchestrator."""
        for tenant_id in active_tenants:
            try:
                # Dequeue acciones de status update
                status_data = await self.queue_manager.dequeue_action(
                    domain="orchestrator",
                    tenant_id=tenant_id,
                    action="status_update",
                    priority="normal",
                    timeout=1
                )
                
                if status_data:
                    await self._handle_status_update(status_data)
                    
            except Exception as e:
                logger.error(f"Error procesando acciones orchestrator para {tenant_id}: {str(e)}")
    
    async def _handle_websocket_callback(self, callback_data: Dict[str, Any]):
        """
        Maneja un callback para envío via WebSocket usando Domain Actions.
        
        Args:
            callback_data: Datos del callback desde Agent Execution
        """
        try:
            data = callback_data.get("data", {})
            
            # Extraer información del callback
            task_id = data.get("task_id")
            session_id = data.get("session_id")
            tenant_id = callback_data.get("tenant_id")
            result = data.get("result", {})
            
            if not all([task_id, session_id, tenant_id]):
                logger.warning("Callback incompleto, faltan campos requeridos")
                return
            
            # Determinar tipo de mensaje y datos según el resultado
            if result.get("status") == "completed":
                message_type = "agent_response"
                message_data = {
                    "response": result.get("response"),
                    "sources": result.get("sources", []),
                    "execution_time": result.get("execution_time"),
                    "tokens_used": result.get("tokens_used"),
                    "agent_info": result.get("agent_info", {})
                }
            elif result.get("status") == "failed":
                message_type = "error"
                message_data = {
                    "error": result.get("error", {}).get("message", "Error desconocido"),
                    "error_type": result.get("error", {}).get("type", "unknown"),
                    "task_id": task_id
                }
            elif result.get("status") == "timeout":
                message_type = "error"
                message_data = {
                    "error": "La ejecución del agente excedió el tiempo límite",
                    "error_type": "timeout",
                    "task_id": task_id
                }
            else:
                message_type = "task_update"
                message_data = {
                    "status": result.get("status"),
                    "progress": result.get("progress", 0),
                    "task_id": task_id
                }
            
            # Crear acción WebSocket
            websocket_action = WebSocketSendAction(
                tenant_id=tenant_id,
                session_id=session_id,
                message_data=message_data,
                message_type=message_type,
                metadata={
                    "task_id": task_id,
                    "source": "agent_execution_callback",
                    "original_result": result
                }
            )
            
            # Procesar acción WebSocket
            ws_result = await self.action_processor.process(websocket_action)
            
            if ws_result.success:
                sent_count = ws_result.result.get("sent_to_connections", 0)
                if sent_count > 0:
                    logger.info(f"Callback enviado via WebSocket: {task_id} -> {sent_count} conexiones")
                else:
                    logger.warning(f"No hay conexiones WebSocket para sesión: {tenant_id}/{session_id}")
            else:
                logger.error(f"Error enviando callback WebSocket: {ws_result.error}")
            
            # Actualizar estado de la acción original
            await self.queue_manager.set_action_status(
                action_id=task_id,
                tenant_id=tenant_id,
                status=result.get("status", "completed"),
                metadata={
                    "completed_at": callback_data.get("timestamp"),
                    "sent_to_websocket": ws_result.success,
                    "websocket_connections": ws_result.result.get("sent_to_connections", 0) if ws_result.success else 0
                }
            )
            
        except Exception as e:
            logger.error(f"Error manejando WebSocket callback: {str(e)}")
    
    async def _handle_status_update(self, status_data: Dict[str, Any]):
        """
        Maneja una actualización de estado.
        
        Args:
            status_data: Datos de la actualización
        """
        try:
            data = status_data.get("data", {})
            
            action_id = data.get("action_id")
            tenant_id = status_data.get("tenant_id")
            status = data.get("status")
            progress = data.get("progress", 0)
            
            if not all([action_id, tenant_id, status]):
                logger.warning("Status update incompleto")
                return
            
            # Actualizar estado en Redis
            await self.queue_manager.set_action_status(
                action_id=action_id,
                tenant_id=tenant_id,
                status=status,
                metadata={
                    "progress": progress,
                    "updated_at": status_data.get("timestamp")
                }
            )
            
            # Si hay WebSocket, notificar el progreso
            if progress > 0:
                progress_action = WebSocketSendAction(
                    tenant_id=tenant_id,
                    session_id=data.get("session_id", ""),
                    message_data={
                        "task_id": action_id,
                        "status": status,
                        "progress": progress
                    },
                    message_type="task_update"
                )
                
                await self.action_processor.process(progress_action)
            
            logger.info(f"Estado actualizado: {action_id} -> {status} ({progress}%)")
            
        except Exception as e:
            logger.error(f"Error manejando status update: {str(e)}")