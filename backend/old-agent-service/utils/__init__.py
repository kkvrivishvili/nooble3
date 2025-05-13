"""
Utilidades específicas para el servicio de agentes.
"""

from common.utils import sanitize_query, format_sources

def get_http_client_from_main():
    """
    Obtiene el cliente HTTP compartido desde el módulo principal.
    
    Returns:
        httpx.AsyncClient: Cliente HTTP compartido
    """
    import httpx
    try:
        from main import get_http_client
        return get_http_client()
    except (ImportError, AttributeError):
        # Fallback: crear un cliente temporal si no se puede importar
        return httpx.AsyncClient(timeout=30.0)