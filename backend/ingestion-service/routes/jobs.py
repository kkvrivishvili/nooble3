"""
Endpoints para la gestión de trabajos en segundo plano.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Path

from common.models import TenantInfo, JobListResponse, JobDetailResponse, JobUpdateResponse
from common.errors import (
    ServiceError, handle_errors, ErrorCode,
    NotFoundError
)
from common.context import with_context
from common.auth import verify_tenant
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

from services.queue import get_job_status, retry_failed_job, cancel_job

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="Listar trabajos",
    description="Obtiene la lista de trabajos de procesamiento"
)
@handle_errors(error_type="simple", log_traceback=False, error_map={
    NotFoundError: ("NOT_FOUND", 404)
})
@with_context(tenant=True)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filtrar por estado (pending, processing, completed, failed)"),
    batch_id: Optional[str] = Query(None, description="Filtrar por ID de lote"),
    document_id: Optional[str] = Query(None, description="Filtrar por ID de documento"),
    limit: int = Query(50, description="Número máximo de trabajos a devolver"),
    offset: int = Query(0, description="Desplazamiento para paginación"),
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Lista los trabajos de procesamiento para el tenant actual.
    
    Args:
        status: Filtrar por estado del trabajo
        batch_id: Filtrar por ID de lote
        document_id: Filtrar por ID de documento
        limit: Límite de resultados
        offset: Desplazamiento para paginación
        tenant_info: Información del tenant
        
    Returns:
        JobListResponse: Lista paginada de trabajos
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Construir consulta base
        query = supabase.table(get_table_name("processing_jobs")) \
            .select("*") \
            .eq("tenant_id", tenant_id)
        
        # Aplicar filtros si existen
        if status:
            query = query.eq("status", status)
            
        if batch_id:
            query = query.eq("batch_id", batch_id)
            
        if document_id:
            query = query.eq("document_id", document_id)
            
        # Aplicar paginación
        query = query.order("created_at", desc=True) \
            .range(offset, offset + limit - 1)
            
        result = await query.execute()
        
        if result.error:
            raise ServiceError(
                message=f"Error obteniendo trabajos: {result.error}",
                error_code="DATABASE_ERROR"
            )
        
        # Calcular conteo total para metadatos de paginación
        count_query = supabase.table(get_table_name("processing_jobs")) \
            .select("count", count="exact") \
            .eq("tenant_id", tenant_id)
            
        if status:
            count_query = count_query.eq("status", status)
            
        if batch_id:
            count_query = count_query.eq("batch_id", batch_id)
            
        if document_id:
            count_query = count_query.eq("document_id", document_id)
            
        count_result = await count_query.execute()
        total_count = count_result.count if hasattr(count_result, "count") else len(result.data)
        
        # Transformar resultados para la respuesta
        jobs = result.data
        
        return JobListResponse(
            success=True,
            message="Trabajos obtenidos exitosamente",
            jobs=jobs,
            total=total_count,
            count=len(jobs),
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error listando trabajos: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al listar trabajos: {str(e)}",
            error_code="JOB_LIST_ERROR"
        )

@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    summary="Obtener trabajo",
    description="Obtiene detalles de un trabajo específico"
)
@handle_errors(error_type="simple", log_traceback=False, error_map={
    NotFoundError: ("NOT_FOUND", 404)
})
@with_context(tenant=True)
async def get_job(
    job_id: str = Path(..., description="ID del trabajo"),
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Obtiene detalles de un trabajo específico, incluyendo estado actual.
    
    Args:
        job_id: ID del trabajo
        tenant_info: Información del tenant
        
    Returns:
        JobDetailResponse: Detalles del trabajo
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        # Obtener información de la cola Redis
        queue_status = await get_job_status(job_id)
        
        # Obtener información de la base de datos
        supabase = get_supabase_client()
        
        job_result = await supabase.table(get_table_name("processing_jobs")) \
            .select("*") \
            .eq("job_id", job_id) \
            .eq("tenant_id", tenant_id) \
            .single() \
            .execute()
            
        if not job_result.data:
            raise NotFoundError(
                message=f"Trabajo con ID {job_id} no encontrado",
                details={"job_id": job_id}
            )
            
        job = job_result.data
        
        # Combinar información
        status = queue_status.get("status") or job.get("status")
        progress = queue_status.get("progress") or job.get("progress", 0)
        
        return JobDetailResponse(
            success=True,
            message="Trabajo obtenido exitosamente",
            job_id=job_id,
            document_id=job.get("document_id"),
            collection_id=job.get("collection_id"),
            batch_id=job.get("batch_id"),
            status=status,
            progress=progress,
            created_at=job.get("created_at"),
            updated_at=job.get("updated_at"),
            completion_time=job.get("completion_time"),
            error=job.get("error"),
            file_info=job.get("file_info", {}),
            processing_stats=job.get("processing_stats", {})
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo trabajo: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al obtener trabajo: {str(e)}",
            error_code="JOB_FETCH_ERROR"
        )

@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobUpdateResponse,
    summary="Reintentar trabajo",
    description="Reintenta un trabajo fallido"
)
@handle_errors(error_type="simple", log_traceback=False, error_map={
    NotFoundError: ("NOT_FOUND", 404)
})
@with_context(tenant=True)
async def retry_job(
    job_id: str = Path(..., description="ID del trabajo a reintentar"),
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Reintenta un trabajo fallido.
    
    Args:
        job_id: ID del trabajo a reintentar
        tenant_info: Información del tenant
        
    Returns:
        JobUpdateResponse: Resultado del reintento
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        # Reintentar trabajo
        result = await retry_failed_job(job_id, tenant_id)
        
        if not result["success"]:
            raise ServiceError(
                message=result["message"],
                error_code="JOB_RETRY_ERROR"
            )
            
        return JobUpdateResponse(
            success=True,
            message=f"Trabajo {job_id} reencolado exitosamente",
            job_id=job_id,
            status="pending",
            previous_status=result.get("previous_status")
        )
        
    except Exception as e:
        logger.error(f"Error al reintentar trabajo: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al reintentar trabajo: {str(e)}",
            error_code="JOB_RETRY_ERROR"
        )

@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobUpdateResponse,
    summary="Cancelar trabajo",
    description="Cancela un trabajo pendiente o en ejecución"
)
@handle_errors(error_type="simple", log_traceback=False, error_map={
    NotFoundError: ("NOT_FOUND", 404)
})
@with_context(tenant=True)
async def cancel_job_endpoint(
    job_id: str = Path(..., description="ID del trabajo a cancelar"),
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Cancela un trabajo pendiente o en ejecución.
    
    Args:
        job_id: ID del trabajo a cancelar
        tenant_info: Información del tenant
        
    Returns:
        JobUpdateResponse: Resultado de la cancelación
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        # Cancelar trabajo
        result = await cancel_job(job_id, tenant_id)
        
        if not result["success"]:
            raise ServiceError(
                message=result["message"],
                error_code="JOB_CANCEL_ERROR"
            )
            
        return JobUpdateResponse(
            success=True,
            message=f"Trabajo {job_id} cancelado exitosamente",
            job_id=job_id,
            status="cancelled",
            previous_status=result.get("previous_status")
        )
        
    except Exception as e:
        logger.error(f"Error al cancelar trabajo: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al cancelar trabajo: {str(e)}",
            error_code="JOB_CANCEL_ERROR"
        )

"""
Endpoints para monitoreo de trabajos de procesamiento.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, Query, Depends

from common.models import TenantInfo, JobsStatsResponse
from common.errors import ServiceError, handle_errors, ErrorCode
from common.context import with_context
from common.auth import verify_tenant
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

stats_router = APIRouter(tags=["stats"])
logger = logging.getLogger(__name__)

@stats_router.get(
    "/stats",
    response_model=JobsStatsResponse,
    summary="Estadísticas de procesamiento",
    description="Obtiene estadísticas de procesamiento de documentos"
)
@handle_errors(error_type="simple", log_traceback=False, error_map={
    NotFoundError: ("NOT_FOUND", 404)
})
@with_context(tenant=True)
async def get_jobs_stats(
    time_period: str = Query("day", description="Periodo de tiempo (hour, day, week, month)"),
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """
    Obtiene estadísticas de procesamiento de documentos.
    
    Args:
        time_period: Periodo de tiempo para las estadísticas
        tenant_info: Información del tenant
        
    Returns:
        JobsStatsResponse: Estadísticas de procesamiento
    """
    tenant_id = tenant_info.tenant_id
    
    try:
        supabase = get_supabase_client()
        
        # Determinar intervalo de fecha
        now = datetime.now()
        
        if time_period == "hour":
            start_date = now - timedelta(hours=1)
            interval = "minute"
        elif time_period == "day":
            start_date = now - timedelta(days=1)
            interval = "hour"
        elif time_period == "week":
            start_date = now - timedelta(weeks=1)
            interval = "day"
        else:  # month
            start_date = now - timedelta(days=30)
            interval = "day"
        
        start_date_str = start_date.isoformat()
        
        # Obtener estadísticas por estado
        status_counts = {}
        
        for status in ["pending", "processing", "completed", "failed", "cancelled"]:
            result = await supabase.table(get_table_name("processing_jobs")) \
                .select("count", count="exact") \
                .eq("tenant_id", tenant_id) \
                .eq("status", status) \
                .gte("created_at", start_date_str) \
                .execute()
                
            status_counts[status] = result.count if hasattr(result, "count") else 0
        
        # Obtener procesamiento por tipo de archivo
        file_type_stats = {}
        
        # Obtener tiempos de procesamiento promedio
        avg_processing_time = 0
        total_jobs = sum(status_counts.values())
        
        return JobsStatsResponse(
            success=True,
            message="Estadísticas obtenidas exitosamente",
            time_period=time_period,
            total_jobs=total_jobs,
            status_counts=status_counts,
            file_type_stats=file_type_stats,
            avg_processing_time=avg_processing_time
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        if isinstance(e, ServiceError):
            raise e
        raise ServiceError(
            message=f"Error al obtener estadísticas: {str(e)}",
            error_code="STATS_FETCH_ERROR"
        )

router.include_router(stats_router, prefix="/jobs")