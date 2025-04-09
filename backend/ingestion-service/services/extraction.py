"""
Funciones para extracción de texto de diferentes formatos de documento.
"""

import os
import logging
import mimetypes
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import UploadFile, ValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.errors import DocumentProcessingError
from config import get_extraction_config_for_mimetype, MAX_FILE_SIZE_MB, SUPPORTED_FILE_TYPES

logger = logging.getLogger(__name__)

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
        import fitz  # PyMuPDF
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
        import fitz
        
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
        from docx import Document
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
        from bs4 import BeautifulSoup
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
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
            import fitz
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
            from docx import Document
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

# Consolidated document processing functions from document_processor.py

async def validate_file(file: UploadFile, max_size_mb: int = MAX_FILE_SIZE_MB) -> Dict[str, Any]:
    """
    Valida un archivo cargado, verificando tipo y tamaño.
    
    Args:
        file: Archivo a validar
        max_size_mb: Tamaño máximo permitido en MB
        
    Returns:
        Dict: Información del archivo
        
    Raises:
        ValidationError: Si el archivo no es válido
    """
    if not file.filename:
        raise ValidationError(
            message="Nombre de archivo inválido",
            details={"filename": None}
        )
    
    # Verificar extensión
    file_extension = os.path.splitext(file.filename)[1].lower().replace(".", "")
    if file_extension not in SUPPORTED_FILE_TYPES:
        raise ValidationError(
            message=f"Tipo de archivo no soportado: {file_extension}",
            details={"filename": file.filename, "supported_types": SUPPORTED_FILE_TYPES}
        )
    
    # Verificar tamaño
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            message=f"Archivo demasiado grande: {file_size / (1024 * 1024):.2f}MB (máximo {max_size_mb}MB)",
            details={"filename": file.filename, "file_size": file_size, "max_size": max_size_mb * 1024 * 1024}
        )
    
    return {
        "filename": file.filename,
        "extension": file_extension,
        "size": file_size,
        "mimetype": file.content_type
    }

async def process_file(
    file_content: bytes, 
    file_type: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Procesa un archivo según su tipo, incluyendo metadatos.
    
    Args:
        file_content: Contenido del archivo en bytes
        file_type: Tipo del archivo
        metadata: Metadatos adicionales
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos combinados,
            'optimal_chunk_size': tamaño sugerido para chunking
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        # Determinar mimetype real
        mimetype = detect_mimetype(tmp_path)
        
        # Obtener procesador específico
        processor = get_file_processor(file_type)
        
        if not processor:
            raise DocumentProcessingError(f"Tipo de archivo no soportado: {file_type}")
        
        # Procesar archivo
        result = await processor(file_content)
        
        # Extraer metadatos del documento
        doc_metadata = await extract_document_metadata(tmp_path, mimetype)
        
        # Combinar metadatos
        full_metadata = {
            **(metadata or {}),
            **doc_metadata,
            'file_size': os.path.getsize(tmp_path),
            'processed_at': datetime.utcnow().isoformat()
        }
        
        # Analizar texto para chunking óptimo
        optimal_chunk_size = await detect_optimal_chunk_size(result['text'])
        
        # Eliminar temporal
        os.unlink(tmp_path)
        
        return {
            'text': result['text'],
            'metadata': full_metadata,
            'optimal_chunk_size': optimal_chunk_size
        }
        
    except Exception as e:
        logger.error(f"Error procesando archivo: {str(e)}")
        raise DocumentProcessingError(f"Error procesando archivo: {str(e)}")

async def process_pdf(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo PDF, usando método optimizado para archivos grandes.
    
    Args:
        file_content: Contenido del archivo PDF en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para analizar tamaño
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        # Determinar método basado en tamaño
        file_size = os.path.getsize(tmp_path) / (1024 * 1024)  # MB
        mimetype = detect_mimetype(tmp_path)
        
        if file_size > 10:  # Usar método para archivos grandes >10MB
            text = await extract_text_from_large_pdf(tmp_path)
        else:
            text = await extract_text_from_pdf(tmp_path)
            
        # Extraer metadatos
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        # Eliminar temporal
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
        
    except Exception as e:
        logger.error(f"Error procesando PDF: {str(e)}")
        raise DocumentProcessingError(f"Error procesando PDF: {str(e)}")

async def process_file_content(file_content: bytes, file_type: str) -> str:
    """Procesa contenido de archivo desde API"""
    processor = get_file_processor(file_type)
    if not processor:
        raise DocumentProcessingError(
            message=f"Tipo de archivo no soportado: {file_type}",
            details={"supported_types": list(processors.keys())}
        )
    return await processor(file_content)

async def process_file_from_storage(tenant_id: str, collection_id: str, file_key: str) -> str:
    """Procesa archivo descargado de Supabase Storage"""
    from backend.common.db.storage import get_file_from_storage
    
    file_path = await get_file_from_storage(tenant_id, collection_id, file_key)
    file_type = file_key.split('.')[-1].lower()
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return await process_file_content(content, file_type)

def get_file_processor(file_type: str):
    """Obtiene el procesador adecuado para el tipo de archivo"""
    processors = {
        "pdf": process_pdf,
        "docx": process_docx,
        "xlsx": process_xlsx,
        "pptx": process_pptx,
        "html": process_html,
        "md": process_markdown,
        "txt": process_text
    }
    return processors.get(file_type.lower())

async def process_docx(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo Word (.docx).
    
    Args:
        file_content: Contenido del archivo Word en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_docx(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando DOCX: {str(e)}")
        raise DocumentProcessingError(f"Error procesando DOCX: {str(e)}")

async def process_xlsx(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo Excel (.xlsx, .xls) o CSV.
    
    Args:
        file_content: Contenido del archivo Excel o CSV en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_excel(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando Excel/CSV: {str(e)}")
        raise DocumentProcessingError(f"Error procesando Excel/CSV: {str(e)}")

async def process_pptx(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo PowerPoint (.pptx).
    
    Args:
        file_content: Contenido del archivo PowerPoint en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_pptx(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando PPTX: {str(e)}")
        raise DocumentProcessingError(f"Error procesando PPTX: {str(e)}")

async def process_html(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo HTML.
    
    Args:
        file_content: Contenido del archivo HTML en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_html(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando HTML: {str(e)}")
        raise DocumentProcessingError(f"Error procesando HTML: {str(e)}")

async def process_markdown(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo Markdown (.md).
    
    Args:
        file_content: Contenido del archivo Markdown en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_markdown(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando Markdown: {str(e)}")
        raise DocumentProcessingError(f"Error procesando Markdown: {str(e)}")

async def process_text(file_content: bytes) -> Dict[str, Any]:
    """
    Procesa un archivo de texto plano (.txt).
    
    Args:
        file_content: Contenido del archivo de texto plano en bytes
        
    Returns:
        Dict: {
            'text': texto extraído,
            'metadata': metadatos del documento
        }
    """
    try:
        # Guardar temporalmente para análisis
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mimetype = detect_mimetype(tmp_path)
        text = await extract_text_from_text(tmp_path)
        metadata = await extract_document_metadata(tmp_path, mimetype)
        
        os.unlink(tmp_path)
        
        return {
            'text': text,
            'metadata': metadata,
            'optimal_chunk_size': await detect_optimal_chunk_size(text)
        }
    except Exception as e:
        logger.error(f"Error procesando texto plano: {str(e)}")
        raise DocumentProcessingError(f"Error procesando texto plano: {str(e)}")

async def extract_text_from_pptx(file_path: str) -> str:
    """
    Extrae texto de un archivo PowerPoint (.pptx).
    
    Args:
        file_path: Ruta al archivo PowerPoint
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        from pptx import Presentation
        presentation = Presentation(file_path)
        
        full_text = []
        for slide in presentation.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    full_text.append(shape.text)
        
        return "\n".join(full_text)
    except Exception as e:
        logger.error(f"Error extrayendo texto de PowerPoint: {str(e)}")
        return ""

async def extract_text_from_markdown(file_path: str) -> str:
    """
    Extrae texto de un archivo Markdown (.md).
    
    Args:
        file_path: Ruta al archivo Markdown
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        return file_path.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Error extrayendo texto de Markdown: {str(e)}")
        return ""

async def extract_text_from_text(file_path: str) -> str:
    """
    Extrae texto de un archivo de texto plano (.txt).
    
    Args:
        file_path: Ruta al archivo de texto plano
        
    Returns:
        str: Texto extraído del documento
    """
    try:
        return file_path.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Error extrayendo texto de texto plano: {str(e)}")
        return ""