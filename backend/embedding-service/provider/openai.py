"""
Proveedor simple de embeddings usando OpenAI.
Implementación directa y simple.
"""

import logging
import aiohttp
from typing import List, Dict, Any, Optional

from common.errors import ServiceError
from common.tracking import track_token_usage
from config.settings import get_settings, OPENAI_MODELS

logger = logging.getLogger(__name__)
settings = get_settings()

class OpenAIEmbeddingProvider:
    """Proveedor simple de embeddings usando OpenAI."""
    
    def __init__(self, model: str = None):
        self.model = model or settings.default_embedding_model
        self.api_key = settings.openai_api_key
        self.api_url = "https://api.openai.com/v1/embeddings"
        
    async def generate_embeddings(
        self,
        texts: List[str],
        tenant_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Genera embeddings para una lista de textos.
        
        Returns:
            Dict con 'embeddings' y 'usage'
        """
        # Filtrar textos vacíos
        non_empty_texts = [t for t in texts if t.strip()]
        if not non_empty_texts:
            return {
                "embeddings": [[0.0] * self._get_dimensions() for _ in texts],
                "usage": {"total_tokens": 0}
            }
        
        # Preparar request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "input": non_empty_texts,
            "model": self.model,
            "encoding_format": "float"
        }
        
        # Hacer request a OpenAI
        timeout = aiohttp.ClientTimeout(total=settings.openai_timeout_seconds)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        raise ServiceError(
                            f"OpenAI API error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                        )
                    
                    result = await response.json()
                    
                    # Extraer embeddings
                    embeddings_data = result.get("data", [])
                    embeddings = [item["embedding"] for item in embeddings_data]
                    
                    # Reconstruir lista completa (incluyendo vectores cero para textos vacíos)
                    full_embeddings = []
                    non_empty_idx = 0
                    
                    for text in texts:
                        if text.strip():
                            full_embeddings.append(embeddings[non_empty_idx])
                            non_empty_idx += 1
                        else:
                            full_embeddings.append([0.0] * self._get_dimensions())
                    
                    # Tracking de tokens
                    usage = result.get("usage", {})
                    total_tokens = usage.get("total_tokens", 0)
                    
                    if total_tokens > 0:
                        await track_token_usage(
                            tenant_id=tenant_id,
                            tokens=total_tokens,
                            model=self.model,
                            token_type="embedding",
                            operation="generate",
                            metadata={
                                "batch_size": len(texts),
                                "non_empty_texts": len(non_empty_texts)
                            }
                        )
                    
                    return {
                        "embeddings": full_embeddings,
                        "usage": usage
                    }
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error calling OpenAI: {str(e)}")
            raise ServiceError(f"Error de red con OpenAI: {str(e)}")
        except Exception as e:
            if isinstance(e, ServiceError):
                raise
            logger.error(f"Unexpected error: {str(e)}")
            raise ServiceError(f"Error generando embeddings: {str(e)}")
    
    def _get_dimensions(self) -> int:
        """Obtiene las dimensiones del modelo actual."""
        model_info = OPENAI_MODELS.get(self.model, OPENAI_MODELS["text-embedding-3-small"])
        return model_info["dimensions"]
