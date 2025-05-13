"""
Utilidades para trabajar con LlamaIndex específicas para el servicio de consulta.

Proporciona funciones y configuraciones para interactuar con componentes
de LlamaIndex de manera estandarizada.
"""

import logging
from typing import Any, Dict, Optional

from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.callbacks import CallbackManager

logger = logging.getLogger(__name__)

def create_response_synthesizer(
    llm: Any,
    response_mode: str = "compact",
    callback_manager: Optional[CallbackManager] = None,
    **kwargs
) -> Any:
    """
    Crea un sintetizador de respuestas configurado para LlamaIndex.
    
    Esta función centraliza la creación de componentes de síntesis de respuestas
    para mantener consistencia en el servicio de consulta.
    
    Args:
        llm: Modelo de lenguaje a utilizar
        response_mode: Modo de respuesta (compact, tree, etc.)
        callback_manager: Gestor de callbacks opcional
        **kwargs: Argumentos adicionales para el sintetizador
        
    Returns:
        Sintetizador de respuestas configurado
    """
    logger.info(f"Creando response synthesizer con modo: {response_mode}")
    
    # Valores predeterminados para modos comunes
    if response_mode == "compact":
        kwargs.setdefault("text_qa_template", None)  # Usar template predeterminado
    
    # Crear y configurar el sintetizador
    response_synthesizer = get_response_synthesizer(
        response_mode=response_mode,
        llm=llm,
        callback_manager=callback_manager,
        **kwargs
    )
    
    return response_synthesizer
