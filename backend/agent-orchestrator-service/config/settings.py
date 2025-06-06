"""
Configuración del Agent Orchestrator Service.
"""

from typing import List
from pydantic import Field
from common.config import Settings as BaseSettings
from common.config import get_service_settings as get_base_settings

class OrchestratorSettings(BaseSettings):
    """Configuración específica para Agent Orchestrator Service."""
    
    # Redis para colas
    redis_url: str = Field(
        "redis://localhost:6379",
        description="URL de Redis para colas de trabajo"
    )
    
    # URLs de servicios (para health checks y comunicación directa si necesario)
    agent_execution_service_url: str = Field(
        "http://localhost:8005",
        description="URL del Agent Execution Service"
    )
    agent_management_service_url: str = Field(
        "http://localhost:8003",
        description="URL del Agent Management Service"
    )
    conversation_service_url: str = Field(
        "http://localhost:8004",
        description="URL del Conversation Service"
    )
    
    # WebSocket configuración
    websocket_ping_interval: int = Field(
        30,
        description="Intervalo de ping para WebSocket (segundos)"
    )
    websocket_ping_timeout: int = Field(
        10,
        description="Timeout para pong de WebSocket (segundos)"
    )
    max_websocket_connections: int = Field(
        1000,
        description="Máximo de conexiones WebSocket simultáneas"
    )
    
    # Task management
    task_timeout_seconds: int = Field(
        300,
        description="Timeout para tareas en cola (segundos)"
    )
    max_queue_size: int = Field(
        10000,
        description="Tamaño máximo de cola por tenant"
    )
    
    # Performance
    worker_batch_size: int = Field(
        10,
        description="Tamaño de lote para procesamiento de callbacks"
    )
    worker_sleep_seconds: float = Field(
        1.0,
        description="Tiempo de espera del worker entre checks"
    )
    
    class Config:
        env_prefix = "ORCHESTRATOR_"

def get_settings() -> OrchestratorSettings:
    """Obtiene configuración del servicio."""
    base_settings = get_base_settings("agent-orchestrator-service")
    return OrchestratorSettings(**base_settings.dict())