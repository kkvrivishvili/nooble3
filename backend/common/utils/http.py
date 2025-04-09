"""
Funciones para comunicación HTTP entre servicios.

Este módulo proporciona funcionalidad estandarizada para la comunicación
entre los diferentes microservicios del backend, garantizando:
- Propagación de contexto (tenant, agent, conversation, collection)
- Reintentos automáticos con backoff
- Timeouts adaptados al tipo de operación
- Formato de respuesta estandarizado
- Integración opcional con el sistema de caché
"""

import logging
import asyncio
import time
import json
from typing import Dict, Any, Optional, List, Union

import httpx

from ..context.vars import (
    get_current_tenant_id, 
    get_current_agent_id, 
    get_current_conversation_id,
    get_current_collection_id
)
from ..context.propagation import add_context_to_headers, Context
from ..errors.exceptions import (
    ServiceError, ErrorCode,
    CommunicationError, ServiceUnavailableError, 
    AuthenticationError, AuthorizationError,
    TimeoutError, RateLimitError
)
from ..cache.manager import CacheManager

logger = logging.getLogger(__name__)

# Constantes para comunicación entre servicios
SERVICE_RESPONSE_FIELDS = ["success", "message", "data", "metadata", "error"]

def get_timeout_for_operation(operation_type: str) -> float:
    """
    Determina el timeout adecuado según el tipo de operación.
    
    Args:
        operation_type: Tipo de operación
        
    Returns:
        float: Timeout en segundos
    """
    timeouts = {
        "default": 60.0,         # Default para la mayoría de operaciones
        "rag_query": 120.0,      # Consultas RAG (más intensivas)
        "embedding": 60.0,       # Generación de embeddings
        "llm_generation": 120.0, # Generación de texto con LLM
        "health_check": 5.0      # Verificaciones de salud (deben ser rápidas)
    }
    return timeouts.get(operation_type, timeouts["default"])

def standardize_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Estandariza el formato de respuesta para asegurar consistencia.
    
    Args:
        response_data: Datos de respuesta del servicio
        
    Returns:
        Dict: Respuesta en formato estándar
    """
    # Si ya tiene el formato estándar, retornar sin cambios
    if all(field in response_data for field in ["success", "message"]):
        return response_data
    
    # Convertir a formato estándar
    result = {
        "success": True,  # Asumimos éxito si llegamos aquí
        "message": "Operación completada correctamente",
        "data": response_data,
        "metadata": {}
    }
    
    # Si la respuesta original ya tenía algunos campos estándar, preservarlos
    for field in SERVICE_RESPONSE_FIELDS:
        if field in response_data and field != "data":
            result[field] = response_data[field]
            if field == "data":
                # Evitar anidamiento excesivo de 'data'
                continue
    
    return result

def create_error_response(error_message: str, error_details: Any = None) -> Dict[str, Any]:
    """
    Crea una respuesta de error en formato estándar.
    
    Args:
        error_message: Mensaje descriptivo del error
        error_details: Detalles adicionales del error (opcional)
        
    Returns:
        Dict: Respuesta de error en formato estándar
    """
    # Si ya recibimos un error específico ServiceError, usarlo directamente
    if isinstance(error_message, ServiceError):
        specific_error = error_message
        error_message = specific_error.message
    # De lo contrario, convertir a CommunicationError genérico
    else:
        specific_error = CommunicationError(
            message=error_message,
            details=error_details
        )
    
    return {
        "success": False,
        "message": error_message,
        "data": None,
        "metadata": {},
        "error": {
            "message": error_message,
            "details": error_details or {},
            "error_code": getattr(specific_error, "error_code", ErrorCode.COMMUNICATION_ERROR),
            "timestamp": time.time()
        }
    }

async def call_service(
    url: str,
    data: Dict[str, Any],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    operation_type: str = "default",
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    custom_timeout: Optional[float] = None,
    use_cache: bool = False,
    cache_ttl: Optional[int] = None
) -> Dict[str, Any]:
    """
    Función unificada para la comunicación entre servicios.
    
    Args:
        url: URL del servicio a llamar
        data: Datos de la solicitud
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        agent_id: ID del agente (opcional, usa el contexto actual si no se especifica)
        conversation_id: ID de la conversación (opcional, usa el contexto actual si no se especifica)
        collection_id: ID de la colección (opcional, usa el contexto actual si no se especifica)
        operation_type: Tipo de operación para determinar timeout
        headers: Headers HTTP adicionales
        max_retries: Número máximo de reintentos
        custom_timeout: Timeout personalizado (opcional)
        use_cache: Si se debe utilizar caché para esta llamada
        cache_ttl: Tiempo de vida en segundos para la caché (si use_cache=True)
        
    Returns:
        Dict: Respuesta del servicio en formato estándar
    """
    # Usar contexto actual si no se proporcionan parámetros específicos
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    collection_id = collection_id or get_current_collection_id()
    
    # Determinar timeout adecuado
    timeout = custom_timeout or get_timeout_for_operation(operation_type)
    
    # Crear headers con el contexto completo
    request_headers = headers or {}
    ctx = Context(tenant_id, agent_id, conversation_id, collection_id)
    async with ctx:
        request_headers = add_context_to_headers(request_headers)
    
    # Asegurar que tenant_id esté incluido en los datos
    if "tenant_id" not in data and tenant_id:
        data["tenant_id"] = tenant_id
    
    # Verificar caché si está habilitado
    if use_cache and tenant_id:
        cache_key = f"service_call:{url}:{json.dumps(data, sort_keys=True)}"
        
        # Intentar obtener de caché
        cached_result = await CacheManager.get(
            data_type="service_call",
            resource_id=cache_key,
            tenant_id=tenant_id
        )
        
        if cached_result:
            logger.debug(f"Resultado obtenido de caché para llamada a {url}")
            return cached_result
    
    # Realizar la solicitud con reintentos
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                logger.debug(f"Llamando a servicio {url} (intento {attempt+1}/{max_retries})")
                response = await client.post(url, json=data, headers=request_headers)
                response.raise_for_status()
                
                # Convertir respuesta a formato estándar
                result = standardize_response(response.json())
                
                # Guardar en caché si está habilitado
                if use_cache and tenant_id and result["success"]:
                    await CacheManager.set(
                        data_type="service_call",
                        resource_id=cache_key,
                        value=result,
                        tenant_id=tenant_id,
                        ttl=cache_ttl or 300  # Default: 5 minutos
                    )
                
                return result
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"Error HTTP {e.response.status_code} llamando a {url}")
                
                # Si tenemos una respuesta JSON, preservarla
                error_details = None
                try:
                    error_details = e.response.json()
                except:
                    error_details = {"status_code": e.response.status_code, "text": e.response.text}
                
                if attempt == max_retries - 1:  # Último intento
                    # Determinar el tipo específico de error según el código de estado HTTP
                    specific_error = None
                    
                    if e.response.status_code == 401:
                        specific_error = AuthenticationError(
                            message=f"Error de autenticación llamando al servicio: {url}",
                            details=error_details
                        )
                    elif e.response.status_code == 403:
                        specific_error = AuthorizationError(
                            message=f"Error de autorización llamando al servicio: {url}",
                            details=error_details
                        )
                    elif e.response.status_code == 429:
                        specific_error = RateLimitError(
                            message=f"Límite de tasa excedido llamando al servicio: {url}",
                            details=error_details
                        )
                    elif e.response.status_code >= 500:
                        specific_error = ServiceUnavailableError(
                            message=f"Servicio no disponible: {url}",
                            details=error_details
                        )
                    else:
                        specific_error = CommunicationError(
                            message=f"Error HTTP {e.response.status_code} llamando al servicio: {url}",
                            details=error_details
                        )
                        
                    error_response = create_error_response(specific_error, error_details)
                    return error_response
                
                await asyncio.sleep(1 * (attempt + 1))  # Backoff lineal
                
            except httpx.TimeoutException as e:
                logger.error(f"Timeout llamando a {url}: {str(e)}")
                
                if attempt == max_retries - 1:  # Último intento
                    specific_error = TimeoutError(
                        message=f"Timeout al llamar al servicio: {url}",
                        details={"operation_type": operation_type, "timeout": timeout}
                    )
                    error_response = create_error_response(specific_error, None)
                    return error_response
                
                # Incrementar timeout para el siguiente intento
                timeout = min(timeout * 1.5, 60.0)  # Máximo 60 segundos
                await asyncio.sleep(1 * (attempt + 1))  # Backoff lineal
                
            except Exception as e:
                logger.error(f"Error llamando a {url}: {str(e)}")
                
                if attempt == max_retries - 1:  # Último intento
                    specific_error = CommunicationError(
                        message=f"Error llamando al servicio: {url}",
                        details={"error_type": e.__class__.__name__, "error_message": str(e)}
                    )
                    error_response = create_error_response(specific_error, None)
                    return error_response
                
                await asyncio.sleep(1 * (attempt + 1))  # Backoff lineal

async def check_service_health(
    service_url: str, 
    service_name: str, 
    timeout: float = 5.0
) -> bool:
    """
    Verifica la disponibilidad de un servicio haciendo un GET a su endpoint /health.
    
    Args:
        service_url: URL base del servicio.
        service_name: Nombre del servicio (para logging).
        timeout: Timeout en segundos para la solicitud.
        
    Returns:
        bool: True si el servicio responde con 200 OK, False en caso contrario.
    """
    health_url = f"{service_url.rstrip('/')}/health"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(health_url, timeout=timeout)
            
        if response.status_code == 200:
            logger.info(f"Servicio {service_name} disponible en {health_url}")
            return True
        else:
            logger.warning(
                f"Servicio {service_name} respondió con status {response.status_code}"
            )
            return False
    except Exception as e:
        logger.error(f"Error verificando salud de {service_name}: {str(e)}")
        return False

# Funciones heredadas eliminadas - todos los servicios deben usar call_service