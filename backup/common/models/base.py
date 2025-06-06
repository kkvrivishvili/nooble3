"""
Modelos base utilizados por todos los servicios.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel as PydanticBaseModel, Field
from uuid import UUID

# Utilizamos PydanticBaseModel como base para evitar conflictos
class BaseModel(PydanticBaseModel):
    """Modelo base del que heredan todos los modelos."""
    
    class Config:
        """Configuración para todos los modelos."""
        from_attributes = True  # Antes era orm_mode = True en Pydantic V1
        arbitrary_types_allowed = True
        extra = "ignore"  # Ignorar campos extra


class TenantInfo(BaseModel):
    """Información básica sobre un tenant."""
    tenant_id: str
    subscription_tier: str  # "free", "pro", "business"

    class Config:
        extra = "ignore"


class BaseResponse(BaseModel):
    """Modelo base para todas las respuestas API para garantizar consistencia."""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ErrorResponse(BaseResponse):
    """Modelo para respuestas de error estandarizadas."""
    success: bool = False
    status_code: int = 500
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": False,
                    "error": "No se pudo procesar la solicitud",
                    "message": "Ocurrió un error al procesar la solicitud",
                    "status_code": 500
                }
            ]
        }


class HealthResponse(BaseResponse):
    """Respuesta estándar para endpoints de health check."""
    status: str
    components: Dict[str, str]
    version: str
    success: bool = True