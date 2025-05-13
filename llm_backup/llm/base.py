"""
Interfaces base para la abstracción de LLMs y modelos de embedding.
"""

from abc import ABC, abstractmethod
import asyncio
from typing import Dict, Any, List, Optional, Union, AsyncGenerator

class BaseEmbeddingModel(ABC):
    """Interfaz común para modelos de embedding."""
    
    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """
        Genera un embedding para un texto.
        
        Args:
            text: Texto para el embedding
            
        Returns:
            List[float]: Vector de embedding
        """
        pass
    
    @abstractmethod
    async def get_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para múltiples textos en batch.
        
        Args:
            texts: Lista de textos
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
        """
        pass

class BaseLLM(ABC):
    """Interfaz común para modelos de lenguaje."""
    
    @abstractmethod
    async def predict(self, 
                     prompt: str, 
                     system_prompt: Optional[str] = None,
                     **kwargs) -> str:
        """
        Genera una respuesta para un prompt.
        
        Args:
            prompt: Texto del prompt
            system_prompt: Instrucción de sistema opcional
            **kwargs: Parámetros adicionales específicos del modelo
            
        Returns:
            str: Texto generado
        """
        pass
    
    @abstractmethod
    async def stream_generate(self, 
                             prompt: str, 
                             system_prompt: Optional[str] = None,
                             **kwargs) -> AsyncGenerator[str, None]:
        """
        Genera una respuesta en streaming.
        
        Args:
            prompt: Texto del prompt
            system_prompt: Instrucción de sistema opcional
            **kwargs: Parámetros adicionales específicos del modelo
            
        Yields:
            str: Fragmentos de texto generados
        """
        pass
    
    @abstractmethod
    async def chat(self, 
                  messages: List[Dict[str, str]],
                  **kwargs) -> Dict[str, Any]:
        """
        Genera una respuesta basada en mensajes de chat.
        
        Args:
            messages: Lista de mensajes en formato {role, content}
            **kwargs: Parámetros adicionales específicos del modelo
            
        Returns:
            Dict[str, Any]: Respuesta generada con metadatos
        """
        pass