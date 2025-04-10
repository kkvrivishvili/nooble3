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
from common.context.vars import get_full_context

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
            # Evaluar tamaño del archivo antes de abrirlo
            file_size = os.path.getsize(file_path)
            page_count = PDFExtractor._get_page_count(file_path)
            
            # Determinar si es un PDF grande basado en tamaño o número de páginas
            large_file = page_count > 50 or file_size > 10 * 1024 * 1024
            
            if large_file:
                # Para archivos grandes, usar extracción optimizada
                return await LargePDFExtractor.extract(file_path)
            
            # Para archivos pequeños, usar extracción estándar pero controlada
            doc = None
            text = ""
            try:
                doc = fitz.open(file_path)
                for page in doc:
                    page_text = page.get_text("text")
                    if page_text.strip():
                        text += page_text + "\n\n"
                        
                # Si no se extrajo texto, intentar con otro modo
                if not text.strip() and doc:
                    for page in doc:
                        page_text = page.get_text("html")
                        soup = BeautifulSoup(page_text, "html.parser")
                        text_content = soup.get_text(separator=" ", strip=True)
                        if text_content.strip():
                            text += text_content + "\n\n"
            finally:
                # Asegurar que el documento siempre se cierre para liberar memoria
                if doc:
                    doc.close()
                    del doc
            
            return text.strip()
        except Exception as e:
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_pdf",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error extrayendo texto de PDF: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from PDF: {str(e)}",
                details={"file_path": file_path, "error_code": ErrorCode.DOCUMENT_EXTRACTION_ERROR},
                context=error_context
            )
    
    @staticmethod
    def _get_page_count(file_path: str) -> int:
        """Obtiene el número de páginas sin cargar todo el documento en memoria."""
        doc = None
        try:
            doc = fitz.open(file_path)
            return doc.page_count
        except Exception as e:
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "get_page_count",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.warning(f"No se pudo obtener el número de páginas: {str(e)}", 
                          extra=error_context)
            return 0
        finally:
            # Garantizar que se liberen los recursos
            if doc:
                doc.close()
                del doc

class LargePDFExtractor:
    """Extractor especializado para PDFs grandes."""
    
    SUPPORTED_MIMETYPES = ['application/pdf']
    # Tamaño de lote óptimo para procesamiento de páginas
    BATCH_SIZE = 10
    
    @staticmethod
    def can_handle(mimetype: str) -> bool:
        return mimetype in LargePDFExtractor.SUPPORTED_MIMETYPES
    
    @staticmethod
    async def extract(file_path: str) -> str:
        """Extrae texto de un archivo PDF grande usando procesamiento por partes."""
        try:
            # Obtener información sin cargar todo el documento
            page_count = PDFExtractor._get_page_count(file_path)
            if page_count == 0:
                context = get_full_context()
                error_context = {
                    "service": "ingestion",
                    "operation": "extract_large_pdf",
                    "file_path": file_path,
                    **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
                }
                logger.error(f"No se pudo determinar el número de páginas para el PDF grande", 
                            extra=error_context)
                raise DocumentProcessingError(
                    message="Could not determine page count for large PDF",
                    details={"file_path": file_path},
                    context=error_context
                )
            
            # Crear lotes de páginas para procesamiento incremental
            batch_size = LargePDFExtractor.BATCH_SIZE
            batches = [(i, min(i + batch_size, page_count)) 
                      for i in range(0, page_count, batch_size)]
            
            all_text = []
            
            # Procesar cada lote independientemente para liberar memoria entre lotes
            for start_page, end_page in batches:
                batch_text = await LargePDFExtractor._process_page_range(
                    file_path, start_page, end_page
                )
                all_text.append(batch_text)
                
                # Forzar la liberación de memoria después de cada lote
                import gc
                gc.collect()
            
            return "\n\n".join(all_text).strip()
        except Exception as e:
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_large_pdf",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error extrayendo texto de PDF grande: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from large PDF: {str(e)}",
                details={"file_path": file_path, "error_code": ErrorCode.DOCUMENT_EXTRACTION_ERROR},
                context=error_context
            )
    
    @staticmethod
    async def _process_page_range(file_path: str, start_page: int, end_page: int) -> str:
        """Procesa un rango específico de páginas de un PDF."""
        doc = None
        try:
            doc = fitz.open(file_path)
            
            # Verificar que el documento está en el rango esperado
            if doc.page_count < end_page:
                end_page = doc.page_count
                
            batch_text = ""
            for i in range(start_page, end_page):
                try:
                    page = doc[i]
                    page_text = page.get_text("text")
                    if page_text.strip():
                        batch_text += page_text + "\n\n"
                    else:
                        # Intentar modo alternativo si no hay texto
                        page_text = page.get_text("html")
                        soup = BeautifulSoup(page_text, "html.parser")
                        text_content = soup.get_text(separator=" ", strip=True)
                        if text_content.strip():
                            batch_text += text_content + "\n\n"
                except Exception as e:
                    context = get_full_context()
                    error_context = {
                        "service": "ingestion",
                        "operation": "process_page_range",
                        "file_path": file_path,
                        "page": i,
                        **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
                    }
                    logger.warning(f"Error en página {i}: {str(e)}", 
                                  extra=error_context)
            
            return batch_text
        finally:
            # Garantizar que se liberen los recursos
            if doc:
                doc.close()
                del doc

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
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_docx",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error extrayendo texto de DOCX: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from DOCX: {str(e)}",
                details={"file_path": file_path},
                context=error_context
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
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_excel",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error extrayendo texto de Excel/CSV: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from Excel/CSV: {str(e)}",
                details={"file_path": file_path},
                context=error_context
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
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_html",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error extrayendo texto de HTML: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error extracting text from HTML: {str(e)}",
                details={"file_path": file_path},
                context=error_context
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
            context = get_full_context()
            error_context = {
                "service": "ingestion",
                "operation": "extract_text",
                "file_path": file_path,
                **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
            }
            logger.error(f"Error leyendo archivo de texto: {str(e)}", 
                        extra=error_context, exc_info=True)
            raise DocumentProcessingError(
                message=f"Error reading text file: {str(e)}",
                details={"file_path": file_path},
                context=error_context
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
    
    context = get_full_context()
    error_context = {
        "service": "ingestion",
        "operation": "get_extractor",
        "mimetype": mimetype,
        **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
    }
    logger.error(f"No se encontró extractor para el tipo MIME: {mimetype}", 
                extra=error_context)
    raise DocumentProcessingError(
        message=f"No extractor found for MIME type: {mimetype}",
        details={"mimetype": mimetype},
        context=error_context
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
        
    Raises:
        DocumentProcessingError: Si hay un error en la extracción del texto
        ValidationError: Si el tipo de archivo no es soportado
    """
    # Obtener contexto para errores
    context = get_full_context()
    error_context = {
        "service": "ingestion",
        "operation": "extract_text",
        "file_path": file_path,
        **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
    }
    
    try:
        # Detectar tipo MIME si no se proporciona
        if not mimetype:
            mimetype, _ = mimetypes.guess_type(file_path)
            if not mimetype:
                raise ValidationError(
                    message="Could not determine file type",
                    details={"file_path": file_path, "error_code": ErrorCode.INVALID_FILE_TYPE},
                    context=error_context
                )
                
        # Obtener el extractor adecuado
        extractor_class = get_extractor_for_mimetype(mimetype)
        if not extractor_class:
            logger.error(f"No hay extractor disponible para el tipo {mimetype}", 
                        extra=error_context)
            raise ValidationError(
                message=f"Unsupported file type: {mimetype}",
                details={"mimetype": mimetype, "error_code": ErrorCode.UNSUPPORTED_FILE_TYPE},
                context=error_context
            )
        
        # Realizar la extracción
        logger.info(f"Iniciando extracción de texto para archivo tipo {mimetype}", 
                   extra=error_context)
        text = await extractor_class.extract(file_path)
        
        # Verificar resultado
        if not text or not text.strip():
            logger.warning(f"No se pudo extraer texto del archivo, intentando método alternativo",
                         extra=error_context)
            # Intentar extracción alternativa
            text = await extract_with_specific_method(file_path, mimetype)
            
        logger.info(f"Extracción completada: {len(text)} caracteres extraídos", 
                  extra=error_context)
        return text
    except (DocumentProcessingError, ValidationError):
        # Reenviar excepciones tipadas
        raise
    except Exception as e:
        # Capturar otras excepciones y convertirlas al formato estándar
        error_msg = f"Error inesperado extrayendo texto: {str(e)}"
        logger.error(error_msg, extra=error_context, exc_info=True)
        raise ServiceError(
            message=error_msg,
            details={"file_path": file_path, "error_code": ErrorCode.DOCUMENT_EXTRACTION_ERROR},
            context=error_context
        )

async def extract_with_specific_method(file_path: str, mimetype: str) -> str:
    """
    Intenta extraer texto con métodos específicos según el tipo MIME si el extractor principal falla.
    
    Args:
        file_path: Ruta al archivo
        mimetype: Tipo MIME del archivo
        
    Returns:
        str: Texto extraído del archivo
        
    Raises:
        DocumentProcessingError: Si hay un error en la extracción alternativa
    """
    context = get_full_context()
    error_context = {
        "service": "ingestion",
        "operation": "extract_with_specific_method",
        "file_path": file_path,
        **({k: v for k, v in context.items() if k in ["tenant_id", "collection_id"]} if context else {})
    }
    
    try:
        text = ""
        # Intentos específicos por tipo de archivo
        if "pdf" in mimetype:
            # Intento con PDFMiner como alternativa
            try:
                import pdfminer
                from pdfminer.high_level import extract_text as pdfminer_extract
                text = pdfminer_extract(file_path)
                logger.info("Extracción alternativa exitosa con PDFMiner", extra=error_context)
            except ImportError:
                logger.warning("PDFMiner no disponible para extracción alternativa", 
                            extra=error_context)
        elif "html" in mimetype or "xml" in mimetype:
            # Intentar con lxml como alternativa
            try:
                from lxml import etree
                parser = etree.HTMLParser()
                tree = etree.parse(file_path, parser)
                text = ' '.join(tree.xpath('//text()'))
                logger.info("Extracción alternativa exitosa con lxml", extra=error_context)
            except ImportError:
                logger.warning("lxml no disponible para extracción alternativa", 
                            extra=error_context)
                
        # Si ninguna alternativa funcionó, aplicar método genérico
        if not text or not text.strip():
            with open(file_path, 'rb') as f:
                content = f.read()
                # Intentar decodificar como texto si es posible
                encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'windows-1252']
                for encoding in encodings:
                    try:
                        text = content.decode(encoding)
                        if text.strip():
                            logger.info(f"Extracción genérica exitosa con encoding {encoding}", 
                                      extra=error_context)
                            break
                    except UnicodeDecodeError:
                        continue
        
        return text.strip() if text else ""
    except Exception as e:
        logger.error(f"Error en extracción alternativa: {str(e)}", 
                   extra=error_context, exc_info=True)
        # Usar formato de error estandarizado
        raise DocumentProcessingError(
            message=f"Failed to extract text using alternative methods: {str(e)}",
            details={"file_path": file_path, "error_code": ErrorCode.DOCUMENT_EXTRACTION_ERROR},
            context=error_context
        )

# ... Resto del código ...