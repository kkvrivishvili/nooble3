"""
Endpoints de chat refactorizados para Domain Actions.
"""

import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from models.chat_actions import ChatSendMessageAction, ChatGetStatusAction, ChatCancelTaskAction
from domain.action_processor import DomainActionProcessor
from common.errors import handle_errors
from common.context import with_context, Context

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/message")
@handle_errors(error_type="simple", log_traceback=True)
@with_context
async def send_message(
    action: ChatSendMessageAction,
    ctx: Context = None
):
    """
    Envía un mensaje de chat usando Domain Actions.
    
    Args:
        action: Acción de envío de mensaje
        
    Returns:
        Resultado de la acción
    """
    try:
        # Procesar acción
        processor = DomainActionProcessor()
        result = await processor.process(action)
        
        if result.success:
            return JSONResponse(
                content={
                    "success": True,
                    **result.result
                },
                status_code=200
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result.error.get("message", "Error interno")
            )
            
    except Exception as e:
        logger.error(f"Error en endpoint send_message: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error interno procesando mensaje"
        )

@router.get("/status/{task_id}")
@handle_errors(error_type="simple", log_traceback=False)
@with_context
async def get_task_status(
    task_id: str,
    tenant_id: str,  # Sin JWT - parámetro directo
    ctx: Context = None
):
    """
    Obtiene el estado de una tarea.
    
    Args:
        task_id: ID de la tarea
        tenant_id: ID del tenant (sin autenticación JWT)
        
    Returns:
        Estado actual de la tarea
    """
    try:
        # Crear acción de consulta
        action = ChatGetStatusAction(
            tenant_id=tenant_id,
            task_id=task_id
        )
        
        # Procesar acción
        processor = DomainActionProcessor()
        result = await processor.process(action)
        
        if result.success:
            return JSONResponse(
                content={
                    "success": True,
                    **result.result
                }
            )
        else:
            error_detail = result.error.get("message", "Tarea no encontrada")
            if result.error.get("type") == "TaskNotFound":
                raise HTTPException(status_code=404, detail=error_detail)
            else:
                raise HTTPException(status_code=500, detail=error_detail)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estado de tarea: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error interno obteniendo estado"
        )

@router.post("/cancel/{task_id}")
@handle_errors(error_type="simple", log_traceback=False)
@with_context
async def cancel_task(
    task_id: str,
    tenant_id: str,  # Sin JWT - parámetro directo
    ctx: Context = None
):
    """
    Cancela una tarea en cola.
    
    Args:
        task_id: ID de la tarea
        tenant_id: ID del tenant (sin autenticación JWT)
        
    Returns:
        Confirmación de cancelación
    """
    try:
        # Crear acción de cancelación
        action = ChatCancelTaskAction(
            tenant_id=tenant_id,
            task_id=task_id
        )
        
        # Procesar acción
        processor = DomainActionProcessor()
        result = await processor.process(action)
        
        if result.success:
            return JSONResponse(
                content={
                    "success": True,
                    **result.result
                }
            )
        else:
            error_detail = result.error.get("message", "No se pudo cancelar")
            if result.error.get("type") == "TaskNotFound":
                raise HTTPException(status_code=404, detail=error_detail)
            elif result.error.get("type") == "CannotCancel":
                raise HTTPException(status_code=400, detail=error_detail)
            else:
                raise HTTPException(status_code=500, detail=error_detail)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelando tarea: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error interno cancelando tarea"
        )
