"""
Implementación del proveedor de embeddings OpenAI.

Este módulo proporciona una implementación completa y autónoma del 
proveedor de embeddings OpenAI, siguiendo los estándares del proyecto
para manejo de errores, caché y contexto.
"""

import logging
import json
import time
import aiohttp
from typing import Dict, List, Any, Tuple, Optional, Union

# Importaciones para manejo de errores estándar
from common.errors import ServiceError, ErrorCode, handle_errors
from common.context import with_context, Context
from common.tracking import track_token_usage, TOKEN_TYPE_EMBEDDING
from common.tracking import OPERATION_EMBEDDING
from common.config.tiers import get_embedding_model_details, get_available_embedding_models
from common.cache.helpers import get_with_cache_aside, standardize_llama_metadata
from common.cache.manager import CacheManager
from common.llm.token_counters import count_tokens

# Importar configuración centralizada
from config.settings import get_settings
from config.constants import EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_DIMENSION, TIMEOUTS

logger = logging.getLogger(__name__)
settings = get_settings()

# Constantes para modelos de OpenAI
OPENAI_EMBEDDING_MODELS = {
    "text-embedding-3-small": {
        "dimensions": 1536,
        "max_tokens": 8191,
        "tiers": ["free", "standard", "pro", "business", "enterprise"]
    },
    "text-embedding-3-large": {
        "dimensions": 3072,
        "max_tokens": 8191,
        "tiers": ["pro", "business", "enterprise"]
    },
    "text-embedding-ada-002": {  # Legacy model
        "dimensions": 1536,
        "max_tokens": 8191,
        "tiers": ["standard", "premium", "free"],
        "deprecated": True
    }
}

# Errores específicos para OpenAI que siguen el estándar del proyecto
class OpenAIEmbeddingError(ServiceError):
    """Error base para operaciones con OpenAI Embeddings."""
    def __init__(self, message: str, code: str = ErrorCode.EXTERNAL_SERVICE_ERROR):
        super().__init__(message=message, code=code)

class OpenAIAuthenticationError(OpenAIEmbeddingError):
    """Error de autenticación con la API de OpenAI."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.AUTHORIZATION_ERROR)

class OpenAIRateLimitError(OpenAIEmbeddingError):
    """Error de límite de tasa con la API de OpenAI."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.RATE_LIMIT_EXCEEDED)

class OpenAIModelNotFoundError(OpenAIEmbeddingError):
    """Error cuando el modelo solicitado no está disponible."""
    def __init__(self, message: str):
        super().__init__(message=message, code=ErrorCode.MODEL_NOT_FOUND_ERROR)

def is_openai_embedding_model(model_name: str) -> bool:
    """
    Verifica si un modelo es un modelo de embedding de OpenAI soportado.
    
    Args:
        model_name: Nombre del modelo a verificar
        
    Returns:
        bool: True si es un modelo de embedding de OpenAI, False en caso contrario
    """
    if not model_name:
        return False
        
    model_name_lower = model_name.lower()
    return any(model.lower() in model_name_lower for model in OPENAI_EMBEDDING_MODELS.keys())

def estimate_openai_tokens(text: str) -> int:
    """
    Estima la cantidad de tokens en un texto para los modelos de OpenAI.
    
    Args:
        text: Texto para estimar tokens
        
    Returns:
        int: Cantidad estimada de tokens
    """
    return count_tokens(text)

async def get_openai_config(tenant_id: str, model_name: str) -> Tuple[str, str]:
    """
    Obtiene la configuración de OpenAI para embeddings.
    
    Args:
        tenant_id: ID del tenant
        model_name: Nombre del modelo de embedding
        
    Returns:
        Tuple[str, str]: API key y endpoint para OpenAI
    """
    # Usar la API key de OpenAI configurada
    api_key = settings.openai_api_key
    
    # Endpoint de OpenAI para embeddings
    endpoint = "https://api.openai.com/v1/embeddings"
    
    # Añadir lógica específica por tenant/modelo si es necesario en el futuro
    
    return api_key, endpoint

async def get_openai_embedding(
    text: str,
    model: str = "text-embedding-3-small", 
    api_key: Optional[str] = None,
    tenant_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    document_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
    ctx: Context = None
) -> Tuple[List[float], Dict[str, Any]]:
    """
    Genera un embedding utilizando la API de OpenAI.
    
    Args:
        text: Texto para generar el embedding
        model: Modelo a utilizar
        api_key: API key para OpenAI (opcional)
        tenant_id: ID del tenant
        collection_id: ID de la colección (para cache)
        document_id: ID del documento (para cache)
        chunk_id: ID del chunk (para cache)
        ctx: Contexto proporcionado por el decorador
        
    Returns:
        Tuple[List[float], Dict[str, Any]]: 
            - Vector de embedding
            - Metadatos del proceso
            
    Raises:
        OpenAIAuthenticationError: Si hay un error de autenticación
        OpenAIRateLimitError: Si se excede el límite de tasa
        OpenAIEmbeddingError: Si hay un error general con OpenAI
    """
    start_time = time.time()
    
    # Si no se proporciona tenant_id, intentar obtenerlo del contexto
    if not tenant_id and ctx:
        tenant_id = ctx.get_tenant_id(validate=False)
    
    # Por defecto, dimensiones para text-embedding-3-small
    dimensions = OPENAI_EMBEDDING_MODELS.get(model, {}).get("dimensions", DEFAULT_EMBEDDING_DIMENSION)
    
    # Si el texto está vacío, devolver vector de ceros
    if not text or text.strip() == "":
        return [0.0] * dimensions, {
            "model": model,
            "usage": {"total_tokens": 0, "prompt_tokens": 0},
            "latency": 0,
            "source": "generation",
            "input_tokens": 0
        }
    
    # Obtener configuración de OpenAI
    api_key_to_use, endpoint = await get_openai_config(tenant_id or "default", model)
    if api_key:
        api_key_to_use = api_key
    
    if not api_key_to_use:
        raise OpenAIAuthenticationError("API key de OpenAI no proporcionada o configurada")
    
    # Controlar tiempos límite
    timeout = aiohttp.ClientTimeout(total=TIMEOUTS.get("embedding_timeout", 30))
    
    # Calcular tokens para tracking
    tokens = estimate_openai_tokens(text)
    
    try:
        # Preparar request para la API de OpenAI
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key_to_use}"
        }
        
        payload = {
            "input": text,
            "model": model,
            "encoding_format": "float"
        }
        
        # Generar un ID idempotencia para evitar doble conteo
        import hashlib
        idempotency_key = hashlib.md5(f"{tenant_id}:{model}:{text}".encode()).hexdigest()
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, headers=headers, json=payload) as response:
                elapsed_time = time.time() - start_time
                
                if response.status == 200:
                    result = await response.json()
                    
                    # Obtener el embedding del resultado de OpenAI
                    # La estructura de respuesta de OpenAI es: {"data": [{"embedding": [...], ...}]}
                    if not result.get("data"):
                        raise OpenAIEmbeddingError("La API de OpenAI no devolvió datos de embedding válidos")
                    
                    embedding_data = result["data"][0]
                    if not embedding_data.get("embedding"):
                        raise OpenAIEmbeddingError("La API de OpenAI no devolvió un embedding válido")
                    
                    embedding = embedding_data["embedding"]
                    
                    # Capturar información de uso y tokens
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", tokens)
                    total_tokens = usage.get("total_tokens", tokens)
                    
                    # Registrar uso de tokens si hay un tenant_id válido
                    if tenant_id and tenant_id != "default":
                        await track_token_usage(
                            tenant_id=tenant_id,
                            tokens=prompt_tokens,
                            model=model,
                            token_type=TOKEN_TYPE_EMBEDDING,
                            operation=OPERATION_EMBEDDING,
                            metadata={"service": "embedding-service", "collection_id": collection_id},
                            idempotency_key=idempotency_key
                        )
                    
                    # Metadatos estandarizados
                    metadata = {
                        "model": model,
                        "usage": {
                            "total_tokens": total_tokens,
                            "prompt_tokens": prompt_tokens
                        },
                        "latency": elapsed_time,
                        "source": "generation",
                        "input_tokens": tokens
                    }
                    
                    # Estandarizar los metadatos para el formato LlamaIndex
                    if tenant_id or collection_id or document_id or chunk_id:
                        metadata = standardize_llama_metadata(
                            metadata=metadata,
                            tenant_id=tenant_id,
                            document_id=document_id,
                            chunk_id=chunk_id,
                            collection_id=collection_id
                        )
                    
                    return embedding, metadata
                
                elif response.status == 401:
                    raise OpenAIAuthenticationError("Error de autenticación con la API de OpenAI")
                
                elif response.status == 429:
                    raise OpenAIRateLimitError("Se ha excedido el límite de tasa de la API de OpenAI")
                
                elif response.status == 404:
                    raise OpenAIModelNotFoundError(f"Modelo de embedding no encontrado: {model}")
                
                else:
                    # Para otros errores, intentar obtener el mensaje de error
                    try:
                        error_data = await response.json()
                        error_message = error_data.get("error", {}).get("message", "")
                        error_type = error_data.get("error", {}).get("type", "")
                        error_msg = f"Error de OpenAI ({response.status}): {error_type} - {error_message}"
                    except:
                        error_msg = f"Error desconocido de OpenAI (HTTP {response.status})"
                    
                    # Mejorar el contexto del error
                    error_context = {
                        "status_code": response.status,
                        "model": model,
                        "tenant_id": tenant_id,
                        "latency": elapsed_time
                    }
                    
                    logger.error(error_msg, extra=error_context)
                    raise OpenAIEmbeddingError(error_msg)
    
    except aiohttp.ClientError as e:
        error_msg = f"Error de conexión con la API de OpenAI: {str(e)}"
        logger.error(error_msg, extra={"model": model, "tenant_id": tenant_id})
        raise OpenAIEmbeddingError(error_msg) from e
    
    except Exception as e:
        if isinstance(e, OpenAIEmbeddingError):
            raise e
        
        error_msg = f"Error al generar embedding con OpenAI: {str(e)}"
        logger.error(error_msg, extra={"model": model, "tenant_id": tenant_id})
        raise OpenAIEmbeddingError(error_msg) from e

class OpenAIEmbeddingProvider:
    """
    Proveedor de embeddings de OpenAI.
    
    Esta clase proporciona una interfaz para generar embeddings utilizando
    los modelos de OpenAI, con soporte para caché y tracking de tokens.
    """
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        dimensions: Optional[int] = None,
        **kwargs
    ):
        """
        Inicializa el proveedor de embeddings de OpenAI.
        
        Args:
            model: Modelo de embedding a utilizar
            api_key: API key para OpenAI (opcional)
            dimensions: Dimensiones del embedding (opcional)
            **kwargs: Parámetros adicionales
        """
        self.model = model
        self.api_key = api_key or settings.openai_api_key
        
        # Establecer dimensiones según el modelo o usar valor explícito
        if dimensions:
            self.dimensions = dimensions
        elif model in OPENAI_EMBEDDING_MODELS:
            self.dimensions = OPENAI_EMBEDDING_MODELS[model]["dimensions"]
        else:
            # Por defecto, dimensiones para text-embedding-3-small
            self.dimensions = DEFAULT_EMBEDDING_DIMENSION
        
        # Almacenar parámetros adicionales
        self.kwargs = kwargs
    
    @handle_errors(
        error_type="service", 
        log_traceback=True,
        error_map={
            OpenAIAuthenticationError: (ErrorCode.AUTHORIZATION_ERROR, 401),
            OpenAIRateLimitError: (ErrorCode.RATE_LIMIT_EXCEEDED, 429),
            OpenAIModelNotFoundError: (ErrorCode.MODEL_NOT_FOUND_ERROR, 404),
            OpenAIEmbeddingError: (ErrorCode.EXTERNAL_SERVICE_ERROR, 500)
        }
    )
    @with_context(tenant=True)
    async def embed_query(self, text: str, tenant_id: Optional[str] = None, ctx: Context = None) -> List[float]:
        """
        Genera un embedding para una consulta.
        
        Args:
            text: Texto para generar el embedding
            tenant_id: ID del tenant
            ctx: Contexto proporcionado por el decorador
            
        Returns:
            List[float]: Vector de embedding
        """
        # Resolver tenant_id desde el contexto si no se proporciona
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(validate=False)
        
        # Generar clave de caché para el embedding
        from common.cache import generate_resource_id_hash
        cache_key = generate_resource_id_hash(text)
        
        # Usar patrón Cache-Aside centralizado
        async def fetch_embedding():
            embedding, _ = await get_openai_embedding(
                text=text,
                model=self.model,
                api_key=self.api_key,
                tenant_id=tenant_id,
                ctx=ctx
            )
            return embedding
        
        # Obtener el TTL para embeddings
        ttl = CacheManager.ttl_extended  # 24 horas para embeddings
        
        # Usar el patrón Cache-Aside centralizado
        embedding, metrics = await get_with_cache_aside(
            data_type="embedding",
            resource_id=cache_key,
            tenant_id=tenant_id,
            fetch_from_db_func=None,  # Sin almacenamiento en BD
            generate_func=fetch_embedding,
            ttl=ttl
        )
        
        return embedding
    
    @handle_errors(
        error_type="service", 
        log_traceback=True,
        error_map={
            OpenAIAuthenticationError: (ErrorCode.AUTHORIZATION_ERROR, 401),
            OpenAIRateLimitError: (ErrorCode.RATE_LIMIT_EXCEEDED, 429),
            OpenAIModelNotFoundError: (ErrorCode.MODEL_NOT_FOUND_ERROR, 404),
            OpenAIEmbeddingError: (ErrorCode.EXTERNAL_SERVICE_ERROR, 500)
        }
    )
    @with_context(tenant=True)
    async def embed_documents(
        self, 
        texts: List[str], 
        tenant_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_ids: Optional[List[str]] = None,
        ctx: Context = None
    ) -> List[List[float]]:
        """
        Genera embeddings para múltiples documentos.
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant
            collection_id: ID de la colección (para cache)
            document_id: ID del documento (para cache)
            chunk_ids: Lista de IDs de chunks (para cache)
            ctx: Contexto proporcionado por el decorador
            
        Returns:
            List[List[float]]: Lista de vectores de embedding
        """
        # Resolver tenant_id desde el contexto si no se proporciona
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(validate=False)
        
        # Si no hay textos, devolver lista vacía
        if not texts:
            return []
        
        # Si los textos son solo espacios en blanco, devolver vectores de ceros
        if all(not text.strip() for text in texts):
            return [[0.0] * self.dimensions for _ in range(len(texts))]
        
        # Procesar cada texto individualmente para aprovechar la caché
        embeddings = []
        for i, text in enumerate(texts):
            # Determinar chunk_id para este texto si está disponible
            chunk_id = chunk_ids[i] if chunk_ids and i < len(chunk_ids) else None
            
            # Generar clave de caché para el embedding
            cache_key = generate_resource_id_hash(text)
            
            # Definir función para generar el embedding si no está en caché
            async def fetch_embedding():
                embedding, _ = await get_openai_embedding(
                    text=text,
                    model=self.model,
                    api_key=self.api_key,
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    ctx=ctx
                )
                return embedding
            
            # Obtener el TTL para embeddings
            ttl = CacheManager.ttl_extended  # 24 horas para embeddings
            
            # Usar el patrón Cache-Aside centralizado
            embedding, metrics = await get_with_cache_aside(
                data_type="embedding",
                resource_id=cache_key,
                tenant_id=tenant_id,
                fetch_from_db_func=None,  # Sin almacenamiento en BD
                generate_func=fetch_embedding,
                ttl=ttl
            )
            
            embeddings.append(embedding)
        
        return embeddings
