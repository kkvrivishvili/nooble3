"""
Integración con OpenAI para LLM y embeddings.
"""

import logging
from typing import Optional

from ..config.settings import get_settings

logger = logging.getLogger(__name__)

def get_openai_client():
    """
    Obtiene un cliente de OpenAI configurado.
    
    Returns:
        Un cliente de OpenAI listo para usar
    """
    try:
        from openai import OpenAI
    except ImportError:
        try:
            # Intentar con la importación antigua
            import openai
            return openai
        except ImportError:
            logger.error("No se pudo importar el cliente de OpenAI. Asegúrate de tener instalada la librería.")
            raise ImportError("Dependencia 'openai' no está instalada.")
    
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    return client

def get_openai_embedding_model(model_name: Optional[str] = None):
    """
    Obtiene un modelo de embeddings de OpenAI configurado.
    
    Args:
        model_name: Nombre del modelo a utilizar (opcional)
        
    Returns:
        Un modelo de embeddings compatible con LlamaIndex/LangChain
    """
    settings = get_settings()
    model = model_name or settings.default_embedding_model
    
    try:
        # Intentar importar desde llama_index primero
        from llama_index.embeddings.openai import OpenAIEmbedding
        
        logger.info(f"Usando embeddings de OpenAI con modelo {model}")
        
        return OpenAIEmbedding(
            model=model,
            api_key=settings.openai_api_key,
            embed_batch_size=settings.embedding_batch_size
        )
    except ImportError:
        # Si no está disponible, usar langchain
        logger.warning("No se pudo importar desde llama_index, usando langchain")
        try:
            from langchain_openai import OpenAIEmbeddings
            
            return OpenAIEmbeddings(
                model=model,
                openai_api_key=settings.openai_api_key
            )
        except ImportError:
            logger.error("No se pudo importar modelos de embedding desde ninguna librería.")
            raise ImportError("Dependencias 'llama_index' o 'langchain_openai' no están instaladas.")