"""
Funciones para dividir documentos en fragmentos (chunks).
"""

import logging
from typing import List, Dict, Any

from common.errors import DocumentProcessingError
from config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

async def split_text_into_chunks(
    text: str, 
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
    metadata: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Divide texto en fragmentos (chunks) para procesamiento.
    
    Args:
        text: Texto a dividir
        chunk_size: Tamaño de cada fragmento
        chunk_overlap: Solapamiento entre fragmentos
        metadata: Metadatos a incluir en cada fragmento
        
    Returns:
        List[Dict[str, Any]]: Lista de fragmentos con metadatos
    """
    try:
        # Verificar que hay texto para procesar
        if not text or len(text.strip()) == 0:
            return []
        
        # Inicializar lista para almacenar fragmentos
        chunks = []
        
        # Si el texto es más corto que el tamaño del fragmento, devolverlo como un solo fragmento
        if len(text) <= chunk_size:
            return [{
                "text": text,
                "metadata": metadata or {}
            }]
        
        # Dividir texto en fragmentos
        start = 0
        while start < len(text):
            # Calcular final del fragmento actual
            end = start + chunk_size
            
            # Si no es el último fragmento, buscar un límite mejor (fin de párrafo, oración, etc.)
            if end < len(text):
                # Intentar terminar el chunk en fin de párrafo
                paragraph_end = text.find("\n\n", end - 50, end + 50)
                if paragraph_end != -1 and paragraph_end < end + 100:
                    end = paragraph_end
                else:
                    # Intentar terminar en fin de oración
                    sentence_end = max(
                        text.find(". ", end - 30, end + 30),
                        text.find("! ", end - 30, end + 30),
                        text.find("? ", end - 30, end + 30)
                    )
                    if sentence_end != -1 and sentence_end < end + 50:
                        end = sentence_end + 1  # Incluir el punto final
            
            # Extraer fragmento
            chunk_text = text[start:end].strip()
            
            if chunk_text:  # Solo agregar si hay texto
                chunks.append({
                    "text": chunk_text,
                    "metadata": metadata or {}
                })
            
            # Mover al siguiente punto de inicio (considerar solapamiento)
            start = end - chunk_overlap if end < len(text) else len(text)
        
        logger.info(f"Documento dividido en {len(chunks)} fragmentos")
        return chunks
        
    except Exception as e:
        logger.error(f"Error dividiendo texto en fragmentos: {str(e)}")
        raise DocumentProcessingError(
            message=f"Error dividiendo texto en fragmentos: {str(e)}",
            details={"text_length": len(text) if text else 0}
        )

async def split_document_intelligently(
    text: str,
    document_id: str,
    metadata: Dict[str, Any],
    chunk_size: int = None,
    chunk_overlap: int = None
) -> List[Dict[str, Any]]:
    """
    Divide un documento de forma inteligente, intentando preservar la estructura.
    
    Args:
        text: Texto del documento
        document_id: ID del documento
        metadata: Metadatos del documento
        chunk_size: Tamaño de fragmento
        chunk_overlap: Solapamiento entre fragmentos
        
    Returns:
        List[Dict[str, Any]]: Lista de fragmentos con metadatos
    """
    # Usar configuración del servicio si no se proporcionan valores
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap
    
    # Asegurarse de que metadata tenga document_id
    doc_metadata = dict(metadata or {})
    doc_metadata["document_id"] = document_id
    
    try:
        # Intentar usar divisores más avanzados de llama_index si está disponible
        try:
            from llama_index.node_parser import SentenceSplitter
            
            # Usar SentenceSplitter para una división más inteligente
            splitter = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            
            nodes = splitter.get_nodes_from_documents([{
                "text": text,
                "id_": document_id,
                "metadata": doc_metadata
            }])
            
            # Convertir nodos a formato estándar
            chunks = []
            for i, node in enumerate(nodes):
                # Extraer texto y metadatos
                node_text = node.text
                node_metadata = {
                    **doc_metadata,
                    "chunk_id": f"{document_id}_{i+1}",
                    "chunk_index": i
                }
                
                chunks.append({
                    "text": node_text,
                    "metadata": node_metadata
                })
                
            return chunks
            
        except ImportError:
            # Si llama_index no está disponible, usar método simple
            logger.warning("LlamaIndex no disponible, usando división simple")
            
            # Agregar información de fragmento a los metadatos
            doc_metadata = {
                **doc_metadata,
                "document_id": document_id
            }
            
            return await split_text_into_chunks(
                text=text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                metadata=doc_metadata
            )
            
    except Exception as e:
        logger.error(f"Error dividiendo documento {document_id}: {str(e)}")
        raise DocumentProcessingError(
            message=f"Error dividiendo documento: {str(e)}",
            details={"document_id": document_id}
        )