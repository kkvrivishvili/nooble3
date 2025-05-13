"""
Registro centralizado para servicios disponibles.

Este módulo permite la comunicación con otros servicios del sistema,
implementando un cliente unificado con soporte para propagación de contexto.
"""

import logging
from typing import Dict, Any, Optional

from common.context import Context
from common.errors import handle_errors, ServiceError
from common.utils.http import call_service
from common.cache import CacheManager

from config import get_settings

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Registro centralizado para servicios disponibles.
    Proporciona acceso a los servicios de la plataforma (query, embedding, ingestion).
    """
    
    def __init__(self):
        """Inicializa el registro de servicios."""
        self.settings = get_settings()
        self.service_urls = {
            "query": self.settings.query_service_url,
            "embedding": self.settings.embedding_service_url,
            "ingestion": self.settings.ingestion_service_url
        }
    
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
        Llama al servicio de consulta (query).
        
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
        # Obtener tenant_id del contexto si no se proporcionó
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(False)
            
        # Construir URL completa
        base_url = self.service_urls["query"]
        url = f"{base_url}/{endpoint.lstrip('/')}"
        
        # Propagar el contexto
        headers = {}
        if tenant_id:
            headers["x-tenant-id"] = tenant_id
        if agent_id:
            headers["x-agent-id"] = agent_id
        if conversation_id:
            headers["x-conversation-id"] = conversation_id
        if collection_id:
            headers["x-collection-id"] = collection_id
            
        # Llamar al servicio usando la utilidad centralizada
        response = await call_service(
            url=url,
            method=method,
            data=data,
            headers=headers,
            operation_type=operation_type
        )
        
        return response
    
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
        Llama al servicio de embeddings.
        
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
        # Obtener tenant_id del contexto si no se proporcionó
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(False)
            
        # Construir URL completa
        base_url = self.service_urls["embedding"]
        url = f"{base_url}/{endpoint.lstrip('/')}"
        
        # Propagar el contexto
        headers = {}
        if tenant_id:
            headers["x-tenant-id"] = tenant_id
        if agent_id:
            headers["x-agent-id"] = agent_id
            
        # Llamar al servicio usando la utilidad centralizada
        response = await call_service(
            url=url,
            method=method,
            data=data,
            headers=headers,
            operation_type=operation_type
        )
        
        return response
    
    @handle_errors(error_type="service", log_traceback=True)
    async def call_ingestion_service(
        self,
        endpoint: str,
        method: str = "POST",
        data: Dict[str, Any] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ctx: Optional[Context] = None,
        operation_type: str = "default"
    ) -> Dict[str, Any]:
        """
        Llama al servicio de ingestion.
        
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
        # Obtener tenant_id del contexto si no se proporcionó
        if not tenant_id and ctx:
            tenant_id = ctx.get_tenant_id(False)
            
        # Construir URL completa
        base_url = self.service_urls["ingestion"]
        url = f"{base_url}/{endpoint.lstrip('/')}"
        
        # Propagar el contexto
        headers = {}
        if tenant_id:
            headers["x-tenant-id"] = tenant_id
        if agent_id:
            headers["x-agent-id"] = agent_id
            
        # Llamar al servicio usando la utilidad centralizada
        response = await call_service(
            url=url,
            method=method,
            data=data,
            headers=headers,
            operation_type=operation_type
        )
        
        return response
    
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
