"""
Implementación del proveedor de embeddings OpenAI.

Este módulo proporciona una implementación completa y autónoma del 
proveedor de embeddings OpenAI, siguiendo los estándares del proyecto
para manejo de errores, caché y contexto.

Modelos soportados:
- text-embedding-3-small: 1536 dimensiones, ideal para casos de uso general.
  Recomendado como opción predeterminada por su balance costo/rendimiento.
- text-embedding-3-large: 3072 dimensiones, mayor precisión para tareas complejas.
  Recomendado para aplicaciones donde se necesita máxima precisión.

Referencias:
- https://platform.openai.com/docs/guides/embeddings
- https://openai.com/blog/new-embedding-models-and-api-updates
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
# Importamos el contador de tokens desde el módulo local
from utils.token_counters import count_embedding_tokens as count_tokens

# Importar configuración centralizada
from config.settings import get_settings
from config.constants import EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_DIMENSION, TIMEOUTS

logger = logging.getLogger(__name__)
settings = get_settings()

# Constantes para modelos de OpenAI
# Referencia actualizada: https://platform.openai.com/docs/models/embeddings
OPENAI_EMBEDDING_MODELS = {
    "text-embedding-3-small": {
        "dimensions": 1536,
        "max_tokens": 8191,        # Límite de tokens por solicitud
        "max_batch_size": 2048,     # Máximo número de textos por lote
        "input_cost": 0.00002,      # Costo por 1K tokens de entrada ($0.00002/1K tokens)
        "tiers": ["free", "standard", "pro", "business", "enterprise"],
        "description": "Modelo de embeddings para uso general con excelente balance rendimiento/costo"
    },
    "text-embedding-3-large": {
        "dimensions": 3072,
        "max_tokens": 8191,        # Límite de tokens por solicitud
        "max_batch_size": 2048,     # Máximo número de textos por lote
        "input_cost": 0.00013,      # Costo por 1K tokens de entrada ($0.00013/1K tokens)
        "tiers": ["pro", "business", "enterprise"],
        "description": "Modelo de alta precisión para tareas complejas que requieren máxima fidelidad"
    }
    # El modelo text-embedding-ada-002 ha sido eliminado de la implementación activa
    # pero se mantiene compatibilidad con dimensiones en constants.py
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

def estimate_openai_tokens(text: str, model_name: str = "text-embedding-3-small") -> int:
    """
    Estima la cantidad de tokens en un texto para los modelos de OpenAI.
    
    Args:
        text: Texto para estimar tokens
        model_name: Nombre del modelo de embedding (por defecto: text-embedding-3-small)
        
    Returns:
        int: Cantidad estimada de tokens
    """
    # Usamos la función especializada de conteo de tokens para embeddings
    from utils.token_counters import count_embedding_tokens
    return count_embedding_tokens(text, model_name)

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
    
    Implementación optimizada para los modelos text-embedding-3-small y text-embedding-3-large.
    Soporta context tracking, caché y manejo estandarizado de errores según los estándares del proyecto.
    
    Args:
        text: Texto para generar el embedding
        model: Modelo a utilizar (text-embedding-3-small o text-embedding-3-large)
        api_key: API key para OpenAI (opcional, si no se proporciona usa la configuración global)
        tenant_id: ID del tenant (para contexto multitenancy y tracking)
        collection_id: ID de la colección (para caché y tracking)
        document_id: ID del documento (para caché y tracking)
        chunk_id: ID del chunk (para caché y tracking)
        ctx: Contexto proporcionado por el decorador with_context
        
    Returns:
        Tuple[List[float], Dict[str, Any]]: 
            - Vector de embedding (1536 dimensiones para small, 3072 para large)
            - Metadatos del proceso (modelo, tokens, latencia, origen)
            
    Raises:
        OpenAIAuthenticationError: Error de autenticación (API key inválida o faltante)
        OpenAIRateLimitError: Se excedió el límite de tasa de la API
        OpenAIModelNotFoundError: El modelo solicitado no existe o no está disponible
        OpenAIEmbeddingError: Otros errores en la generación de embeddings (red, formato, etc.)
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
    
    # Calcular tokens para tracking usando el modelo específico
    tokens = estimate_openai_tokens(text, model)
    
    try:
        # Preparar request para la API de OpenAI
        # Cabeceras estándar para la API de OpenAI
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key_to_use}",
            "OpenAI-Organization": settings.openai_org_id if hasattr(settings, 'openai_org_id') else None,
            "User-Agent": "Nooble/EmbeddingService"
        }
        # Eliminar valores None de las cabeceras
        headers = {k: v for k, v in headers.items() if v is not None}
        
        # Configuración optimizada para modelos text-embedding-3-*
        # Referencia: https://platform.openai.com/docs/api-reference/embeddings/create
        payload = {
            "input": text,
            "model": model,
            "encoding_format": "float",   # Formato estándar para vectores (alternativa: 'base64')
            "dimensions": OPENAI_EMBEDDING_MODELS.get(model, {}).get("dimensions", None)  # Opcional: usar las dimensiones del modelo
        }
        
        # Eliminar parámetros None del payload
        payload = {k: v for k, v in payload.items() if v is not None}
        
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
                    
                    # Determinar si los tokens vienen de la API o son estimados
                    api_prompt_tokens = usage.get("prompt_tokens", 0)
                    api_total_tokens = usage.get("total_tokens", 0)
                    
                    # Determinar la fuente de los datos de tokens
                    token_source = "api" if "usage" in result and api_prompt_tokens > 0 else "estimated"
                    
                    # Usar valores de la API si están disponibles, sino usar estimados
                    prompt_tokens = api_prompt_tokens if api_prompt_tokens > 0 else tokens
                    total_tokens = api_total_tokens if api_total_tokens > 0 else tokens
                    
                    # Si no hay tokens reportados pero tenemos texto, asegurarnos de usar la estimación
                    if total_tokens == 0 and text:
                        # Ya tenemos tokens estimados en la variable 'tokens'
                        total_tokens = tokens
                        prompt_tokens = tokens  # En embeddings, prompt_tokens == total_tokens
                        token_source = "estimated"
                    
                    # Generar hash del texto para identificar el embedding (para idempotencia)
                    from hashlib import md5
                    text_hash = md5(text.encode()).hexdigest()[:10]
                    
                    # Registrar uso de tokens si hay un tenant_id válido
                    if tenant_id and tenant_id != "default" and total_tokens > 0:
                        # Crear metadata enriquecida para el tracking
                        tracking_metadata = {
                            "service": "embedding-service", 
                            "provider": "openai",
                            "token_source": token_source,
                            "text_hash": text_hash,
                            "text_length": len(text),
                            "embedding_dimension": len(embedding) if embedding else dimensions
                        }
                        
                        # Añadir IDs relevantes si están disponibles
                        if collection_id:
                            tracking_metadata["collection_id"] = collection_id
                        if document_id:
                            tracking_metadata["document_id"] = document_id
                        if chunk_id:
                            tracking_metadata["chunk_id"] = chunk_id
                        
                        await track_token_usage(
                            tenant_id=tenant_id,
                            tokens=total_tokens,
                            model=model,
                            token_type=TOKEN_TYPE_EMBEDDING,
                            operation=OPERATION_EMBEDDING,
                            metadata=tracking_metadata,
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
                        "input_tokens": tokens,
                        "token_source": token_source
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
        Genera un embedding para una consulta usando el modelo OpenAI configurado.
        
        Implementa el patrón Cache-Aside unificado siguiendo los estándares del proyecto:
        1. Usa generate_resource_id_hash para generar claves consistentes
        2. Implementa get_with_cache_aside para el patrón completo
        3. Utiliza los TTLs estandarizados (ttl_extended = 24 horas para embeddings)
        4. Integra con el sistema de tracking mediante idempotency_key
        
        Args:
            text: Texto para generar el embedding
            tenant_id: ID del tenant (puede obtenerse del contexto si es None)
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[float]: Vector de embedding (1536 o 3072 dimensiones según el modelo)
        """
        # Resolver tenant_id desde el contexto si no se proporciona
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(validate=False)
        
        # Si el texto está vacío, devolver vector de ceros inmediatamente (optimización)
        if not text or text.strip() == "":
            return [0.0] * self.dimensions
        
        # Generar clave de caché para el embedding siguiendo el estándar del proyecto
        from common.cache import generate_resource_id_hash
        cache_key = generate_resource_id_hash(text)
        
        # Función de generación para el patrón Cache-Aside
        async def fetch_embedding():
            embedding, _ = await get_openai_embedding(
                text=text,
                model=self.model,
                api_key=self.api_key,
                tenant_id=tenant_id,
                ctx=ctx
            )
            return embedding
        
        # Usar TTL estandarizado para embeddings (24 horas)
        # Referencia: ver CacheManager.ttl_extended en las memorias del proyecto
        ttl = CacheManager.ttl_extended
        
        # Implementar el patrón Cache-Aside siguiendo el estándar unificado
        # Referencia: ver la memoria "Guía de Implementación de Caché Unificada"
        embedding, metrics = await get_with_cache_aside(
            data_type="embedding",
            resource_id=cache_key,
            tenant_id=tenant_id,
            fetch_from_db_func=None,  # No se requiere persistencia en BD para embeddings
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
        Genera embeddings para múltiples documentos utilizando el modelo OpenAI configurado.
        
        Implementa el patrón Cache-Aside unificado para cada documento individual, permitiendo:
        1. Caché eficiente por documento con keys basadas en el hash del contenido
        2. Tracking de uso con metadatos enriquecidos por colección/documento/chunk
        3. Manejo optimizado de casos especiales (textos vacíos, lotes grandes)
        4. Compatibilidad con los estándares multitenancy del sistema
        
        Args:
            texts: Lista de textos para generar embeddings
            tenant_id: ID del tenant (puede obtenerse del contexto si es None)
            collection_id: ID de la colección para tracking y metadatos de caché
            document_id: ID del documento para tracking y metadatos de caché
            chunk_ids: Lista de IDs de chunks correspondientes a cada texto
            ctx: Contexto proporcionado por el decorador with_context
            
        Returns:
            List[List[float]]: Lista de vectores de embedding (1536 o 3072 dimensiones según modelo)
            
        Note:
            Este método procesa documentos de forma individual para maximizar los hits de caché.
            Para operaciones realmente masivas con texto nuevo, considere usar la API de batch
            directamente para optimizar costos y rendimiento.
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
        
        # Optimización: primero dividir entre textos vacíos y no vacíos para procesamiento eficiente
        empty_indices = [i for i, text in enumerate(texts) if not text.strip()]
        non_empty_indices = [i for i, text in enumerate(texts) if text.strip()]
        
        # Inicializar lista para todos los embeddings
        embeddings = [None] * len(texts)
        
        # Asignar vectores de ceros para textos vacíos (optimización inmediata sin caché)
        for i in empty_indices:
            embeddings[i] = [0.0] * self.dimensions
        
        # Procesar los textos no vacíos con caché
        if non_empty_indices:
            # Usar semáforo para limitar procesamiento paralelo y evitar saturación
            import asyncio
            semaphore = asyncio.Semaphore(20)  # Máximo de 20 peticiones simultáneas para evitar sobrecarga
            
            async def process_text(index):
                # Obtener el texto y su chunk_id asociado si existe
                text = texts[index]
                chunk_id = chunk_ids[index] if chunk_ids and index < len(chunk_ids) else None
                
                # Control de concurrencia
                async with semaphore:
                    # Generar clave de caché según el estándar del proyecto
                    cache_key = generate_resource_id_hash(text)
                    
                    # Definir función para generación bajo demanda
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
                    
                    # Usar el patrón Cache-Aside unificado como se define en las memorias del proyecto
                    embedding, _ = await get_with_cache_aside(
                        data_type="embedding",
                        resource_id=cache_key,
                        tenant_id=tenant_id,
                        fetch_from_db_func=None,  # No se requiere persistencia en DB
                        generate_func=fetch_embedding,
                        ttl=CacheManager.ttl_extended  # 24 horas para embeddings según estándar
                    )
                    
                    # Guardar el embedding en su posición original
                    embeddings[index] = embedding
            
            # Crear y ejecutar tareas para procesar todos los embeddings en paralelo
            # pero controlando la concurrencia con el semáforo
            tasks = [process_text(i) for i in non_empty_indices]
            await asyncio.gather(*tasks)
        
        return embeddings
