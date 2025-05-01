"""
Extractores específicos de LlamaIndex para procesamiento de documentos.

Este módulo extiende la funcionalidad de extracción usando LlamaIndex,
aprovechando los readers especializados para diferentes tipos de documentos.
"""

import logging
import os
import tempfile
from typing import Dict, Any, Optional, List, BinaryIO, Union

from fastapi import UploadFile
from llama_index.readers.file import (
    PDFReader, DocxReader, CSVReader, 
    PandasExcelReader, 
    MarkdownReader, ImageReader
)
# Implementaremos nuestro propio HTMLReader usando BeautifulSoup
from bs4 import BeautifulSoup
from llama_index.core import Document

from common.errors import DocumentProcessingError, ValidationError, ServiceError, handle_errors
from common.context import with_context, Context
from common.tracking import track_token_usage
from common.config import get_settings
from common.cache import get_with_cache_aside, serialize_for_cache
import hashlib
import tiktoken

logger = logging.getLogger(__name__)
settings = get_settings()

# Implementación personalizada de HTMLReader ya que la versión de LlamaIndex no la tiene disponible
class CustomHTMLReader:
    """Lector personalizado para contenido HTML usando BeautifulSoup."""
    
    def load_data(self, file_path=None, html_str=None):
        """
        Carga y procesa contenido HTML ya sea desde un archivo o desde una cadena.
        
        Args:
            file_path: Ruta al archivo HTML (opcional)
            html_str: Cadena de texto HTML (opcional)
            
        Returns:
            Una lista de documentos de LlamaIndex
        """
        if file_path is None and html_str is None:
            raise ValueError("Debe proporcionar file_path o html_str")
            
        if file_path is not None:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            html_content = html_str
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extraer texto del body, eliminando scripts y estilos
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator='\n', strip=True)
        
        # Obtener metadatos básicos (título si existe)
        metadata = {}
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string
            
        return [Document(text=text, metadata=metadata)]

# Mapa de tipos MIME a lectores de LlamaIndex
LLAMA_READERS = {
    'application/pdf': PDFReader(),
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DocxReader(),
    'application/msword': DocxReader(),
    'text/csv': CSVReader(),
    'application/csv': CSVReader(),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': PandasExcelReader(),
    'application/vnd.ms-excel': PandasExcelReader(),
    'text/html': CustomHTMLReader(),
    'application/xhtml+xml': CustomHTMLReader(),
    'text/markdown': MarkdownReader(),
    'text/plain': None,  # Manejado directamente como texto
    'image/jpeg': ImageReader(),
    'image/png': ImageReader(),
    'image/gif': ImageReader(),
    'image/webp': ImageReader(),
}

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def extract_with_llama_index(
    file_path: str,
    mimetype: str,
    metadata: Dict[str, Any],
    ctx: Context = None
) -> List[Document]:
    """
    Extrae contenido de un archivo usando los readers de LlamaIndex.
    
    Args:
        file_path: Ruta al archivo en disco
        mimetype: Tipo MIME del archivo
        metadata: Metadatos para asociar a los documentos
        ctx: Contexto de la operación
        
    Returns:
        List[Document]: Lista de documentos generados por LlamaIndex
        
    Raises:
        DocumentProcessingError: Si hay un error en la extracción
    """
    try:
        # Obtener el lector adecuado según el mimetype
        reader = LLAMA_READERS.get(mimetype)
        
        if not reader and mimetype.startswith('text/plain'):
            # Extraer texto plano directamente
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
                return [Document(text=text, metadata=metadata)]
        
        elif not reader:
            raise DocumentProcessingError(
                message=f"No hay lector de LlamaIndex para el tipo MIME: {mimetype}",
                details={"mimetype": mimetype}
            )
        
        # Extraer documentos con el lector apropiado
        documents = reader.load_data(file=file_path, extra_info=metadata)
        
        # Estimar tokens para tracking (aproximación)
        total_tokens = sum(len(doc.text.split()) * 1.3 for doc in documents)
        
        # Registrar uso para tracking
        tenant_id = metadata.get("tenant_id")
        if tenant_id:
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=int(total_tokens),
                token_type="processing",
                operation="extraction"
            )
        
        logger.info(f"Extraídos {len(documents)} documentos usando LlamaIndex ({int(total_tokens)} tokens estimados)")
        return documents
        
    except Exception as e:
        logger.error(f"Error extrayendo contenido con LlamaIndex: {str(e)}")
        if isinstance(e, DocumentProcessingError):
            raise
        raise DocumentProcessingError(
            message=f"Error en extracción con LlamaIndex: {str(e)}",
            details={"mimetype": mimetype, "file_path": file_path}
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def process_upload_with_llama_index(
    tenant_id: str,
    collection_id: str,
    file_key: str,
    ctx: Context = None
) -> str:
    """
    Procesa un archivo subido a Storage usando LlamaIndex, implementando el patrón Cache-Aside recomendado.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        file_key: Clave del archivo en Storage
        ctx: Contexto de la operación
        
    Returns:
        str: Texto procesado del documento
        
    Raises:
        ServiceError: Si hay un error en el procesamiento
    """
    from common.db.storage import get_file_from_storage
    from services.llama_core import load_and_process_file_with_llama_index
    import os
    import tempfile
    
    # Generar un resource_id consistente para el archivo
    # Usar la clave del archivo como identificador único
    resource_id = f"file:{file_key}"
    
    # Función para buscar en DB (en este caso no aplica, pero requerido por el patrón)
    async def fetch_from_db(resource_id, tenant_id):
        return None  # No guardamos directamente el texto procesado en DB
    
    # Función para generar el resultado si no está en caché
    async def generate_processed_text(resource_id, tenant_id):
        logger.info(f"Procesando archivo {file_key} con LlamaIndex (no en caché)")
        
        # Crear directorio temporal para descargar y procesar el archivo
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Descargar archivo de Storage
                local_path = os.path.join(temp_dir, f"temp_file_{file_key.split('/')[-1]}")
                file_info = await get_file_from_storage(file_key, local_path)
                
                if not file_info:
                    raise ServiceError(
                        message="No se pudo descargar el archivo de Storage",
                        error_code="DOWNLOAD_ERROR",
                        status_code=500
                    )
                    
                # Determinar tipo MIME
                mimetype = file_info.get("mimetype") or file_info.get("contentType")
                if not mimetype or mimetype == "application/octet-stream":
                    import mimetypes
                    guessed_type = mimetypes.guess_type(file_key.split("/")[-1])[0]
                    mimetype = guessed_type or "application/octet-stream"
                
                # El archivo ya fue descargado por get_file_from_storage
                file_name = file_key.split("/")[-1]
                temp_file_path = local_path
                    
                # Preparar metadatos
                metadata = {
                    "tenant_id": tenant_id,
                    "collection_id": collection_id,
                    "file_key": file_key,
                    "file_name": file_name
                }
                
                # Procesar con LlamaIndex
                text = await load_and_process_file_with_llama_index(
                    file_path=temp_file_path,
                    mimetype=mimetype,
                    metadata=metadata,
                    ctx=ctx
                )
                
                logger.info(f"Archivo {file_key} procesado exitosamente con LlamaIndex ({len(text)} caracteres)")
                return text
                
            except Exception as e:
                logger.error(f"Error procesando archivo {file_key}: {str(e)}")
                if isinstance(e, ServiceError):
                    raise
                raise ServiceError(
                    message=f"Error procesando archivo: {str(e)}",
                    error_code="PROCESSING_ERROR",
                    status_code=500
                )
    
    # Implementar el patrón Cache-Aside estándar
    # El texto procesado se cacheará con TTL_EXTENDED (24 horas)
    try:
        processed_text, metrics = await get_with_cache_aside(
            data_type="processed_file",
            resource_id=resource_id,
            tenant_id=tenant_id,
            collection_id=collection_id,
            fetch_from_db_func=fetch_from_db,
            generate_func=generate_processed_text,
            ctx=ctx
        )
        
        # Añadir métricas de caché al contexto si existe
        if ctx:
            ctx.add_metric("file_processing_cache", metrics)
        
        # Loguear si fue un acierto de caché
        if metrics.get("cache_hit", False):
            logger.info(f"Texto de archivo recuperado de caché: {resource_id}")
            
        return processed_text
        
    except Exception as e:
        logger.error(f"Error en proceso de caché para archivo {file_key}: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(
            message=f"Error procesando archivo: {str(e)}",
            error_code="PROCESSING_ERROR",
            status_code=500
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def process_text_with_llama_index(
    text: str,
    tenant_id: str,
    collection_id: str,
    metadata: Dict[str, Any] = None,
    ctx: Context = None
) -> str:
    """
    Procesa texto directamente usando LlamaIndex, implementando el patrón Cache-Aside recomendado.
    
    Args:
        text: Texto a procesar
        tenant_id: ID del tenant
        collection_id: ID de la colección
        metadata: Metadatos adicionales
        ctx: Contexto de la operación
        
    Returns:
        str: Texto procesado
    """
    if not text or not isinstance(text, str):
        raise ValidationError(
            message="Texto inválido o vacío",
            details={"text_length": len(text) if text else 0}
        )
    
    # Generar un resource_id consistente usando hash del texto
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    resource_id = f"text:{text_hash}"
    
    # Función para buscar en DB (en este caso no aplica, pero requerido por el patrón)
    async def fetch_from_db(resource_id, tenant_id):
        return None  # No guardamos directamente el texto procesado en DB
    
    # Función para generar el resultado si no está en caché
    async def generate_processed_text(resource_id, tenant_id):
        # Preparar metadatos para tracking
        combined_metadata = {
            **(metadata or {}),
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "content_type": "text/plain",
            "source": "direct_text"
        }
        
        # Mejorar la estimación de tokens usando tiktoken
        try:
            # Usar el modelo por defecto o uno apropiado para estimación
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            token_count = len(encoding.encode(text))
        except Exception as e:
            # Fallback a la estimación anterior si hay error con tiktoken
            logger.warning(f"Error estimando tokens con tiktoken: {str(e)}")
            token_count = int(len(text.split()) * 1.3)
        
        # Registrar uso para tracking
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=token_count,
            token_type="processing",
            operation="text_ingestion"
        )
        
        logger.info(f"Texto procesado con LlamaIndex ({len(text)} caracteres, {token_count} tokens)")
        return text
    
    # Implementar el patrón Cache-Aside estándar
    # El texto procesado se cacheará con TTL_STANDARD (1 hora)
    processed_text, metrics = await get_with_cache_aside(
        data_type="processed_text",
        resource_id=resource_id,
        tenant_id=tenant_id,
        collection_id=collection_id,
        fetch_from_db_func=fetch_from_db,
        generate_func=generate_processed_text,
        ctx=ctx
    )
    
    # Añadir métricas de caché al contexto si existe
    if ctx:
        ctx.add_metric("text_processing_cache", metrics)
    
    # Loguear si fue un acierto de caché
    if metrics.get("cache_hit", False):
        logger.info(f"Texto recuperado de caché: {resource_id}")
    
    return processed_text
