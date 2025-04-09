"""
Servicio unificado para extracción y procesamiento de documentos.
"""

import logging
import os
import tempfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio

from common.config import get_settings
from common.db.storage import get_file_from_storage
from common.errors import DocumentProcessingError

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from docx import Document
import pandas as pd

logger = logging.getLogger(__name__)
settings = get_settings()

# --------------------------
# Funciones de Extracción Existente
# --------------------------
"""
Servicio para extracción de texto de diferentes formatos de archivo.
"""

def detect_mimetype(file_path: str) -> str:
    """
    Detecta el tipo MIME de un archivo.
    
    Args:
        file_path: Ruta al archivo
        
    Returns:
        str: Tipo MIME del archivo
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    
    if not mime_type:
        # Intentar detectar por extensión
        _, extension = os.path.splitext(file_path.lower())
        extension_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".csv": "text/csv",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".md": "text/markdown",
            ".json": "application/json",
            ".html": "text/html",
            ".htm": "text/html"
        }
        mime_type = extension_map.get(extension, "application/octet-stream")
    
    return mime_type

async def extract_text_from_file(file_path: str, mimetype: Optional[str] = None) -> str:
    """
    Extrae texto de un archivo utilizando el extractor adecuado según su tipo MIME.
    
    Args:
        file_path: Ruta al archivo
        mimetype: Tipo MIME del archivo (opcional, se detecta si no se proporciona)
        
    Returns:
        str: Texto extraído del archivo
    """
    if not mimetype:
        mimetype = detect_mimetype(file_path)
    
    # Obtener configuración específica para este tipo MIME
    extraction_config = get_extraction_config_for_mimetype(mimetype)
    
    try:
        # Usar LlamaIndex SimpleDirectoryReader para extraer texto
        from llama_index.readers.file import SimpleDirectoryReader
        
        # El directorio debe existir para que SimpleDirectoryReader funcione
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        
        # Configurar opciones según el tipo de documento
        file_extractor = SimpleDirectoryReader(
            input_dir=file_dir,
            file_extractor={
                # Configuraciones específicas para cada tipo
                ".pdf": extraction_config.get("pdf_parser", "default"),
                ".docx": "default",
                ".xlsx": "default",
                ".csv": "default"
            }
        )
        
        # Cargar solo el archivo específico
        documents = file_extractor.load_data(file=file_name)
        
        if not documents:
            logger.warning(f"No se pudo extraer texto del archivo {file_path}")
            return ""
        
        # Combinar texto de todos los documentos (puede haber múltiples páginas)
        combined_text = "\n\n".join([doc.text for doc in documents])
        
        return combined_text
    except Exception as e:
        logger.error(f"Error extrayendo texto de {file_path}: {str(e)}")
        # Intentar extraer con métodos específicos según el tipo MIME
        return await extract_with_specific_method(file_path, mimetype)

async def extract_with_specific_method(file_path: str, mimetype: str) -> str:
    """
    Intenta extraer texto con métodos específicos según el tipo MIME si LlamaIndex falla.
    
    Args:
        file_path: Ruta al archivo
        mimetype: Tipo MIME del archivo
        
    Returns:
        str: Texto extraído del archivo
    """
    try:
        # Implementaciones específicas para diferentes tipos MIME
        if mimetype == "application/pdf":
            return await extract_text_from_pdf(file_path)
        elif mimetype in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
            return await extract_text_from_docx(file_path)
        elif mimetype in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel", "text/csv"]:
            return await extract_text_from_excel(file_path)
        elif mimetype in ["text/plain", "text/markdown", "application/json"]:
            # Archivos de texto plano
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif mimetype in ["text/html", "application/xhtml+xml"]:
            return await extract_text_from_html(file_path)
        else:
            logger.warning(f"No hay extractor específico para el tipo MIME: {mimetype}")
            # Intentar leer como texto plano
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                return ""
    except Exception as e:
        logger.error(f"Error en extracción específica para {mimetype}: {str(e)}")
        return ""

async def extract_text_from_pdf(file_path: str) -> str:
    """
    Extrae texto de un archivo PDF.
    
    Args:
        file_path: Ruta al archivo PDF
        
    Returns:
        str: Texto extraído del PDF
    """
    try:
        # Intentar primero con PyMuPDF (más rápido)
        doc = fitz.open(file_path)
        text = ""
        
        for page in doc:
            text += page.get_text()
            text += "\n\n"
        
        return text
    except Exception as e:
        logger.warning(f"Error extrayendo con PyMuPDF: {str(e)}")
        
        try:
            # Intentar con pdfminer.six como alternativa
            from pdfminer.high_level import extract_text
            return extract_text(file_path)
        except Exception as e2:
            logger.error(f"Error extrayendo con pdfminer: {str(e2)}")
            
            try:
                # Último intento con PyPDF2
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                text = ""
                
                for page in reader.pages:
                    text += page.extract_text() + "\n\n"
                
                return text
            except Exception as e3:
                logger.error(f"Error extrayendo con PyPDF2: {str(e3)}")
                return ""

async def extract_text_from_large_pdf(file_path: str) -> str:
    """
    Extrae texto de un archivo PDF grande usando procesamiento por partes.
    
    Args:
        file_path: Ruta al archivo PDF
        
    Returns:
        str: Texto extraído del PDF
    """
    try:
        doc = fitz.open(file_path)
        
        # Procesar por lotes de páginas para reducir uso de memoria
        batch_size = 10
        text_parts = []
        
        for i in range(0, len(doc), batch_size):
            batch_text = ""
            for page_num in range(i, min(i + batch_size, len(doc))):
                page = doc[page_num]
                batch_text += page.get_text() + "\n\n"
            
            text_parts.append(batch_text)
        
        # Liberar memoria
        doc.close()
        
        return "\n\n".join(text_parts)
    except Exception as e:
        logger.error(f"Error extrayendo texto de PDF grande: {str(e)}")
        # Intentar con método alternativo
        return await extract_text_from_pdf(file_path)

async def extract_text_from_docx(file_path: str) -> str:
    """
    Extrae texto de un archivo Word (.docx).
    
    Args:
        file_path: Ruta al archivo Word
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        doc = Document(file_path)
        
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
            
        # También extraer texto de tablas
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    full_text.append(" | ".join(row_text))
        
        return "\n".join(full_text)
    except Exception as e:
        logger.error(f"Error extrayendo texto de Word: {str(e)}")
        return ""

async def extract_text_from_excel(file_path: str) -> str:
    """
    Extrae texto de un archivo Excel (.xlsx, .xls) o CSV.
    
    Args:
        file_path: Ruta al archivo Excel o CSV
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        import pandas as pd
        
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:  # Excel
            df = pd.read_excel(file_path)
        
        # Convertir cada hoja a texto
        text_parts = []
        
        # Añadir nombres de columnas
        text_parts.append(" | ".join(str(col) for col in df.columns))
        
        # Añadir filas
        for _, row in df.iterrows():
            text_parts.append(" | ".join(str(cell) for cell in row))
        
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"Error extrayendo texto de Excel/CSV: {str(e)}")
        return ""

async def extract_text_from_html(file_path: str) -> str:
    """
    Extrae texto de un archivo HTML.
    
    Args:
        file_path: Ruta al archivo HTML
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        soup = BeautifulSoup(open(file_path, 'r', encoding='utf-8', errors='ignore').read(), 'html.parser')
        
        # Extraer texto visible y estructurado
        text = soup.get_text(separator='\n', strip=True)
        
        # También preservar enlaces importantes
        for link in soup.find_all('a', href=True):
            if link.text.strip():
                text += f"\nLink: {link.text.strip()} - {link['href']}"
        
        return text
    except Exception as e:
        logger.error(f"Error extrayendo texto de HTML: {str(e)}")
        return ""

async def detect_optimal_chunk_size(text: str) -> int:
    """
    Detecta el tamaño óptimo de fragmento basado en el contenido.
    
    Args:
        text: Texto a analizar
        
    Returns:
        int: Tamaño óptimo de fragmento
    """
    # Análisis básico del texto
    avg_sentence_length = 0
    sentences = text.split('.')
    
    if sentences:
        avg_sentence_length = sum(len(s) for s in sentences) / len(sentences)
    
    # Ajustar tamaño del fragmento según complejidad del texto
    if avg_sentence_length > 100:
        # Texto con oraciones largas, usa fragmentos más grandes
        return 1500
    elif avg_sentence_length < 50:
        # Texto con oraciones cortas, usa fragmentos más pequeños
        return 800
    else:
        # Valor por defecto
        return 1000

async def extract_document_metadata(file_path: str, mimetype: str) -> Dict[str, Any]:
    """
    Extrae metadatos detallados de un documento.
    
    Args:
        file_path: Ruta al archivo
        mimetype: Tipo MIME del archivo
        
    Returns:
        Dict[str, Any]: Metadatos del documento
    """
    metadata = {
        "content_type": mimetype,
        "extracted_at": "2023-03-09T14:30:00Z",
    }
    
    try:
        # Extraer metadatos específicos según tipo
        if "pdf" in mimetype:
            doc = fitz.open(file_path)
            
            # Extraer metadatos básicos
            metadata.update({
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "keywords": doc.metadata.get("keywords", ""),
                "page_count": len(doc),
                "created_date": doc.metadata.get("creationDate", "")
            })
            
            doc.close()
            
        elif "docx" in mimetype:
            doc = Document(file_path)
            
            # Extraer propiedades del documento
            core_props = doc.core_properties
            metadata.update({
                "title": core_props.title or "",
                "author": core_props.author or "",
                "created_date": str(core_props.created) if core_props.created else "",
                "modified_date": str(core_props.modified) if core_props.modified else "",
                "paragraph_count": len(doc.paragraphs),
                "word_count": sum(len(p.text.split()) for p in doc.paragraphs)
            })
            
        # Más tipos según sea necesario...
            
    except Exception as e:
        logger.warning(f"Error extrayendo metadatos avanzados: {str(e)}")
        
    return metadata

def get_extraction_config_for_mimetype(mimetype: str) -> Dict[str, Any]:
    """
    Obtiene la configuración de extracción específica para un tipo MIME.
    
    Args:
        mimetype: Tipo MIME del documento
        
    Returns:
        Dict[str, Any]: Configuración de extracción
    """
    # Configuración predeterminada
    default_config = {
        "pdf_parser": "pdfminer",
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "max_file_size_mb": 50
    }
    
    # Configuraciones específicas por tipo MIME
    mime_configs = {
        "application/pdf": {
            "pdf_parser": "pymupdf",
            "max_file_size_mb": 100,
            "large_file_threshold_mb": 25
        },
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
            "max_file_size_mb": 30
        },
        "text/plain": {
            "max_file_size_mb": 20
        },
        "text/html": {
            "max_file_size_mb": 15
        }
    }
    
    return mime_configs.get(mimetype, default_config)

# --------------------------
# Funciones Consolidadas de Procesamiento
# --------------------------
async def process_file(
    file_content: bytes,
    file_type: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Procesa un archivo y extrae texto, metadatos y chunks optimizados.
    
    Args:
        file_content: Contenido del archivo en bytes
        file_type: Tipo de archivo (pdf, docx, etc)
        metadata: Metadatos adicionales
        
    Returns:
        Dict: {
            'text': str,
            'metadata': dict,
            'optimal_chunk_size': int,
            'chunks': list[str]
        }
    """
    try:
        # Guardar temporalmente el archivo
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = tmp_file.name
            
        # Extraer contenido
        text = await extract_text_from_file(tmp_path, file_type)
        metadata = await extract_document_metadata(tmp_path, file_type)
        chunk_size = await detect_optimal_chunk_size(text)
        
        # Dividir en chunks
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': chunk_size,
            'chunks': chunks
        }
        
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

async def process_text(
    text_content: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Procesa texto plano."""
    chunk_size = await detect_optimal_chunk_size(text_content)
    return {
        'text': text_content,
        'metadata': metadata or {},
        'optimal_chunk_size': chunk_size,
        'chunks': [text_content[i:i+chunk_size] for i in range(0, len(text_content), chunk_size)]
    }

async def process_file_from_storage(
    tenant_id: str,
    collection_id: str,
    file_key: str
) -> str:
    """
    Procesa un archivo directamente desde Supabase Storage.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        file_key: Clave del archivo en storage
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        logger.info(f"Procesando archivo desde storage: {file_key}")
        
        # Obtener archivo desde Supabase Storage
        file_data = await get_file_from_storage(file_key, tenant_id)
        if not file_data:
            raise DocumentProcessingError(
                message=f"No se pudo obtener el archivo desde storage: {file_key}",
                details={"tenant_id": tenant_id, "file_key": file_key}
            )
        
        # Determinar tipo MIME
        file_type = detect_mimetype(file_key)
        
        # Procesar archivo
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(file_data)
            tmp_path = tmp_file.name
            
        try:
            # Extraer contenido utilizando las funciones existentes
            text = await extract_text_from_file(tmp_path, file_type)
            return text
        finally:
            # Limpiar archivo temporal
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error procesando archivo desde storage: {str(e)}")
        if isinstance(e, DocumentProcessingError):
            raise
        raise DocumentProcessingError(
            message=f"Error procesando archivo desde storage: {str(e)}",
            details={"tenant_id": tenant_id, "file_key": file_key}
        )