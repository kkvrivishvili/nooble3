"""
Utilidades para procesamiento y manipulación de texto.
"""

import re
from typing import List, Dict, Any

def sanitize_query(query: str) -> str:
    """
    Sanitiza una consulta de usuario eliminando datos potencialmente sensibles.
    
    Args:
        query: Consulta original del usuario
        
    Returns:
        str: Consulta sanitizada
    """
    # Reemplazar posibles datos sensibles (correos, API keys, etc.)
    # Emails
    query = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]', query)
    
    # API Keys y tokens (secuencias largas de caracteres alfanuméricos)
    query = re.sub(r'(api[_-]?key|token|password|secret)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{10,})["\']?', 
                 r'\1: [REDACTED]', 
                 query, 
                 flags=re.IGNORECASE)
    
    # URLs con credenciales
    query = re.sub(r'(https?:\/\/)[^:]+:[^@]+@', r'\1[REDACTED]@', query)
    
    # Números de tarjetas de crédito potenciales (secuencias de 13-19 dígitos)
    query = re.sub(r'\b(\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4})\b', '[CARD_NUMBER]', query)
    
    return query

def format_sources(sources: List[Dict[str, Any]]) -> str:
    """
    Formatea fuentes de información para incluirlas en respuestas.
    
    Args:
        sources: Lista de fuentes RAG
        
    Returns:
        str: Texto formateado con las fuentes
    """
    if not sources:
        return ""
    
    result = "\n\nFuentes:"
    for i, source in enumerate(sources, 1):
        source_text = source.get("text", "")
        source_metadata = source.get("metadata", {})
        source_name = source_metadata.get("source") or source_metadata.get("filename", f"Fuente {i}")
        result += f"\n[{i}] {source_name}: {source_text[:200]}..."
    
    return result
