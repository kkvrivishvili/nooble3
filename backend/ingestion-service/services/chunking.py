import logging
from typing import List, Dict, Any

from common.errors import ServiceError, ErrorCode, DocumentProcessingError, handle_errors
from common.config import get_settings
from common.config.tiers import get_tier_limits
from common.context import with_context, Context

# Importar la función desde llama_core para centralizar la implementación
from services.llama_core import split_text_with_llama_index

logger = logging.getLogger(__name__)
settings = get_settings()

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def split_text_into_chunks(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
    metadata: Dict[str, Any] = None,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Divide un texto en chunks usando LlamaIndex.
    
    Args:
        text: Texto completo a dividir
        chunk_size: Tamaño máximo de cada chunk en caracteres
        chunk_overlap: Número de caracteres que se solapan entre chunks
        metadata: Metadatos a incluir en cada chunk
        ctx: Contexto de la operación
        
    Returns:
        List[Dict[str, Any]]: Lista de chunks con metadatos
    """
    # Validaciones básicas
    if not text or not isinstance(text, str):
        raise DocumentProcessingError("El texto a dividir no es válido")
    
    if len(text) == 0:
        logger.warning("Se recibió un texto vacío para dividir")
        return []
    
    # Generar un document_id si no está en los metadatos
    metadata = metadata or {}
    document_id = metadata.get("document_id", f"doc_{hash(text)[:8]}")
    
    # Usar LlamaIndex para la división inteligente de texto
    return await split_text_with_llama_index(
        text=text,
        document_id=document_id,
        metadata=metadata,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        ctx=ctx
    )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def split_document_intelligently(
    text: str,
    document_id: str,
    metadata: Dict[str, Any],
    chunk_size: int = None,
    chunk_overlap: int = None,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Divide un documento de forma inteligente con LlamaIndex.
    
    Args:
        text: Texto del documento
        document_id: ID del documento
        metadata: Metadatos del documento
        chunk_size: Tamaño de fragmento
        chunk_overlap: Solapamiento entre fragmentos
        ctx: Contexto de la operación
        
    Returns:
        List[Dict[str, Any]]: Lista de fragmentos con metadatos
    """
    # Asegurarse de que metadata tenga document_id
    doc_metadata = dict(metadata or {})
    doc_metadata["document_id"] = document_id
    
    try:
        # Verificar si el tenant tiene acceso a RAG avanzado según su tier
        tier = "free"  # Valor por defecto
        if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
            tier = ctx.tenant_info.tier
            
        # Obtener los límites del tier para verificar si tiene RAG avanzado
        tenant_id = metadata.get("tenant_id")
        tier_limits = get_tier_limits(tier, tenant_id=tenant_id)
        has_advanced_rag = tier_limits.get("has_advanced_rag", False)
        
        logger.info(f"Tenant tier: {tier}, advanced RAG access: {has_advanced_rag}")
        
        # Uso directo de la función centralizada en llama_core
        return await split_text_with_llama_index(
            text=text,
            document_id=document_id,
            metadata=doc_metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            ctx=ctx
        )
            
    except Exception as e:
        logger.error(f"Error dividiendo documento {document_id}: {str(e)}")
        raise ServiceError(
            error_code=ErrorCode.PROCESSING_ERROR, 
            message=f"Error dividiendo documento con LlamaIndex: {str(e)}",
            details={"document_id": document_id}
        )