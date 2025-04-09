"""
Endpoints para la gestión de trabajos en segundo plano.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Path

from common.models import TenantInfo, JobListResponse, JobDetailResponse, JobUpdateResponse
from common.errors import (
    ServiceError, handle_service_error_simple, ErrorCode,
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
@handle_service_error_simple
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
@handle_service_error_simple
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
@handle_service_error_simple
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
@handle_service_error_simple
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