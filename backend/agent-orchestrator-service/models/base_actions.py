"""
Acciones base del sistema Domain Actions.
"""

from typing import Any, Dict, Optional
from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod

class BaseAction(BaseModel, ABC):
    """Acción base del sistema."""
    
    # Identificadores únicos
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str = Field(..., description="Tipo de acción")
    
    # Context (NO JWT - acceso público pero con contabilización)
    tenant_id: str = Field(..., description="ID del tenant propietario del agente")
    user_id: Optional[str] = Field(None, description="ID del usuario (opcional)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @abstractmethod
    def get_domain(self) -> str:
        """Retorna el dominio de la acción."""
        pass
    
    @abstractmethod
    def get_action_name(self) -> str:
        """Retorna el nombre de la acción."""
        pass
    
    def get_priority(self) -> str:
        """Retorna la prioridad por defecto."""
        return "normal"

class ActionResult(BaseModel):
    """Resultado de ejecución de una acción."""
    
    action_id: str = Field(..., description="ID de la acción")
    success: bool = Field(..., description="Si fue exitosa")
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = Field(None)
    execution_time: float = Field(..., description="Tiempo de ejecución")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ActionHandler(ABC):
    """Handler base para acciones."""
    
    @abstractmethod
    async def execute(self, action: BaseAction) -> ActionResult:
        """Ejecuta la acción."""
        pass
    
    @abstractmethod
    def can_handle(self, action_type: str) -> bool:
        """Verifica si puede manejar este tipo de acción."""
        pass
    
    @abstractmethod
    def get_supported_actions(self) -> list:
        """Retorna lista de acciones soportadas."""
        pass