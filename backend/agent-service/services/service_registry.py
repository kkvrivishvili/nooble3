"""
Registro centralizado para servicios disponibles.

Este módulo permite la comunicación estandarizada con otros servicios del sistema,
implementando un cliente unificado con soporte para propagación de contexto, métricas
y gestión de fallos.
"""

import logging
import time
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union, TypeVar

from common.context import Context, with_context
from common.errors import handle_errors, ServiceError, HTTPServiceError
from common.utils.http import call_service
from common.cache import CacheManager
from common.tracking import track_operation_latency

from config import get_settings

from models import (
    ServiceType, ServiceConfig, RequestMethod, 
    ServiceRequest, ServiceResponse, ServiceRegistry as ServiceRegistryModel,
    ContextPayload, ContextManager
)

logger = logging.getLogger(__name__)

# Tipo genérico para función de caché
T = TypeVar('T')


class ServiceRegistry:
    """
    Registro centralizado para servicios disponibles.
    Proporciona acceso a los servicios de la plataforma utilizando modelos estandarizados
    y siguiendo patrones consistentes para propagación de contexto, caché y manejo de errores.
    """
    
    def __init__(self):
        """Inicializa el registro de servicios."""
        self.settings = get_settings()
        self.registry = ServiceRegistryModel()
        self._initialize_services()
        self._last_health_check = {}
        self._failed_health_checks = {}
        
    def _initialize_services(self):
        """Inicializa el registro con los servicios base de la plataforma."""
        # Registrar servicio de consulta (query)
        self.registry.register_service(ServiceConfig(
            service_name="query",
            service_type=ServiceType.QUERY,
            base_url=self.settings.query_service_url,
            timeout_seconds=30,
            retry_count=3,
            retry_backoff_factor=0.5,
            connection_pool_size=20,
            health_check_endpoint="/health",
            is_internal=True
        ))
        
        # Registrar servicio de embeddings
        self.registry.register_service(ServiceConfig(
            service_name="embedding",
            service_type=ServiceType.EMBEDDING,
            base_url=self.settings.embedding_service_url,
            timeout_seconds=60,  # Los embeddings pueden tardar más
            retry_count=2,
            retry_backoff_factor=1.0,
            connection_pool_size=10,
            health_check_endpoint="/health",
            is_internal=True
        ))
        
        # Registrar servicio de ingestión
        self.registry.register_service(ServiceConfig(
            service_name="ingestion",
            service_type=ServiceType.INGESTION,
            base_url=self.settings.ingestion_service_url,
            timeout_seconds=120,  # La ingestión puede tardar aún más
            retry_count=1,
            retry_backoff_factor=2.0,
            connection_pool_size=5,
            health_check_endpoint="/health",
            is_internal=True
        ))
    
    @handle_errors(error_type="service", log_traceback=True)
    async def call_service_with_context(
        self,
        service_name: str,
        endpoint: str,
        method: str = "POST",
        data: Dict[str, Any] = None,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        ctx: Optional[Context] = None,
        operation_type: str = "standard",
        use_cache: bool = True,
        cache_ttl: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Método centralizado para llamar a cualquier servicio con propagación de contexto.
        
        Args:
            service_name: Nombre del servicio a llamar
            endpoint: Endpoint a llamar
            method: Método HTTP
            data: Datos para enviar
            params: Parámetros de query string
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            collection_id: ID de la colección
            idempotency_key: Clave de idempotencia
            ctx: Contexto de la operación
            operation_type: Tipo de operación para timeout
            use_cache: Si se debe usar caché
            cache_ttl: TTL para caché en segundos
            
        Returns:
            Dict[str, Any]: Respuesta del servicio
        """
        # Obtener tenant_id del contexto si no se proporcionó
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(False)
            
        # Obtener configuración del servicio
        try:
            service_config = self.registry.get_service_config(service_name)
        except ValueError as e:
            raise ServiceError(f"Servicio no registrado: {service_name}") from e
            
        # Construir URL completa
        base_url = service_config.base_url
        url = f"{base_url}/{endpoint.lstrip('/')}"
        
        # Crear context payload para propagar
        context_payload = ContextPayload(
            tenant_id=tenant_id,
            user_id=ctx.get_user_id(False) if ctx else None,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            source_service="agent"
        )
        
        # Configurar gestor de contexto
        context_manager = ContextManager(
            context=context_payload
        )
        
        # Obtener headers con contexto propagado
        headers = context_manager.get_headers_for_propagation()
        
        # Añadir clave de idempotencia si se proporciona
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        
        # Crear clave para caché
        cache_key = f"{service_name}:{endpoint}:{method}"
        if idempotency_key:
            cache_key += f":{idempotency_key}"
            
        # Si se usa caché, intentar obtener de caché primero
        if use_cache and method.upper() in ["GET", "POST"] and tenant_id:
            # Usar patrón Cache-Aside para obtener respuesta
            start_time = time.time()
            try:
                response = await CacheManager.get_with_cache_aside(
                    data_type="service_response",
                    resource_id=cache_key,
                    fetch_function=lambda: self._make_actual_call(url, method, data, params, headers, operation_type),
                    tenant_id=tenant_id,
                    ttl=cache_ttl or CacheManager.ttl_short
                )
                
                # Registrar latencia
                latency_ms = int((time.time() - start_time) * 1000)
                await track_operation_latency(
                    operation_type=f"service_call_{service_name}",
                    latency_ms=latency_ms,
                    metadata={
                        "endpoint": endpoint,
                        "method": method,
                        "from_cache": True
                    }
                )
                
                return response
            except Exception as e:
                logger.warning(f"Error al obtener de caché: {str(e)}. Continuando con llamada directa.")
        
        # Si no se usa caché o falló, hacer la llamada directamente
        return await self._make_actual_call(url, method, data, params, headers, operation_type)
    
    async def _make_actual_call(
        self, 
        url: str, 
        method: str, 
        data: Optional[Dict[str, Any]], 
        params: Optional[Dict[str, Any]],
        headers: Dict[str, str], 
        operation_type: str
    ) -> Dict[str, Any]:
        """
        Realiza la llamada efectiva al servicio utilizando la función call_service.
        
        Args:
            url: URL completa del servicio
            method: Método HTTP
            data: Datos para enviar
            params: Parámetros de query string
            headers: Headers HTTP incluyendo contexto propagado
            operation_type: Tipo de operación para tracking
            
        Returns:
            Dict[str, Any]: Respuesta del servicio
        """
        start_time = time.time()
        
        try:
            # Llamar al servicio usando la utilidad centralizada
            response = await call_service(
                url=url,
                method=method,
                data=data,
                params=params,
                headers=headers,
                operation_type=operation_type
            )
            
            # Registrar latencia
            latency_ms = int((time.time() - start_time) * 1000)
            await track_operation_latency(
                operation_type=f"service_call_{operation_type}",
                latency_ms=latency_ms,
                metadata={
                    "url": url,
                    "method": method,
                    "from_cache": False
                }
            )
            
            return response
        except Exception as e:
            # Registrar error y re-lanzar
            logger.error(f"Error en llamada a servicio: {url} - {str(e)}")
            raise
    
    @handle_errors(error_type="service", log_traceback=True)
    async def call_query_service(
        self,
        endpoint: str,
        method: str = "POST",
        data: Dict[str, Any] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        ctx: Optional[Context] = None,
        operation_type: str = "rag_query"
    ) -> Dict[str, Any]:
        """
        Llama al servicio de consulta (query) - Compatible con código existente.
        
        Args:
            endpoint: Endpoint a llamar
            method: Método HTTP
            data: Datos para enviar
            tenant_id: ID del tenant
            agent_id: ID del agente
            conversation_id: ID de la conversación
            collection_id: ID de la colección
            ctx: Contexto de la operación
            operation_type: Tipo de operación para timeout
            
        Returns:
            Dict[str, Any]: Respuesta del servicio
        """
        # Usar el método centralizado
        return await self.call_service_with_context(
            service_name="query",
            endpoint=endpoint,
            method=method,
            data=data,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
            ctx=ctx,
            operation_type=operation_type
        )
        
    @handle_errors(error_type="service", log_traceback=True)
    async def call_embedding_service(
        self,
        endpoint: str,
        method: str = "POST",
        data: Dict[str, Any] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ctx: Optional[Context] = None,
        operation_type: str = "embedding_generation"
    ) -> Dict[str, Any]:
        """
        Llama al servicio de embeddings - Compatible con código existente.
        
        Args:
            endpoint: Endpoint a llamar
            method: Método HTTP
            data: Datos para enviar
            tenant_id: ID del tenant
            agent_id: ID del agente
            ctx: Contexto de la operación
            operation_type: Tipo de operación para timeout
            
        Returns:
            Dict[str, Any]: Respuesta del servicio
        """
        # Usar el método centralizado
        return await self.call_service_with_context(
            service_name="embedding",
            endpoint=endpoint,
            method=method,
            data=data,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ctx=ctx,
            operation_type=operation_type
        )
        
    @handle_errors(error_type="service", log_traceback=True)
    async def call_ingestion_service(
        self,
        endpoint: str,
        method: str = "POST",
        data: Dict[str, Any] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ctx: Optional[Context] = None,
        operation_type: str = "ingestion"
    ) -> Dict[str, Any]:
        """
        Llama al servicio de ingestión - Compatible con código existente.
        
        Args:
            endpoint: Endpoint a llamar
            method: Método HTTP
            data: Datos para enviar
            tenant_id: ID del tenant
            agent_id: ID del agente
            ctx: Contexto de la operación
            operation_type: Tipo de operación para timeout
            
        Returns:
            Dict[str, Any]: Respuesta del servicio
        """
        # Usar el método centralizado
        return await self.call_service_with_context(
            service_name="ingestion",
            endpoint=endpoint,
            method=method,
            data=data,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ctx=ctx,
            operation_type=operation_type
        )
    
    @handle_errors(error_type="service", log_traceback=True)
    async def check_service_health(self, service_name: str) -> Dict[str, str]:
        """
        Verifica el estado de salud de un servicio.
        
        Args:
            service_name: Nombre del servicio a verificar
            
        Returns:
            Dict[str, str]: Estado del servicio
        """
        if service_name not in self.service_urls:
            return {"status": "unavailable", "message": f"Servicio {service_name} no configurado"}
            
        base_url = self.service_urls[service_name]
        url = f"{base_url}/health"
        
        try:
            # Usar health_check como tipo de operación para timeout corto
            response = await call_service(
                url=url,
                method="GET",
                operation_type="health_check"
            )
            
            if response.get("status") == "ok":
                return {"status": "available", "message": "Servicio disponible"}
            else:
                return {"status": "degraded", "message": "Servicio responde pero con degradación"}
        except Exception as e:
            logger.warning(f"Error verificando servicio {service_name}: {str(e)}")
            return {"status": "unavailable", "message": f"Error: {str(e)}"}
    
    @handle_errors(error_type="service", log_traceback=True)
    async def get_collections(
        self, 
        tenant_id: str,
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        Obtiene las colecciones disponibles para un tenant.
        
        Args:
            tenant_id: ID del tenant
            ctx: Contexto de la operación
            
        Returns:
            Dict[str, Any]: Lista de colecciones
        """
        # Clave de caché para resultados
        cache_key = f"collections:{tenant_id}"
        
        # Verificar caché primero
        cached_collections = await CacheManager.get(
            data_type="collections",
            resource_id=cache_key,
            tenant_id=tenant_id
        )
        
        if cached_collections:
            return cached_collections
            
        # Si no está en caché, obtener de query service
        try:
            response = await self.call_query_service(
                endpoint="collections",
                method="GET",
                tenant_id=tenant_id,
                ctx=ctx,
                operation_type="default"
            )
            
            # Guardar en caché por un tiempo limitado
            if response.get("success", False):
                await CacheManager.set(
                    data_type="collections",
                    resource_id=cache_key,
                    value=response,
                    tenant_id=tenant_id,
                    ttl=CacheManager.ttl_standard  # 1 hora
                )
                
            return response
        except Exception as e:
            logger.error(f"Error obteniendo colecciones: {str(e)}")
            return {
                "success": False,
                "message": f"Error obteniendo colecciones: {str(e)}",
                "collections": []
            }
