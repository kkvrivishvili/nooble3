"""
Servicio unificado para extracción y procesamiento de documentos.
"""

import logging
import os
import tempfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Protocol, Type
import asyncio

from common.config import get_settings
from common.db.storage import get_file_from_storage
from common.errors import DocumentProcessingError, ValidationError, ServiceError, ErrorCode

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from docx import Document
import pandas as pd

logger = logging.getLogger(__name__)
settings = get_settings()

# --------------------------
# Clases de Estrategia para Extracción
# --------------------------

class DocumentExtractor(Protocol):
    """Protocolo que define la interfaz para extractores de documentos."""
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        """Determina si este extractor puede manejar el tipo de documento dado."""
        ...
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto del documento."""
        ...

class PDFExtractor:
    """Extractor para documentos PDF."""
    
    SUPPORTED_MIMETYPES = ['application/pdf']
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in PDFExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo PDF."""
        try:
            # Usar PyMuPDF para extraer texto
            doc = fitz.open(file_path)
            text = ""
            # Tamaño para determinar si es un PDF grande
            large_file = doc.page_count > 50 or os.path.getsize(file_path) > 10 * 1024 * 1024
            
            if large_file:
                # Para archivos grandes, usar extracción optimizada
                return await LargePDFExtractor.extract(file_path)
            
            for page in doc:
                page_text = page.get_text("text")
                if page_text.strip():
                    text += page_text + "\n\n"
            doc.close()
            
            # Si no se extrajo texto, intentar con otro modo
            if not text.strip():
                logger.warning(f"No se pudo extraer texto en modo normal, intentando con modo alternativo")
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    page_text = page.get_text("html")
                    soup = BeautifulSoup(page_text, "html.parser")
                    text_content = soup.get_text(separator=" ", strip=True)
                    if text_content.strip():
                        text += text_content + "\n\n"
                doc.close()
            
            return text.strip()
        except Exception as e:
            logger.error(f"Error extrayendo texto de PDF: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from PDF: {str(e)}",
                details={"file_path": file_path}
            )

class LargePDFExtractor:
    """Extractor especializado para PDFs grandes."""
    
    SUPPORTED_MIMETYPES = ['application/pdf']
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in LargePDFExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo PDF grande usando procesamiento por partes."""
        try:
            doc = fitz.open(file_path)
            text_parts = []
            
            # Procesar grupos de páginas en paralelo
            batch_size = 20  # Número de páginas por lote
            batches = [range(i, min(i + batch_size, doc.page_count)) 
                     for i in range(0, doc.page_count, batch_size)]
            
            async def process_batch(batch):
                batch_text = ""
                for i in batch:
                    try:
                        page = doc[i]
                        page_text = page.get_text("text")
                        if page_text.strip():
                            batch_text += page_text + "\n\n"
                    except Exception as e:
                        logger.warning(f"Error en página {i}: {str(e)}")
                return batch_text
            
            # Ejecutar extracción por lotes
            tasks = [process_batch(batch) for batch in batches]
            results = await asyncio.gather(*tasks)
            
            text = "".join(results)
            doc.close()
            
            return text.strip()
        except Exception as e:
            logger.error(f"Error extrayendo texto de PDF grande: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from large PDF: {str(e)}",
                details={"file_path": file_path}
            )

class DocxExtractor:
    """Extractor para documentos Word (.docx)."""
    
    SUPPORTED_MIMETYPES = [
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword'
    ]
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in DocxExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo Word (.docx)."""
        try:
            doc = Document(file_path)
            
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)
            
            # Procesar también tablas
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():
                            row_text.append(cell.text.strip())
                    if row_text:
                        paragraphs.append(" | ".join(row_text))
            
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Error extrayendo texto de DOCX: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from DOCX: {str(e)}",
                details={"file_path": file_path}
            )

class ExcelExtractor:
    """Extractor para hojas de cálculo (Excel, CSV)."""
    
    SUPPORTED_MIMETYPES = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'text/csv',
        'application/csv'
    ]
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in ExcelExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo Excel (.xlsx, .xls) o CSV."""
        try:
            if file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path, sheet_name=None)  # Leer todas las hojas
            
            text_parts = []
            
            # Si es un diccionario de DataFrames (múltiples hojas)
            if isinstance(df, dict):
                for sheet_name, sheet_df in df.items():
                    text_parts.append(f"Sheet: {sheet_name}")
                    text_parts.append(sheet_df.to_string(index=False))
            else:
                # Si es un único DataFrame
                text_parts.append(df.to_string(index=False))
            
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extrayendo texto de Excel/CSV: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from Excel/CSV: {str(e)}",
                details={"file_path": file_path}
            )

class HtmlExtractor:
    """Extractor para documentos HTML."""
    
    SUPPORTED_MIMETYPES = ['text/html', 'application/xhtml+xml']
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in HtmlExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo HTML."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Eliminar scripts y estilos
            for script in soup(["script", "style"]):
                script.extract()
            
            # Obtener texto
            text = soup.get_text(separator=' ', strip=True)
            
            # Limpiar espacios excesivos
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            logger.error(f"Error extrayendo texto de HTML: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from HTML: {str(e)}",
                details={"file_path": file_path}
            )

class TextExtractor:
    """Extractor para archivos de texto plano."""
    
    SUPPORTED_MIMETYPES = ['text/plain', 'text/markdown']
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in TextExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo de texto plano."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error leyendo archivo de texto: {str(e)}", exc_info=True)
            raise DocumentProcessingError(
                message=f"Error reading text file: {str(e)}",
                details={"file_path": file_path}
            )

# --------------------------
# Registro y Factory de Extractores
# --------------------------

# Lista de todos los extractores disponibles
DOCUMENT_EXTRACTORS = [
    PDFExtractor,
    DocxExtractor,
    ExcelExtractor,
    HtmlExtractor,
    TextExtractor
]

def get_extractor_for_mimetype(mimetype: str) -> Type[DocumentExtractor]:
    """
    Devuelve el extractor adecuado para un tipo MIME dado.
    
    Args:
        mimetype: Tipo MIME del documento
        
    Returns:
        Type[DocumentExtractor]: Clase del extractor
        
    Raises:
        DocumentProcessingError: Si no se encuentra un extractor para el tipo MIME
    """
    for extractor in DOCUMENT_EXTRACTORS:
        if extractor.can_handle(mimetype):
            return extractor
    
    raise DocumentProcessingError(
        message=f"No se encontró extractor para el tipo MIME: {mimetype}",
        details={"mimetype": mimetype}
    )

# --------------------------
# Funciones Principales de Extracción
# --------------------------

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
        mimetype, _ = mimetypes.guess_type(file_path)
    
    if not mimetype:
        # Si no se puede determinar el tipo, adivinar basado en la extensión
        extension = os.path.splitext(file_path)[1].lower()
        mime_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.html': 'text/html',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.csv': 'text/csv'
        }
        mimetype = mime_map.get(extension, 'application/octet-stream')
    
    try:
        # Obtener el extractor adecuado
        extractor = get_extractor_for_mimetype(mimetype)
        
        # Extraer texto usando el extractor
        text = await extractor.extract(file_path)
        
        # Verificar que se obtuvo texto
        if not text or not text.strip():
            logger.warning(f"El extractor principal no obtuvo texto. Intentando método alternativo.")
            return await extract_with_specific_method(file_path, mimetype)
        
        return text
    except Exception as e:
        logger.error(f"Error en extracción de texto: {str(e)}", exc_info=True)
        try:
            # Si falla el extractor principal, intentar método alternativo
            return await extract_with_specific_method(file_path, mimetype)
        except Exception as e2:
            # Si ambos métodos fallan, propagar error
            raise DocumentProcessingError(
                message=f"Error extracting text: {str(e)}. Fallback also failed: {str(e2)}",
                details={"file_path": file_path, "mimetype": mimetype}
            )

async def extract_with_specific_method(file_path: str, mimetype: str) -> str:
    """
    Intenta extraer texto con métodos específicos según el tipo MIME si el extractor principal falla.
    
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
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error en extracción específica para {mimetype}: {str(e)}")

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
                raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error extrayendo con PyPDF2: {str(e3)}")

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
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error extrayendo texto de Word: {str(e)}")

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
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error extrayendo texto de Excel/CSV: {str(e)}")

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
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error extrayendo texto de HTML: {str(e)}")

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
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error procesando archivo desde storage: {str(e)}")

async def validate_file(file: 'UploadFile') -> dict:
    """
    Valida un archivo subido y devuelve información sobre él.
    
    Args:
        file: Archivo subido a través de FastAPI
        
    Returns:
        dict: Información del archivo (tipo, tamaño, etc.)
        
    Raises:
        ValidationError: Si el archivo no es válido o supera el tamaño máximo
    """
    try:
        # Validar nombre y extensión
        filename = file.filename
        if not filename:
            raise ValidationError(
                message="Nombre de archivo inválido",
                details={"filename": filename}
            )
            
        # Detectar tipo MIME
        mime_type = detect_mimetype(filename)
        
        # Validar tipo de archivo
        valid_mime_types = [
            # PDF
            "application/pdf",
            # Word
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            # Excel
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            # CSV y texto
            "text/csv",
            "text/plain",
            "text/markdown",
            # HTML
            "text/html",
            "application/xhtml+xml",
            # JSON
            "application/json"
        ]
        
        if mime_type not in valid_mime_types:
            raise ValidationError(
                message=f"Tipo de archivo no soportado: {mime_type}",
                details={"mime_type": mime_type, "filename": filename}
            )
            
        # Validar tamaño (leer contenido para determinar el tamaño real)
        # Se limita la lectura a MAX_FILE_SIZE para evitar cargar archivos grandes en memoria
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
        
        # Verificamos posición actual
        current_position = file.file.tell()
        
        # Movemos al inicio para obtener tamaño
        file.file.seek(0, 2)  # Ir al final
        file_size = file.file.tell()  # Obtener posición actual (tamaño)
        
        # Volver a la posición original
        file.file.seek(current_position)
        
        if file_size > MAX_FILE_SIZE:
            raise ValidationError(
                message=f"El archivo excede el tamaño máximo permitido ({MAX_FILE_SIZE / (1024 * 1024):.1f} MB)",
                details={"file_size": file_size, "max_size": MAX_FILE_SIZE}
            )
            
        # Todo validado correctamente
        return {
            "filename": filename,
            "mime_type": mime_type,
            "size": file_size
        }
        
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        logger.error(f"Error validando archivo: {str(e)}")
        raise ServiceError(ErrorCode.INTERNAL_ERROR, f"Error validando archivo: {str(e)}")