"""
Modelos específicos del servicio de ingesta.
"""

from .jobs import JobListResponse, JobDetailResponse, JobUpdateResponse, JobsStatsResponse

__all__ = [
    'JobListResponse',
    'JobDetailResponse', 
    'JobUpdateResponse',
    'JobsStatsResponse'
]
