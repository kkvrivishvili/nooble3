"""
Modelos para la gestión de trabajos en segundo plano.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from common.models.base import BaseModel, BaseResponse

class JobInfo(BaseModel):
    """Información básica de un trabajo de procesamiento."""
    job_id: str
    tenant_id: str
    status: str
    job_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    document_id: Optional[str] = None
    collection_id: Optional[str] = None
    batch_id: Optional[str] = None
    priority: Optional[int] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class JobListResponse(BaseResponse):
    """Respuesta para listado paginado de trabajos."""
    jobs: List[JobInfo]
    total: int
    limit: int
    offset: int
    filters: Optional[Dict[str, Any]] = None

class JobDetailResponse(BaseResponse):
    """Respuesta detallada para un trabajo específico."""
    job: JobInfo
    logs: Optional[List[Dict[str, Any]]] = None
    related_jobs: Optional[List[JobInfo]] = None
    stats: Optional[Dict[str, Any]] = None

class JobUpdateResponse(BaseResponse):
    """Respuesta para operaciones de actualización de un trabajo."""
    job: JobInfo
    action: str
    successful: bool
    previous_status: Optional[str] = None

class JobStatItem(BaseModel):
    """Estadística para un tipo de trabajo específico."""
    job_type: str
    total: int
    completed: int
    failed: int
    pending: int
    processing: int
    success_rate: float

class JobsStatsResponse(BaseResponse):
    """Respuesta con estadísticas de procesamiento de documentos."""
    stats: List[JobStatItem]
    period: str  # "hour", "day", "week", "month"
    from_date: datetime
    to_date: datetime
    total_jobs: int
