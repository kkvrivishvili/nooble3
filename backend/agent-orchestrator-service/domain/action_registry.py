"""
Registry automático de action handlers.
"""

import logging
from typing import Dict, Type, Optional, List
from models.base_actions import ActionHandler

logger = logging.getLogger(__name__)

class ActionRegistry:
    """Registry de action handlers."""
    
    def __init__(self):
        self.handlers: Dict[str, ActionHandler] = {}
        self._register_default_handlers()
    
    def register_handler(self, action_type: str, handler: ActionHandler):
        """Registra un handler manualmente."""
        self.handlers[action_type] = handler
        logger.info(f"Handler registrado: {action_type}")
        
    def get_handler(self, action_type: str) -> Optional[ActionHandler]:
        """Obtiene handler para un tipo de acción."""
        return self.handlers.get(action_type)
    
    def list_handlers(self) -> Dict[str, List[str]]:
        """Lista todos los handlers registrados."""
        return {
            action_type: handler.get_supported_actions()
            for action_type, handler in self.handlers.items()
        }
    
    def _register_default_handlers(self):
        """Registra handlers por defecto."""
        try:
            # Importar y registrar handlers
            from actions.chat_actions import ChatActionHandler
            from actions.websocket_actions import WebSocketActionHandler
            
            chat_handler = ChatActionHandler()
            websocket_handler = WebSocketActionHandler()
            
            # Registrar acciones de chat
            for action_type in chat_handler.get_supported_actions():
                self.register_handler(action_type, chat_handler)
            
            # Registrar acciones de websocket
            for action_type in websocket_handler.get_supported_actions():
                self.register_handler(action_type, websocket_handler)
                
        except ImportError as e:
            logger.warning(f"No se pudieron importar algunos handlers: {str(e)}")
