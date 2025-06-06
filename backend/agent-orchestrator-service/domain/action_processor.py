"""
Procesador central de acciones del dominio.
"""

import logging
import time
from typing import Dict, Type, Optional
from models.base_actions import BaseAction, ActionResult, ActionHandler
from domain.action_registry import ActionRegistry

logger = logging.getLogger(__name__)

class DomainActionProcessor:
    """Procesador central de acciones del dominio."""
    
    def __init__(self):
        self.registry = ActionRegistry()
        
    async def process(self, action: BaseAction) -> ActionResult:
        """
        Procesa una acción del dominio.
        
        Args:
            action: Acción a procesar
            
        Returns:
            Resultado de la ejecución
        """
        start_time = time.time()
        
        try:
            logger.info(f"Procesando acción: {action.action_type} para tenant: {action.tenant_id}")
            
            # Obtener handler
            handler = self.registry.get_handler(action.action_type)
            if not handler:
                raise Exception(f"No handler found for action: {action.action_type}")
            
            # Ejecutar acción
            result = await handler.execute(action)
            
            # Agregar timing
            result.execution_time = time.time() - start_time
            
            logger.info(f"Acción {action.action_type} completada en {result.execution_time:.2f}s")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error procesando acción {action.action_type}: {str(e)}")
            
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error={
                    "type": type(e).__name__,
                    "message": str(e)
                },
                execution_time=execution_time,
                metadata={
                    "action_type": action.action_type,
                    "tenant_id": action.tenant_id
                }
            )
    
    async def process_and_enqueue(self, action: BaseAction) -> ActionResult:
        """
        Procesa una acción que puede requerir encolado externo.
        
        Args:
            action: Acción a procesar
            
        Returns:
            Resultado inmediato (la acción puede seguir procesándose asíncronamente)
        """
        return await self.process(action)