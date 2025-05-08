"""
Mejores prácticas para el uso de @with_context en los servicios Query, Embedding, e Ingestion.

Este archivo sirve como referencia completa y guía de implementación 
para asegurar un uso consistente del decorador @with_context.
"""

from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from common.context import with_context, Context
from common.auth.tenant import TenantInfo, verify_tenant
from common.errors import handle_errors


# SECCIÓN 1: DOCUMENTACIÓN DE PATRONES RECOMENDADOS
# =================================================

"""
PATRONES RECOMENDADOS PARA EL USO DE @with_context

1. ENDPOINTS DE QUERY SERVICE
-----------------------------

1.1. Endpoint de consulta a colección:
    @router.post("/collections/{collection_id}/query")
    @with_context(tenant=True, collection=True, validate_tenant=True)  # Requerimos tenant y collection válidos para consultas
    async def query_collection(...):
        ...

1.2. Endpoint de información interna con contexto de agente:
    @router.post("/internal/agent/{agent_id}/process")
    @with_context(tenant=True, agent=True, conversation=True, validate_tenant=True)  # Requerimos todos los contextos para procesamiento de agente
    async def process_agent_query(...):
        ...

1.3. Endpoint de health check sin contexto:
    @router.get("/health")
    @with_context(tenant=False)  # Endpoint público sin requerimiento de tenant
    async def health_check(...):
        ...

2. ENDPOINTS DE EMBEDDING SERVICE
--------------------------------

2.1. Endpoint de generación de embeddings:
    @router.post("/embeddings")
    @with_context(tenant=True, collection=True, validate_tenant=True)  # Requerimos tenant y collection válidos para generar embeddings
    async def generate_embeddings(...):
        ...

2.2. Endpoint de modelos disponibles:
    @router.get("/models")
    @with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para obtener modelos según tier
    async def list_available_models(...):
        ...

2.3. Endpoint interno sin validación:
    @router.post("/internal/embed")
    @with_context(tenant=True, validate_tenant=False)  # Endpoint interno que acepta tenant_id como parámetro
    async def internal_embed(...):
        ...

3. ENDPOINTS DE INGESTION SERVICE
--------------------------------

3.1. Endpoint de carga de documentos:
    @router.post("/upload")
    @with_context(tenant=True, collection=True, validate_tenant=True)  # Requerimos tenant y collection válidos para la carga de documentos
    async def upload_document(...):
        ...

3.2. Endpoint de gestión de trabajos:
    @router.get("/jobs/{job_id}")
    @with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para acceder a los trabajos
    async def get_job_status(...):
        ...

4. SERVICIOS INTERNOS
-------------------

4.1. Funciones de acceso a vector store:
    @with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para acceder a vector store
    async def get_vector_store_for_collection(...):
        ...

4.2. Funciones de generación de embeddings:
    @with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para generación de embeddings
    async def get_embedding(...):
        ...

4.3. Funciones de cola de procesamiento:
    @with_context(tenant=True, validate_tenant=True)  # Requerimos tenant válido para operaciones de cola
    async def enqueue_job(...):
        ...

5. INTEGRACIÓN CON SISTEMAS CENTRALIZADOS
-----------------------------------------

5.1. Uso con CacheManager:
    # El tenant_id y otros valores contextuales se utilizan automáticamente
    # en las claves de caché para garantizar el aislamiento por tenant
    @with_context(tenant=True, validate_tenant=True)
    async def get_cached_data(...):
        result = await CacheManager.get(
            data_type="query_result",
            resource_id=query_id,
            # No es necesario pasar tenant_id, se obtiene del contexto
            use_memory=True,
            search_hierarchy=True
        )
        return result

5.2. Uso con track_token_usage:
    @with_context(tenant=True, validate_tenant=True)
    async def process_llm_request(...):
        # El track_token_usage utiliza el tenant_id del contexto
        await track_token_usage(
            tokens=token_count,
            model=model_name,
            token_type="llm"
            # No es necesario pasar tenant_id, se obtiene del contexto
        )
"""


# SECCIÓN 2: EJEMPLOS DE IMPLEMENTACIÓN
# =====================================

# Ejemplo de router para demostración
router = APIRouter()


# Modelo de ejemplo
class SampleRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None


class SampleResponse(BaseModel):
    result: str
    status: str


# Ejemplo de endpoint de query service
@router.post("/collections/{collection_id}/query")
@with_context(tenant=True, collection=True, validate_tenant=True)  # Requerimos tenant y collection válidos para consultas
@handle_errors(error_type="simple", log_traceback=False)
async def sample_query_endpoint(
    collection_id: str,
    request: SampleRequest,
    tenant_info: TenantInfo = Depends(verify_tenant),
    ctx: Context = None
) -> SampleResponse:
    """
    Ejemplo de endpoint de consulta que implementa las mejores prácticas.
    """
    # El contexto está garantizado por @with_context
    tenant_id = ctx.get_tenant_id()
    
    return SampleResponse(
        result=f"Consulta procesada para colección {collection_id}",
        status="success"
    )


# Ejemplo de endpoint interno
@router.post("/internal/process")
@with_context(tenant=True, validate_tenant=False)  # Endpoint interno que acepta tenant_id como parámetro
@handle_errors(error_type="service", log_traceback=True)
async def sample_internal_endpoint(
    request: Dict[str, Any],
    tenant_id: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Ejemplo de endpoint interno para procesamiento sin validación de tenant.
    """
    # El tenant_id se proporciona como parámetro
    return {
        "processed": True,
        "tenant_id": tenant_id
    }
