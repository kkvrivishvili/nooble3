"""
Modelos para la gestión de contexto en el Agent Service.

Este módulo define los modelos Pydantic para la gestión de contexto,
incluyendo configuraciones de propagación y payload de contexto entre servicios.
"""

from typing import Dict, List, Any, Optional, Set
from pydantic import BaseModel, Field, validator
from datetime import datetime
import uuid


class ContextConfig(BaseModel):
    """Configuración para propagación de contexto."""
    propagate_tenant: bool = Field(True, description="Propagar ID de tenant")
    propagate_user: bool = Field(True, description="Propagar ID de usuario")
    propagate_conversation: bool = Field(True, description="Propagar ID de conversación")
    propagate_session: bool = Field(True, description="Propagar ID de sesión")
    propagate_agent: bool = Field(True, description="Propagar ID de agente")
    custom_fields: Optional[List[str]] = Field(None, description="Campos personalizados a propagar")
    exclude_fields: Optional[List[str]] = Field(None, description="Campos a excluir de la propagación")
    max_context_size_kb: int = Field(64, description="Tamaño máximo del contexto en KB")
    
    @validator('exclude_fields')
    def validate_exclude_fields(cls, v, values):
        """Validar que no se excluyan campos requeridos si se están propagando."""
        if v is None:
            return v
            
        required_mappings = {
            'propagate_tenant': 'tenant_id',
            'propagate_user': 'user_id',
            'propagate_conversation': 'conversation_id',
            'propagate_session': 'session_id',
            'propagate_agent': 'agent_id'
        }
        
        for config_key, field_name in required_mappings.items():
            if values.get(config_key, False) and field_name in v:
                raise ValueError(f"No se puede excluir {field_name} mientras {config_key} está habilitado")
                
        return v


class ContextPayload(BaseModel):
    """Datos a propagar entre servicios."""
    tenant_id: str = Field(..., description="ID del tenant")
    user_id: Optional[str] = Field(None, description="ID del usuario si está disponible")
    conversation_id: Optional[str] = Field(None, description="ID de la conversación si está disponible")
    session_id: Optional[str] = Field(None, description="ID de sesión si está disponible")
    agent_id: Optional[str] = Field(None, description="ID del agente si está disponible")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único de la solicitud")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de la solicitud")
    path: Optional[str] = Field(None, description="Ruta de la solicitud original")
    source_service: Optional[str] = Field(None, description="Servicio que origina la solicitud")
    target_service: Optional[str] = Field(None, description="Servicio destino de la solicitud")
    is_system: bool = Field(False, description="Si la solicitud es del sistema y no del usuario")
    custom_data: Optional[Dict[str, Any]] = Field(None, description="Datos personalizados")
    parent_request_id: Optional[str] = Field(None, description="ID de la solicitud padre si es una subsolicitud")
    
    def clone(self) -> 'ContextPayload':
        """Clona el contexto actual pero con un nuevo request_id."""
        data = self.dict()
        data['parent_request_id'] = self.request_id
        data['request_id'] = str(uuid.uuid4())
        data['timestamp'] = datetime.utcnow()
        return ContextPayload(**data)
    
    def to_headers(self) -> Dict[str, str]:
        """Convierte el contexto a headers HTTP."""
        headers = {}
        
        # Añadir campos principales
        if self.tenant_id:
            headers['X-Tenant-ID'] = self.tenant_id
        if self.user_id:
            headers['X-User-ID'] = self.user_id
        if self.conversation_id:
            headers['X-Conversation-ID'] = self.conversation_id
        if self.agent_id:
            headers['X-Agent-ID'] = self.agent_id
        if self.request_id:
            headers['X-Request-ID'] = self.request_id
        if self.session_id:
            headers['X-Session-ID'] = self.session_id
            
        # Añadir campos adicionales
        if self.is_system:
            headers['X-System-Request'] = 'true'
        if self.source_service:
            headers['X-Source-Service'] = self.source_service
        if self.target_service:
            headers['X-Target-Service'] = self.target_service
        if self.parent_request_id:
            headers['X-Parent-Request-ID'] = self.parent_request_id
            
        return headers
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> 'ContextPayload':
        """Crea un contexto a partir de headers HTTP."""
        # Mapeo de headers a campos
        mapping = {
            'X-Tenant-ID': 'tenant_id',
            'X-User-ID': 'user_id',
            'X-Conversation-ID': 'conversation_id',
            'X-Agent-ID': 'agent_id',
            'X-Request-ID': 'request_id',
            'X-Session-ID': 'session_id',
            'X-Source-Service': 'source_service',
            'X-Target-Service': 'target_service',
            'X-Parent-Request-ID': 'parent_request_id'
        }
        
        # Construir diccionario de datos
        data = {}
        for header, field in mapping.items():
            if header in headers:
                data[field] = headers[header]
                
        # Campos booleanos
        if 'X-System-Request' in headers:
            data['is_system'] = headers['X-System-Request'].lower() == 'true'
            
        # Asegurar que tenant_id esté presente
        if 'tenant_id' not in data:
            raise ValueError("Falta el header X-Tenant-ID requerido")
            
        return cls(**data)


class ContextManager(BaseModel):
    """Gestor de contexto para el Agent Service."""
    config: ContextConfig = Field(default_factory=ContextConfig, description="Configuración del gestor")
    context: ContextPayload = Field(..., description="Contexto actual")
    
    def propagate(self, target_service: str) -> Dict[str, str]:
        """Propaga el contexto al servicio destino."""
        # Clonar y modificar el contexto
        propagated = self.context.clone()
        propagated.source_service = "agent"
        propagated.target_service = target_service
        
        # Filtrar campos según configuración
        exclude_fields = self.config.exclude_fields or []
        headers = propagated.to_headers()
        
        # Eliminar campos excluidos
        for field in exclude_fields:
            header = next((h for h, f in {
                'X-Tenant-ID': 'tenant_id',
                'X-User-ID': 'user_id',
                'X-Conversation-ID': 'conversation_id',
                'X-Agent-ID': 'agent_id',
                'X-Session-ID': 'session_id'
            }.items() if f == field), None)
            
            if header and header in headers:
                del headers[header]
                
        return headers
