"""
Herramienta para integraciones con APIs externas.

Permite a los agentes interactuar con servicios externos vía API REST.
"""

import logging
import json
import re
import time
import httpx
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List, Set
from pydantic import BaseModel, Field, validator

from common.context import Context
from common.errors.handlers import handle_errors
from common.cache import CacheManager, get_with_cache_aside
from common.tracking import track_performance_metric

from tools.base import BaseTool

logger = logging.getLogger(__name__)

class ExternalAPIInput(BaseModel):
    """Modelo de entrada para la herramienta de API externa."""
    endpoint: str = Field(description="Endpoint o ruta específica de la API")
    params: Optional[Dict[str, Any]] = Field(None, description="Parámetros de consulta (query params)")
    body: Optional[Dict[str, Any]] = Field(None, description="Cuerpo de la petición (para POST/PUT)")
    headers: Optional[Dict[str, Any]] = Field(None, description="Cabeceras HTTP adicionales")
    
    @validator("endpoint")
    def validate_endpoint(cls, v):
        # Evitar inyección de rutas o ../
        if ".." in v or "//" in v or re.search(r"[\\\s'\"ñ]|\.\.\/", v):
            raise ValueError("Endpoint contiene caracteres no permitidos")
        
        # Evitar rutas absolutes o URLs completas (debe ser relativo al base_url)
        parsed = urlparse(v)
        if parsed.scheme or parsed.netloc:
            raise ValueError("El endpoint debe ser una ruta relativa, no una URL completa")
            
        return v.strip('/')
        
    @validator("headers")
    def sanitize_headers(cls, v):
        if not v:
            return v
            
        # Lista de cabeceras que no deben ser sobreescritas por seguridad
        restricted_headers = {
            "authorization", "cookie", "host", "content-length", 
            "user-agent", "referer", "origin", "x-csrf-token"
        }
        
        # Filtrar cabeceras restringidas (ignorando mayusculas/minusculas)
        return {k: v for k, v in v.items() 
                if k.lower() not in restricted_headers}

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
    
    async def _sanitize_params(self, params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Sanitiza parámetros de consulta para prevenir inyecciones."""
        if not params:
            return params
            
        sanitized = {}
        for key, value in params.items():
            # Validar claves y valores (no permitir caracteres especiales en claves)
            if not re.match(r'^[a-zA-Z0-9_\-]+$', key):
                logger.warning(f"Parámetro con nombre inválido ignorado: {key}")
                continue
                
            # Para valores, convertirlos a string y sanitizar
            if isinstance(value, (dict, list)):
                sanitized[key] = json.dumps(value)
            else:
                # Convertir a string y eliminar caracteres potencialmente peligrosos
                str_value = str(value)
                if re.search(r'[;<>\\`]', str_value):
                    logger.warning(f"Valor potencialmente peligroso sanitizado para {key}")
                    str_value = re.sub(r'[;<>\\`]', '', str_value)
                sanitized[key] = str_value
                
        return sanitized
    
    async def _verify_url_is_allowed(self, url: str) -> bool:
        """Verifica que la URL sea segura y esté permitida."""
        parsed = urlparse(url)
        
        # Verificar que solo use protocolos seguros
        if parsed.scheme not in ('http', 'https'):
            logger.error(f"Protocolo no permitido: {parsed.scheme}")
            return False
            
        # Lista opcional de dominios permitidos (se puede expandir)
        # Esto se podría cargar desde una configuración
        return True
        
    async def _check_connectivity(self, url: str) -> Dict[str, Any]:
        """Verifica la conectividad con el servicio externo antes de realizar la petición principal.
        
        Args:
            url: URL base del servicio a verificar
            
        Returns:
            Dict con resultado de la verificación {success: bool, error: Optional[str], latency_ms: Optional[float]}
        """
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        try:
            # Realizar una petición HEAD ligera para verificar conectividad
            async with httpx.AsyncClient() as client:
                start_time = time.time()
                response = await client.head(
                    base_url,
                    timeout=5.0,  # Timeout reducido para prueba de conectividad
                    follow_redirects=True
                )
                latency_ms = (time.time() - start_time) * 1000
                
                # Verificar si hay problemas de conectividad
                if response.status_code >= 500:
                    logger.warning(f"Error de servidor en prueba de conectividad: {response.status_code}")
                    return {
                        "success": False,
                        "error": f"El servidor externo respondió con error: {response.status_code}",
                        "latency_ms": latency_ms
                    }
                    
                # Registrar métricas de latencia
                await track_performance_metric(
                    metric_type="api_connectivity_check",
                    value=latency_ms,
                    tenant_id=self.ctx.get_tenant_id() if self.ctx else None,
                    metadata={
                        "url": base_url,
                        "status_code": response.status_code,
                        "latency_ms": latency_ms
                    }
                )
                
                # Detectar latencias excesivas
                if latency_ms > 1000:  # Más de 1 segundo
                    logger.warning(f"Alta latencia detectada en API externa: {latency_ms:.2f}ms")
                
                return {
                    "success": True,
                    "latency_ms": latency_ms
                }
                
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"Error de conectividad con API externa: {base_url}", extra={"error": str(e)})
            return {
                "success": False,
                "error": f"No se pudo conectar con el servicio externo: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error inesperado en prueba de conectividad: {str(e)}")
            return {
                "success": False,
                "error": f"Error verificando conectividad: {str(e)}"
            }
    
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
        
        # Sanitizar endpoint
        endpoint = endpoint.strip('/')
        
        # Construir URL completa
        url = f"{self.base_url.rstrip('/')}/{endpoint}"
        
        # Verificar que la URL sea permitida
        if not await self._verify_url_is_allowed(url):
            return "Error: La URL solicitada no está permitida por razones de seguridad"
            
        # Verificar conectividad con el servicio externo antes de proceder
        connectivity_result = await self._check_connectivity(url)
        if not connectivity_result['success']:
            return f"Error de conectividad con el servicio externo: {connectivity_result['error']}"
        
        # Combinar headers (con prioridad para los default_headers)
        combined_headers = {**self.default_headers}
        if headers:
            # Filtrar cabeceras protegidas
            sanitized_headers = {k: v for k, v in headers.items() 
                               if k.lower() not in ('authorization', 'cookie', 'host')}
            combined_headers.update(sanitized_headers)
        
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
                # Sanitizar parámetros
                sanitized_params = await self._sanitize_params(params)
                
                # Validar método HTTP
                allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')
                if method.upper() not in allowed_methods:
                    return f"Error: Método HTTP no permitido: {method}. Use uno de: {', '.join(allowed_methods)}"
                
                # Realizar la petición con parámetros sanitizados
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    params=sanitized_params,
                    json=body if body else None,  # El body se valida mediante el modelo Pydantic
                    headers=combined_headers,
                    timeout=30.0,  # Timeout razonable
                    follow_redirects=True  # Seguir redirecciones de forma segura
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
