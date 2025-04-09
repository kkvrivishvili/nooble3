"""
Módulo para interactuar con Supabase Storage
"""
import os
import uuid
from typing import Optional, Union
import logging

from supabase import Client

from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

def get_storage_client() -> Client:
    """Obtiene cliente de Supabase Storage"""
    from supabase import create_client
    
    return create_client(
        settings.supabase_url,
        settings.supabase_key
    )

async def upload_to_storage(
    tenant_id: str,
    collection_id: str,
    file_content: Union[bytes, str],
    file_name: str
) -> str:
    """
    Sube un archivo a Supabase Storage
    
    Returns:
        str: file_key (ruta relativa en storage)
    """
    sb = get_storage_client()
    
    # Generar ruta única: tenant/collection/uuid_filename
    file_ext = os.path.splitext(file_name)[1]
    file_key = f"{tenant_id}/{collection_id}/{uuid.uuid4()}{file_ext}"
    
    # Subir archivo
    sb.storage.from_("documents").upload(file_key, file_content)
    
    return file_key

async def get_file_from_storage(
    tenant_id: str,
    collection_id: str,
    file_key: str,
    local_path: Optional[str] = None
) -> str:
    """
    Descarga un archivo de Supabase Storage
    
    Returns:
        str: Ruta local del archivo descargado
    """
    sb = get_storage_client()
    
    if not local_path:
        local_path = f"/tmp/{os.path.basename(file_key)}"
    
    with open(local_path, "wb") as f:
        data = sb.storage.from_("documents").download(file_key)
        f.write(data)
    
    return local_path

async def update_document_counters(tenant_id: str, collection_id: str, increment: bool = True) -> bool:
    """
    Actualiza los contadores de documentos para un tenant y colección.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        increment: True para incrementar, False para decrementar
        
    Returns:
        bool: True si se actualizó correctamente
    """
    try:
        from .rpc import increment_document_count, decrement_document_count
        
        if increment:
            await increment_document_count(
                tenant_id=tenant_id,
                count=1,
                collection_id=collection_id
            )
        else:
            await decrement_document_count(
                tenant_id=tenant_id,
                count=1,
                collection_id=collection_id
            )
        
        return True
    except Exception as e:
        logger.error(f"Error actualizando contadores de documentos: {str(e)}")
        return False
