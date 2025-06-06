"""
Gestor de colas con formato Domain:Action estandarizado - CORREGIDO con pool de Redis.
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from models.base_actions import BaseAction
from config.settings import get_settings
from common.redis_pool import get_redis_client  # Usar pool compartido

logger = logging.getLogger(__name__)
settings = get_settings()

class DomainQueueManager:
    """
    Gestor de colas con formato estandarizado.
    Formato: {domain}:{tenant_id}:{action}:{priority}
    """
    
    def __init__(self):
        self._redis_client = None
    
    async def _get_redis(self):
        """Obtiene cliente Redis del pool compartido."""
        if not self._redis_client:
            self._redis_client = await get_redis_client()
        return self._redis_client
    
    def _get_queue_name(self, action: BaseAction) -> str:
        """
        Genera nombre de cola según formato estándar.
        Formato: {domain}:{tenant_id}:{action}:{priority}
        """
        domain = action.get_domain()
        tenant_id = action.tenant_id
        action_name = action.get_action_name()
        priority = action.get_priority()
        
        return f"{domain}:{tenant_id}:{action_name}:{priority}"
    
    def _get_status_key(self, action_id: str, tenant_id: str) -> str:
        """Genera clave para estado de acción."""
        return f"action_status:{tenant_id}:{action_id}"
    
    def _get_queue_stats_key(self, tenant_id: str) -> str:
        """Genera clave para estadísticas de cola."""
        return f"queue_stats:{tenant_id}"
    
    async def enqueue_action(self, action: BaseAction, target_domain: str = None) -> bool:
        """
        Encola una acción en el dominio correspondiente.
        
        Args:
            action: Acción a encolar
            target_domain: Dominio destino (si es diferente al de la acción)
            
        Returns:
            bool: True si se encoló exitosamente
        """
        try:
            redis_client = await self._get_redis()
            
            # Usar dominio específico si se proporciona (para enviar a otros servicios)
            if target_domain:
                queue_name = f"{target_domain}:{action.tenant_id}:{action.get_action_name()}:{action.get_priority()}"
            else:
                queue_name = self._get_queue_name(action)
            
            # Verificar límite de cola
            queue_size = await redis_client.llen(queue_name)
            if queue_size >= settings.max_queue_size:
                logger.warning(f"Cola llena para {queue_name}: {queue_size}")
                return False
            
            # Preparar datos de la acción
            action_data = {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "tenant_id": action.tenant_id,
                "data": action.dict(),
                "enqueued_at": datetime.now().isoformat()
            }
            
            # Encolar (LPUSH para FIFO con BRPOP)
            await redis_client.lpush(queue_name, json.dumps(action_data))
            
            # Actualizar estadísticas
            await self._update_queue_stats(action.tenant_id, "enqueued")
            
            logger.info(f"Acción encolada en {queue_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error encolando acción: {str(e)}")
            return False
    
    async def dequeue_action(
        self,
        domain: str,
        tenant_id: str,
        action: str,
        priority: str = "normal",
        timeout: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Desencola una acción específica.
        
        Args:
            domain: Dominio de la acción
            tenant_id: ID del tenant
            action: Nombre de la acción
            priority: Prioridad
            timeout: Timeout en segundos
            
        Returns:
            Dict con datos de la acción o None
        """
        try:
            redis_client = await self._get_redis()
            
            queue_name = f"{domain}:{tenant_id}:{action}:{priority}"
            
            # BRPOP para obtener acción
            result = await redis_client.brpop(queue_name, timeout=timeout)
            
            if result:
                _, action_json = result
                action_data = json.loads(action_json)
                
                # Actualizar estadísticas
                await self._update_queue_stats(tenant_id, "dequeued")
                
                logger.info(f"Acción desencolada de {queue_name}")
                return action_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error desencolando acción: {str(e)}")
            return None
    
    async def set_action_status(
        self,
        action_id: str,
        tenant_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Establece el estado de una acción.
        
        Args:
            action_id: ID de la acción
            tenant_id: ID del tenant
            status: Estado de la acción
            metadata: Metadatos adicionales
        """
        try:
            redis_client = await self._get_redis()
            
            status_key = self._get_status_key(action_id, tenant_id)
            
            status_data = {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "status": status,
                "updated_at": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            
            # Guardar con TTL
            await redis_client.setex(
                status_key,
                settings.task_timeout_seconds,
                json.dumps(status_data)
            )
            
            # Actualizar estadísticas según estado
            if status == "completed":
                await self._update_queue_stats(tenant_id, "completed")
            elif status == "failed":
                await self._update_queue_stats(tenant_id, "failed")
            
        except Exception as e:
            logger.error(f"Error estableciendo estado de acción: {str(e)}")
    
    async def get_action_status(
        self,
        action_id: str,
        tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el estado de una acción.
        
        Args:
            action_id: ID de la acción
            tenant_id: ID del tenant
            
        Returns:
            Dict con estado o None si no existe
        """
        try:
            redis_client = await self._get_redis()
            
            status_key = self._get_status_key(action_id, tenant_id)
            status_json = await redis_client.get(status_key)
            
            if status_json:
                return json.loads(status_json)
            
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo estado de acción: {str(e)}")
            return None
    
    async def get_queue_size(
        self,
        domain: str,
        tenant_id: str,
        action: str,
        priority: str = "normal"
    ) -> int:
        """
        Obtiene el tamaño actual de una cola.
        
        Args:
            domain: Dominio de la acción
            tenant_id: ID del tenant
            action: Nombre de la acción
            priority: Prioridad
            
        Returns:
            Tamaño de la cola
        """
        try:
            redis_client = await self._get_redis()
            
            queue_name = f"{domain}:{tenant_id}:{action}:{priority}"
            return await redis_client.llen(queue_name)
            
        except Exception as e:
            logger.error(f"Error obteniendo tamaño de cola: {str(e)}")
            return 0
    
    async def clear_queue(
        self,
        domain: str,
        tenant_id: str,
        action: str,
        priority: str = "normal"
    ):
        """
        Limpia una cola específica.
        
        Args:
            domain: Dominio de la acción
            tenant_id: ID del tenant
            action: Nombre de la acción
            priority: Prioridad
        """
        try:
            redis_client = await self._get_redis()
            
            queue_name = f"{domain}:{tenant_id}:{action}:{priority}"
            await redis_client.delete(queue_name)
            
            logger.info(f"Cola limpiada: {queue_name}")
            
        except Exception as e:
            logger.error(f"Error limpiando cola: {str(e)}")
    
    async def _update_queue_stats(self, tenant_id: str, operation: str):
        """
        Actualiza estadísticas de cola para un tenant.
        
        Args:
            tenant_id: ID del tenant
            operation: Tipo de operación (enqueued, dequeued, completed, failed)
        """
        try:
            redis_client = await self._get_redis()
            stats_key = self._get_queue_stats_key(tenant_id)
            
            # Incrementar contador
            await redis_client.hincrby(stats_key, operation, 1)
            
            # Actualizar timestamp
            await redis_client.hset(
                stats_key,
                f"last_{operation}",
                datetime.now().isoformat()
            )
            
            # Establecer TTL de 24 horas
            await redis_client.expire(stats_key, 86400)
            
        except Exception as e:
            logger.error(f"Error actualizando estadísticas: {str(e)}")
    
    async def get_queue_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas de cola para un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Dict con estadísticas
        """
        try:
            redis_client = await self._get_redis()
            
            stats_key = self._get_queue_stats_key(tenant_id)
            stats = await redis_client.hgetall(stats_key)
            
            return {
                "tenant_id": tenant_id,
                "enqueued": int(stats.get("enqueued", 0)),
                "dequeued": int(stats.get("dequeued", 0)),
                "completed": int(stats.get("completed", 0)),
                "failed": int(stats.get("failed", 0)),
                "last_enqueued": stats.get("last_enqueued"),
                "last_dequeued": stats.get("last_dequeued"),
                "last_completed": stats.get("last_completed"),
                "last_failed": stats.get("last_failed")
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {str(e)}")
            return {}
    
    async def estimate_wait_time(self, tenant_id: str, action: str) -> float:
        """
        Estima tiempo de espera basado en estadísticas reales.
        
        Args:
            tenant_id: ID del tenant
            action: Tipo de acción
            
        Returns:
            Tiempo estimado en segundos
        """
        try:
            redis_client = await self._get_redis()
            
            # Obtener métricas de los últimos 100 procesados
            metrics_key = f"action_metrics:{tenant_id}:{action}"
            recent_times = await redis_client.lrange(metrics_key, 0, 99)
            
            if not recent_times:
                # Sin datos históricos, usar estimación por defecto
                return 8.0
            
            # Calcular promedio
            times = [float(t) for t in recent_times]
            avg_time = sum(times) / len(times)
            
            # Obtener tamaño actual de cola
            queue_size = await self.get_queue_size("agent", tenant_id, action)
            
            # Estimar tiempo total (tiempo promedio * posición en cola)
            return avg_time * (queue_size + 1)
            
        except Exception as e:
            logger.error(f"Error estimando tiempo: {str(e)}")
            return 8.0  # Fallback