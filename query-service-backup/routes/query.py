"""
Endpoints para consultas RAG.

NOTA IMPORTANTE: Este archivo ha sido actualizado para contener solo endpoints internos.
El Query Service solo debe ser accesible internamente desde el Agent Service.
Los endpoints públicos deben estar en el Agent Service que actúa como orquestador.
"""

import time
import logging
from typing import Optional, List, Dict, Any, Union

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import UUID4, BaseModel, Field

from common.models import TenantInfo, QueryRequest, QueryResponse
from common.errors import (
    handle_errors, QueryProcessingError, ErrorCode
)
from common.context import with_context, Context
from common.auth.tenant import TenantInfo, verify_tenant
from common.auth import validate_model_access
# Importar configuración centralizada del servicio
from config.settings import get_settings
from config.constants import (
    DEFAULT_SIMILARITY_TOP_K,
    MAX_SIMILARITY_TOP_K,
    DEFAULT_RESPONSE_MODE,
    SIMILARITY_THRESHOLD
)
from common.config.tiers import get_available_llm_models
from common.tracking import track_token_usage
from services.query_engine import create_query_engine, process_query_with_sources

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Endpoint /collections/{collection_id}/query eliminado
# Los endpoints públicos deben estar en el Agent Service que actúa como orquestador

# Endpoint /search eliminado
# Los endpoints públicos deben estar en el Agent Service que actúa como orquestador

# Para mantener la compatibilidad, se agrega un mensaje de deprecación
@router.post("/collections/{collection_id}/query")
async def deprecated_public_endpoint(collection_id: str):
    """Endpoint deprecado. Usar el Agent Service para consultas."""
    raise HTTPException(
        status_code=410,
        detail={
            "message": "Este endpoint ha sido deprecado. El Query Service ahora solo es accesible internamente.",
            "migration_path": "Use el Agent Service como punto de entrada para todas las consultas."
        }
    )

@router.post("/search")
async def deprecated_search_endpoint():
    """Endpoint deprecado. Usar el Agent Service para búsquedas."""
    raise HTTPException(
        status_code=410,
        detail={
            "message": "Este endpoint ha sido deprecado. El Query Service ahora solo es accesible internamente.",
            "migration_path": "Use el Agent Service como punto de entrada para todas las búsquedas."
        }
    )
