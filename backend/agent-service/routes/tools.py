"""
Endpoints para gestión de herramientas de agentes.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends

from common.models import TenantInfo
from common.errors import ServiceError, handle_errors
from common.context import with_context
from common.auth import verify_tenant

from services.tools import get_available_collections

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/tools/rag",
    tags=["Tools"],
    summary="Obtener herramientas RAG disponibles",
    description="Lista las colecciones disponibles como herramientas RAG"
)
@handle_errors(error_type="simple", log_traceback=False)
@with_context(tenant=True)
async def list_rag_tools(
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    """Lista todas las colecciones disponibles como herramientas RAG."""
    try:
        # Obtener colecciones disponibles
        collections = await get_available_collections(tenant_info.tenant_id)
        
        # Transformar cada colección en una herramienta
        tools = []
        for collection in collections:
            collection_id = collection.get("collection_id")
            tool_config = {
                "name": f"search_{collection_id[:8]}",
                "description": f"Buscar en {collection.get('name')} - {collection.get('description', '')}",
                "type": "rag",
                "metadata": {
                    "collection_id": collection_id,
                    "collection_name": collection.get("name"),
                    "similarity_top_k": 4,
                    "response_mode": "compact"
                }
            }
            tools.append(tool_config)
        
        return {
            "success": True,
            "message": "Herramientas RAG disponibles obtenidas correctamente",
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        logger.error(f"Error obteniendo herramientas RAG: {str(e)}")
        raise ServiceError(
            message=f"Error al obtener herramientas RAG: {str(e)}",
            error_code="TOOLS_RETRIEVAL_ERROR"
        )