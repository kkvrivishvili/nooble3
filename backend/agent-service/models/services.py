"""
Modelos para el Service Registry en el Agent Service.

Este módulo define los modelos Pydantic para la configuración de servicios,
solicitudes y respuestas estandarizadas entre servicios.
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, validator, root_validator
from datetime import datetime, timedelta
import uuid

from .context import ContextPayload


class ServiceType(str, Enum):
    """Tipo de servicio en el sistema Nooble3."""
    QUERY = "query"
    EMBEDDING = "embedding"
    INGESTION = "ingestion"
    AGENT = "agent"
    EXTERNAL = "external"


class ServiceConfig(BaseModel):
    """Configuración para servicios externos."""
    service_name: str = Field(..., description="Nombre del servicio")
    service_type: ServiceType = Field(..., description="Tipo de servicio")
    base_url: str = Field(..., description="URL base del servicio")
    timeout_seconds: int = Field(30, description="Timeout para solicitudes")
    retry_count: int = Field(3, description="Número de reintentos")
    retry_backoff_factor: float = Field(0.5, description="Factor de backoff para reintentos")
    connection_pool_size: int = Field(10, description="Tamaño del pool de conexiones")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers personalizados")
    auth_config: Optional[Dict[str, Any]] = Field(None, description="Configuración de autenticación")
    health_check_endpoint: str = Field("/health", description="Endpoint para health check")
    is_internal: bool = Field(True, description="Si es un servicio interno de Nooble3")
    
    @validator('timeout_seconds')
    def validate_timeout(cls, v):
        if v < 1 or v > 300:
            raise ValueError("timeout_seconds debe estar entre 1 y 300")
        return v
    
    @validator('retry_count')
    def validate_retry_count(cls, v):
        if v < 0 or v > 10:
            raise ValueError("retry_count debe estar entre 0 y 10")
        return v
    
    @validator('connection_pool_size')
    def validate_connection_pool_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError("connection_pool_size debe estar entre 1 y 100")
        return v


class RequestMethod(str, Enum):
    """Método HTTP para solicitudes a servicios."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class ServiceRequest(BaseModel):
    """Solicitud estandarizada a servicios."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único de la solicitud")
    endpoint: str = Field(..., description="Endpoint a llamar")
    method: RequestMethod = Field(RequestMethod.POST, description="Método HTTP")
    data: Optional[Dict[str, Any]] = Field(None, description="Datos de la solicitud")
    params: Optional[Dict[str, Any]] = Field(None, description="Parámetros de query string")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers adicionales")
    context: Optional[ContextPayload] = Field(None, description="Contexto a propagar")
    timeout: Optional[int] = Field(None, description="Timeout en segundos (sobreescribe config)")
    idempotency_key: Optional[str] = Field(None, description="Clave de idempotencia")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de la solicitud")
    
    @root_validator
    def validate_params_and_data(cls, values):
        """Validar coherencia entre método y datos/parámetros."""
        method = values.get('method')
        data = values.get('data')
        
        if method == RequestMethod.GET and data:
            raise ValueError("No se pueden enviar datos en el cuerpo con método GET")
            
        return values


class ServiceResponse(BaseModel):
    """Respuesta estandarizada de servicios."""
    request_id: str = Field(..., description="ID de la solicitud original")
    success: bool = Field(..., description="Si la solicitud fue exitosa")
    status_code: int = Field(..., description="Código de estado HTTP")
    data: Optional[Dict[str, Any]] = Field(None, description="Datos de respuesta")
    error: Optional[str] = Field(None, description="Error en caso de fallo")
    error_code: Optional[str] = Field(None, description="Código de error en caso de fallo")
    latency_ms: int = Field(..., description="Latencia en milisegundos")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de la respuesta")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers de la respuesta")
    
    @validator('data', 'error')
    def check_success_data_error(cls, v, values):
        """Validar coherencia entre success, data y error."""
        if 'success' in values:
            success = values['success']
            if success and v is None and v == 'error':
                raise ValueError("Si success es True, error debe ser None")
            if not success and v is None and v == 'data':
                # No se valida presencia de datos en error porque algunos errores no tienen datos
                pass
        return v


class ServiceRegistry(BaseModel):
    """Registro centralizado de servicios."""
    services: Dict[str, ServiceConfig] = Field(default_factory=dict, description="Servicios registrados")
    last_health_check: Dict[str, datetime] = Field(default_factory=dict, description="Último health check")
    failed_health_checks: Dict[str, int] = Field(default_factory=dict, description="Conteo de fallos de health check")
    
    def register_service(self, config: ServiceConfig) -> None:
        """Registra un nuevo servicio."""
        self.services[config.service_name] = config
        self.last_health_check[config.service_name] = datetime.min
        self.failed_health_checks[config.service_name] = 0
        
    def get_service_config(self, service_name: str) -> ServiceConfig:
        """Obtiene la configuración de un servicio."""
        if service_name not in self.services:
            raise ValueError(f"Servicio {service_name} no registrado")
        return self.services[service_name]
    
    def needs_health_check(self, service_name: str, interval_seconds: int = 60) -> bool:
        """Determina si un servicio necesita health check."""
        if service_name not in self.services:
            raise ValueError(f"Servicio {service_name} no registrado")
            
        last_check = self.last_health_check.get(service_name, datetime.min)
        interval = timedelta(seconds=interval_seconds)
        
        return datetime.utcnow() - last_check > interval
    
    def update_health_status(self, service_name: str, is_healthy: bool) -> None:
        """Actualiza el estado de salud de un servicio."""
        if service_name not in self.services:
            raise ValueError(f"Servicio {service_name} no registrado")
            
        self.last_health_check[service_name] = datetime.utcnow()
        
        if is_healthy:
            self.failed_health_checks[service_name] = 0
        else:
            self.failed_health_checks[service_name] += 1
