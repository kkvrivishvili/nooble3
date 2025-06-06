"""
Modelos relacionados con tenants y suscripciones.
"""

from typing import Dict, Any, List, Optional
from pydantic import Field
from .base import BaseModel, BaseResponse

class PublicTenantInfo(BaseModel):
    """Información básica de un tenant para acceso público."""
    tenant_id: str
    name: str
    token_quota: int = 0
    tokens_used: int = 0
    has_quota: bool = True


class TenantStatsResponse(BaseResponse):
    """Respuesta con estadísticas de uso de un tenant."""
    tenant_id: str
    requests_by_model: List[Dict[str, Any]] = Field(default_factory=list)
    tokens: Dict[str, int] = Field(default_factory=lambda: {"tokens_in": 0, "tokens_out": 0})
    daily_usage: List[Dict[str, Any]] = Field(default_factory=list)
    documents_by_collection: List[Dict[str, Any]] = Field(default_factory=list)


class UsageByModel(BaseModel):
    """Estadísticas de uso por modelo."""
    model: str
    count: int


class TokensUsage(BaseModel):
    """Información de tokens consumidos."""
    tokens_in: int = 0
    tokens_out: int = 0


class DailyUsage(BaseModel):
    """Uso diario de la API."""
    date: str
    count: int