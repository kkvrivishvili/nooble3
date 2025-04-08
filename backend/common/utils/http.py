"""
Funciones para comunicación HTTP entre servicios.
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional

import httpx

from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id
from ..context.propagation import add_context_to_headers, Context
from ..errors.exceptions import ServiceError

logger = logging.getLogger(__name__)

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

async def prepare_service_request(
    url: str, 
    data: Dict[str, Any], 
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    operation_type: str = "default"
) -> Dict[str, Any]:
    """
    Prepara una solicitud HTTP entre servicios con el contexto completo.
    
    Args:
        url: URL del servicio
        data: Datos a enviar
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        agent_id: ID del agente (opcional, usa el contexto actual si no se especifica)
        conversation_id: ID de la conversación (opcional, usa el contexto actual si no se especifica)
        collection_id: ID de la colección (opcional, usa el contexto actual si no se especifica)
        operation_type: Tipo de operación para determinar el timeout
        
    Returns:
        Dict con los datos de la respuesta
    """
    # Obtener valores del contexto actual si no se proporcionan explícitamente
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    
    # Asegurar que tenant_id esté incluido en los datos
    if "tenant_id" not in data and tenant_id:
        data["tenant_id"] = tenant_id
    
    # Añadir reintentos y timeout variable
    max_retries = 3
    base_timeout = get_timeout_for_operation(operation_type)
    retry_count = 0
    
    # Crear headers con el contexto actual
    headers = {}
    headers = add_context_to_headers(headers)
    
    while retry_count < max_retries:
        try:
            timeout = base_timeout * (retry_count + 1)
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.debug(f"Enviando solicitud a {url} con contexto: {headers}")
                
                response = await client.post(url, json=data, headers=headers)
                
                # Verificar respuesta
                if response.status_code != 200:
                    logger.error(f"Error en solicitud a {url}: {response.status_code} - {response.text}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise ServiceError(f"Error en solicitud: {response.status_code} - {response.text}")
                    logger.warning(f"Reintentando solicitud ({retry_count}/{max_retries})...")
                    await asyncio.sleep(1.0 * retry_count)  # Backoff lineal
                    continue
                    
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error HTTP en solicitud a {url}: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                raise ServiceError(f"Error de conexión: {str(e)}")
            logger.warning(f"Reintentando solicitud ({retry_count}/{max_retries})...")
            await asyncio.sleep(1.0 * retry_count)
        except Exception as e:
            logger.error(f"Error al enviar solicitud a {url}: {str(e)}")
            raise ServiceError(f"Error en solicitud: {str(e)}")


async def call_service_with_context(
    url: str,
    data: Dict[str, Any],
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    timeout: Optional[float] = None,
    operation_type: str = "default"
) -> Dict[str, Any]:
    """
    Llama a otro servicio preservando el contexto actual de ejecución.
    
    Args:
        url: URL del servicio a llamar
        data: Datos de la solicitud
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        agent_id: ID del agente (opcional, usa el contexto actual si no se especifica)
        conversation_id: ID de la conversación (opcional, usa el contexto actual si no se especifica)
        collection_id: ID de la colección (opcional, usa el contexto actual si no se especifica)
        timeout: Timeout personalizado (opcional)
        operation_type: Tipo de operación para determinar timeout automático
        
    Returns:
        Dict: Respuesta del servicio
    """
    # Usar el contexto actual si no se proporcionan parámetros específicos
    tenant_id = tenant_id or get_current_tenant_id()
    agent_id = agent_id or get_current_agent_id()
    conversation_id = conversation_id or get_current_conversation_id()
    
    # Determinar timeout adecuado
    if timeout is None:
        timeout = get_timeout_for_operation(operation_type)
    
    # Crear el cliente HTTP con timeout adecuado
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Crear headers con el contexto completo
        headers = {}
        ctx = Context(tenant_id, agent_id, conversation_id, collection_id)
        async with ctx:
            headers = add_context_to_headers(headers)
        
        # Realizar la solicitud con reintentos
        for attempt in range(3):
            try:
                logger.debug(f"Llamando a servicio {url} con contexto: {headers}")
                response = await client.post(url, json=data, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.warning(f"Error HTTP {e.response.status_code} llamando a {url} (intento {attempt+1}/3)")
                if attempt == 2:  # Último intento
                    raise ServiceError(f"Error llamando al servicio: {str(e)}")
                await asyncio.sleep(1 * (attempt + 1))  # Backoff lineal
            except Exception as e:
                logger.error(f"Error llamando a {url}: {str(e)}")
                raise ServiceError(f"Error llamando al servicio: {str(e)}")


async def check_service_health(service_url: str, service_name: str, timeout: float = 5.0) -> bool:
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
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(health_url)
            is_healthy = response.status_code == 200
            if not is_healthy:
                logger.warning(f"Health check fallido para {service_name} en {health_url}: Status {response.status_code}")
            return is_healthy
    except httpx.TimeoutException:
        logger.warning(f"Health check timeout para {service_name} en {health_url}")
        return False
    except httpx.RequestError as e:
        logger.warning(f"Error de conexión en health check para {service_name} en {health_url}: {e.__class__.__name__}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado en health check para {service_name} en {health_url}: {str(e)}")
        return False