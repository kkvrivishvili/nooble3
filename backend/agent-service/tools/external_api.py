"""
Herramienta para integraciones con APIs externas.

Permite a los agentes interactuar con servicios externos vía API REST.
"""

import logging
import json
import httpx
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from common.context import Context
from common.errors.handlers import handle_errors
from common.cache import CacheManager
from common.tracking import track_performance_metric

from tools.base import BaseTool

logger = logging.getLogger(__name__)

class ExternalAPIInput(BaseModel):
    """Modelo de entrada para la herramienta de API externa."""
    endpoint: str = Field(description="Endpoint o ruta específica de la API")
    params: Optional[Dict[str, Any]] = Field(None, description="Parámetros de consulta (query params)")
    body: Optional[Dict[str, Any]] = Field(None, description="Cuerpo de la petición (para POST/PUT)")
    headers: Optional[Dict[str, Any]] = Field(None, description="Cabeceras HTTP adicionales")

class ExternalAPITool(BaseTool):
    """
    Herramienta para integración con APIs externas.
    
    Permite que los agentes realicen peticiones a APIs externas
    con soporte para caché, configuración dinámica y mapeo de resultados.
    """
    
    name = "external_api"
    description = "Realiza llamadas a APIs externas para obtener o enviar información"
    args_schema = ExternalAPIInput
    
    def __init__(
        self, 
        service_registry, 
        ctx: Optional[Context] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        result_mappings: Optional[Dict[str, str]] = None,
        cache_enabled: bool = True,
        cache_ttl: Optional[int] = None
    ):
        """
        Inicializa la herramienta de API externa.
        
        Args:
            service_registry: Registro de servicios
            ctx: Contexto opcional
            base_url: URL base para todas las peticiones
            api_key: Clave de API para autenticación
            default_headers: Cabeceras por defecto para todas las peticiones
            result_mappings: Mapeos para formatear los resultados de la API
            cache_enabled: Si se debe utilizar caché para las respuestas
            cache_ttl: Tiempo de vida en caché (None = usar valor estándar)
        """
        super().__init__(service_registry, ctx)
        self.base_url = base_url or ""
        self.api_key = api_key
        self.default_headers = default_headers or {}
        self.result_mappings = result_mappings or {}
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        
        # Añadir api_key a headers si está presente
        if self.api_key and "Authorization" not in self.default_headers:
            self.default_headers["Authorization"] = f"Bearer {self.api_key}"
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _run_with_context(
        self, 
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Ejecuta la petición a la API externa con gestión de contexto.
        
        Args:
            endpoint: Endpoint o ruta específica
            method: Método HTTP (GET, POST, PUT, DELETE)
            params: Parámetros de consulta
            body: Cuerpo de la petición
            headers: Cabeceras HTTP adicionales
            
        Returns:
            Respuesta formateada de la API
            
        Raises:
            ServiceError: Si hay errores de comunicación con la API
        """
        tenant_id = self.ctx.get_tenant_id() if self.ctx else None
        
        # Construir URL completa
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # Combinar headers
        combined_headers = {**self.default_headers}
        if headers:
            combined_headers.update(headers)
        
        # Generar clave de caché
        cache_key = f"{method}:{url}:{json.dumps(params or {})}:{json.dumps(body or {})}"
        cache_hash = self._hash_cache_key(cache_key)
        
        # Verificar caché si está habilitada
        if self.cache_enabled and method.upper() == "GET":
            cached_result = await CacheManager.get(
                data_type="external_api",
                resource_id=cache_hash,
                tenant_id=tenant_id,
                agent_id=self.ctx.get_agent_id() if self.ctx else None
            )
            
            if cached_result:
                logger.info(f"Resultado de API externa recuperado de caché: {url}")
                return self._format_api_result(cached_result)
        
        # Realizar petición HTTP
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=body if body else None,
                    headers=combined_headers,
                    timeout=30.0  # Timeout razonable
                )
                
                # Verificar si la respuesta es exitosa
                response.raise_for_status()
                
                # Intentar parsearlo como JSON
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    # Si no es JSON, devolver texto
                    result = {"text": response.text}
                
                # Guardar en caché si es GET y caché está habilitada
                if self.cache_enabled and method.upper() == "GET":
                    ttl = self.cache_ttl or CacheManager.ttl_standard
                    await CacheManager.set(
                        data_type="external_api",
                        resource_id=cache_hash,
                        value=result,
                        tenant_id=tenant_id,
                        agent_id=self.ctx.get_agent_id() if self.ctx else None,
                        ttl=ttl
                    )
                
                # Registrar métricas
                await track_performance_metric(
                    metric_type="external_api_call",
                    value=1,
                    tenant_id=tenant_id,
                    metadata={
                        "url": url,
                        "method": method,
                        "status_code": response.status_code,
                        "latency_ms": response.elapsed.total_seconds() * 1000
                    }
                )
                
                # Formatear y devolver resultado
                return self._format_api_result(result)
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Error en petición API ({e.response.status_code}): {url}", 
                           extra={"error": str(e), "status": e.response.status_code})
                return f"Error en la API: {e.response.status_code} - {e.response.text}"
                
            except httpx.RequestError as e:
                logger.error(f"Error conectando con API: {url}", extra={"error": str(e)})
                return f"Error conectando con la API: {str(e)}"
    
    def _format_api_result(self, result: Dict[str, Any]) -> str:
        """
        Formatea el resultado de la API para consumo del agente.
        
        Args:
            result: Resultado original de la API
            
        Returns:
            Texto formateado con el resultado
        """
        if isinstance(result, dict):
            # Si hay un mapeo definido, aplicarlo
            if self.result_mappings:
                formatted_result = {}
                for target_key, source_path in self.result_mappings.items():
                    value = self._extract_nested_value(result, source_path)
                    if value is not None:
                        formatted_result[target_key] = value
                
                # Si se pudo aplicar el mapeo, devolver el resultado formateado
                if formatted_result:
                    return json.dumps(formatted_result, indent=2)
            
            # Extraer campos relevantes según configuración
            if "message" in result:
                return str(result["message"])
            elif "data" in result:
                return json.dumps(result["data"], indent=2)
            elif "results" in result:
                return json.dumps(result["results"], indent=2)
        
        # Para otros casos, simplemente convertir a JSON con formato
        return json.dumps(result, indent=2)
    
    def _extract_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Extrae un valor anidado de un diccionario usando una ruta de acceso.
        
        Args:
            data: Diccionario de datos
            path: Ruta de acceso separada por puntos (e.g., "data.items.0.name")
            
        Returns:
            Valor extraído o None si no se encuentra
        """
        parts = path.split(".")
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return None
        
        return current
    
    def _hash_cache_key(self, key: str) -> str:
        """Genera un hash para usar como clave de caché."""
        import hashlib
        return hashlib.md5(key.encode()).hexdigest()
