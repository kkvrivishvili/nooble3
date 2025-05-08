"""
Definición de la clase Settings y función get_settings() para configuración centralizada.
"""

import os
import json
import logging
import time
from typing import Dict, Any, Optional, List, Union
from functools import lru_cache
from pydantic import Field, validator
from pydantic_settings import BaseSettings

# Eliminamos las importaciones directas y usaremos importaciones tardías
# para evitar dependencias circulares
# from ..errors.handlers import handle_errors
# from ..errors.exceptions import ConfigurationError, ErrorCode

logger = logging.getLogger(__name__)

# Variables globales para control de caché
_force_settings_reload = False
_settings_last_refresh = {}  # {tenant_id: timestamp}
_settings_ttl = 3600  # 1 hora por defecto

class Settings(BaseSettings):
    """
    Configuración centralizada para todos los servicios.
    
    Utiliza valores de entorno y configuraciones de tenant desde Supabase.
    """
    # =========== Configuración general ===========
    service_name: str = Field("llama-service", description="Nombre del servicio actual")
    service_version: str = Field("1.0.0", env="SERVICE_VERSION", description="Versión del servicio")
    environment: str = Field("development", description="Entorno actual (development, staging, production)")
    debug_mode: bool = Field(False, description="Modo de depuración")
    
    # =========== URLs de servicios ===========
    embedding_service_url: str = Field("http://embedding-service:8001", env="EMBEDDING_SERVICE_URL", description="URL del servicio de embeddings")
    query_service_url: str = Field("http://query-service:8002", env="QUERY_SERVICE_URL", description="URL del servicio de consultas")
    agent_service_url: str = Field("http://agent-service:8003", env="AGENT_SERVICE_URL", description="URL del servicio de agentes")
    ingestion_service_url: str = Field("http://ingestion-service:8000", env="INGESTION_SERVICE_URL", description="URL del servicio de ingesta")
    
    # =========== Tenant por defecto ===========
    default_tenant_id: str = Field("00000000-0000-0000-0000-000000000000", description="ID del tenant por defecto")
    validate_tenant_access: bool = Field(False, description="Validar que el tenant esté activo")
    
    # =========== Logging ===========
    log_level: str = Field("INFO", description="Nivel de logging")
    log_format: str = Field("[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s", description="Formato de logging")
    
    # =========== Base de datos ===========
    supabase_url: str = Field("https://localhost:54321", env="SUPABASE_URL", description="URL de Supabase")
    supabase_key: str = Field("supabase-key", env="SUPABASE_KEY", description="Clave de Supabase")
    supabase_service_key: str = Field("supabase-service-key", env="SUPABASE_SERVICE_KEY", description="Clave de servicio de Supabase")
    db_prefix: str = Field("ai_", description="Prefijo para tablas")
    
    # =========== Redis ===========
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL", description="URL de Redis")
    redis_max_connections: int = Field(10, description="Máximo número de conexiones Redis")
    redis_password: Optional[str] = Field(None, env="REDIS_PASSWORD", description="Contraseña de Redis")
    
    # =========== Modelado de lenguaje ===========
    openai_api_key: str = Field("", env="OPENAI_API_KEY", description="Clave API de OpenAI")
    openai_org_id: Optional[str] = Field(None, env="OPENAI_ORG_ID", description="ID de organización de OpenAI")
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY", description="Clave de API de Anthropic")
    default_llm_model: str = Field("gpt-3.5-turbo", env="DEFAULT_OPENAI_LLM_MODEL", description="Modelo predeterminado para LLM")
    default_embedding_model: str = Field("text-embedding-3-small", env="DEFAULT_OPENAI_EMBEDDING_MODEL", description="Modelo predeterminado para embeddings")
    
    # =========== Configuración de Ollama ===========
    use_ollama: bool = Field(True, env="USE_OLLAMA", description="Usar Ollama en lugar de OpenAI")
    ollama_api_url: str = Field("http://ollama:11434", env="OLLAMA_API_URL", description="URL de la API de Ollama")
    default_ollama_model: str = Field("qwen3:1.7b", env="DEFAULT_OLLAMA_MODEL", description="Modelo predeterminado para Ollama")
    default_ollama_llm_model: str = Field("qwen3:1.7b", env="DEFAULT_OLLAMA_LLM_MODEL", description="Modelo LLM predeterminado para Ollama")
    default_ollama_embedding_model: str = Field("nomic-embed-text", env="DEFAULT_OLLAMA_EMBEDDING_MODEL", description="Modelo de embedding para Ollama")
    
    # =========== API AI =========== 
    api_key_hash_salt: str = Field("default-salt", env="API_KEY_HASH_SALT", description="Salt para hash de claves de API")
    api_key_hash_iterations: int = Field(100000, description="Iteraciones de hash para claves de API")
    
    # =========== Cache ===========
    settings_ttl: int = Field(300, description="TTL para caché de configuraciones (segundos)")
    cache_ttl_extended: int = Field(86400, description="TTL para caché extendida (24h)")
    cache_ttl_standard: int = Field(3600, description="TTL para caché estándar (1h)")
    cache_ttl_short: int = Field(300, description="TTL para caché corta (5min)")
    use_memory_cache: bool = Field(True, description="Usar caché en memoria")
    memory_cache_size: int = Field(1000, description="Tamaño máximo de caché en memoria (items)")
    memory_cache_cleanup_percent: float = Field(0.2, description="Porcentaje de entradas a eliminar durante limpieza")
    cache_ttl_permanent: int = Field(0, description="TTL para caché permanente (0 = sin expiración)")
    
    # =========== Configuración avanzada ===========
    load_config_from_supabase: bool = Field(True, description="Cargar configuraciones desde Supabase")
    override_settings_from_env: bool = Field(True, description="Permitir sobrescribir por variables de entorno")
    mock_supabase: bool = Field(False, description="Usar mock para supabase")
    allow_cors: bool = Field(True, description="Permitir CORS")
    cors_origins: List[str] = Field(["*"], description="Orígenes permitidos para CORS")

    # =========== Embeddings =========== 
    # Nota: Las configuraciones específicas de embeddings se han migrado al servicio de embeddings
    # Solo se mantienen los modelos predeterminados que son usados por múltiples servicios
    
    # =========== Query Service ===========
    default_similarity_top_k: int = Field(4, description="Número de resultados similares por defecto")
    similarity_threshold: float = Field(0.7, description="Umbral de similitud para resultados")
    
    # =========== Agent Service ===========
    agent_default_message_limit: int = Field(50, description="Límite de mensajes por defecto para agentes")
    agent_streaming_timeout: int = Field(300, description="Timeout para streaming de agentes (segundos)")
    model_capacity: Dict[str, int] = Field(
        default_factory=lambda: {
            "gpt-3.5-turbo": 4096,
            "gpt-4": 8192,
            "gpt-4-turbo": 16384,
            "llama3": 8192,
            "qwen3:1.7b": 8192,
        },
        description="Capacidad de tokens por modelo"
    )
    
    # =========== Límites para streaming ===========
    streaming_timeout: int = Field(60, description="Timeout para streaming (segundos)")
    
    # =========== Manejo de recursos ===========
    max_query_retries: int = Field(3, description="Máximo de reintentos de consulta")
    chunk_size: int = Field(512, description="Tamaño de fragmentos para indexación")
    chunk_overlap: int = Field(51, description="Solapamiento entre fragmentos")
    max_workers: int = Field(4, description="Máximo de workers para procesamiento")
    max_doc_size_mb: int = Field(10, description="Tamaño máximo de documentos (MB)")
    
    # =========== Rate Limiting ===========
    enable_rate_limiting: bool = Field(True, description="Activar limitación de tasa")
    default_rate_limit: int = Field(10, description="Límite de tasa por defecto (req/min)")
    
    # =========== Tracking y Reconciliación ===========
    enable_usage_tracking: bool = Field(True, env="ENABLE_USAGE_TRACKING", description="Habilitar tracking de uso")
    reconciliation_schedule_daily: str = Field("0 2 * * *", env="RECONCILIATION_SCHEDULE_DAILY", description="Cron schedule para reconciliación diaria")
    reconciliation_schedule_weekly: str = Field("0 3 * * 0", env="RECONCILIATION_SCHEDULE_WEEKLY", description="Cron schedule para reconciliación semanal")
    reconciliation_schedule_monthly: str = Field("0 4 1 * *", env="RECONCILIATION_SCHEDULE_MONTHLY", description="Cron schedule para reconciliación mensual")
    
    # Límites para alertas de reconciliación
    reconciliation_alert_threshold: int = Field(1000, env="RECONCILIATION_ALERT_THRESHOLD", description="Umbral para alertas de reconciliación")
    reconciliation_critical_threshold: int = Field(5000, env="RECONCILIATION_CRITICAL_THRESHOLD", description="Umbral crítico para alertas de reconciliación")
    
    # Configuración de notificaciones
    slack_webhook_url: Optional[str] = Field(None, env="SLACK_WEBHOOK_URL", description="URL del webhook de Slack para notificaciones")
    alert_notifications_enabled: bool = Field(True, env="ALERT_NOTIFICATIONS_ENABLED", description="Habilitar notificaciones de alertas")
    monitoring_enabled: bool = Field(True, env="MONITORING_ENABLED", description="Habilitar sistema de monitorización")
    
    # Factores de coste por modelo
    model_cost_factors: Dict[str, float] = Field(
        default_factory=lambda: {
            "gpt-4": 20.0,  # Base: 1.0, 20x más costoso
            "gpt-4-32k": 40.0,  # Base: 1.0, 40x más costoso
            "gpt-3.5-turbo": 1.0,  # Base
            "llama2-70b": 10.0,  # Base: 1.0, 10x más costoso
            "claude-2": 15.0,  # Base: 1.0, 15x más costoso
        },
        description="Factores de coste relativo por modelo"
    )
    
    @validator("redis_url")
    def validate_redis_url(cls, v):
        """Validar que la URL de Redis siga el formato correcto"""
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("La URL de Redis debe comenzar con redis:// o rediss://")
        return v

    @validator("service_name")
    def validate_service_name(cls, v):
        """Validar que el nombre del servicio sea válido"""
        valid_services = ["agent-service", "embedding-service", "query-service", "ingestion-service"]
        if v not in valid_services and not v.endswith("-service"):
            # En modo desarrollo permitimos más flexibilidad
            logger.warning(f"Servicio {v} no estándar, asegúrese de usarlo solo en desarrollo")
        return v
    
    class Config:
        """Configuración para Pydantic"""
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

def get_settings(tenant_id: Optional[str] = None) -> Settings:
    """
    Obtiene la configuración con caché para el servicio.
    
    El sistema de caché incluye:
    - TTL automático de 5 minutos
    - Invalidación manual mediante invalidate_settings_cache()
    - Límite de 100 configuraciones en caché
    - Soporte para actualización por tenant específico
    
    Returns:
        Settings: Objeto de configuración.
        
    Raises:
        ConfigurationError: Si hay un problema al cargar configuraciones
    """
    # Importación tardía para evitar dependencias circulares
    from ..errors.exceptions import ConfigurationError, ErrorCode
    
    # Variables para caché
    global _settings_last_refresh, _settings_ttl
    
    # Claves de contexto para logs
    error_context = {"function": "get_settings"}
    if tenant_id:
        error_context["tenant_id"] = tenant_id
    
    try:
        # Verificar si hay una versión cacheada válida
        if tenant_id in _settings_last_refresh:
            # Verificar si ha expirado el TTL
            if time.time() - _settings_last_refresh[tenant_id] < _settings_ttl:
                # Obtener de caché LRU
                try:
                    settings = _get_settings_lru(tenant_id)
                    return settings
                except Exception as e:
                    logger.warning(f"Error al recuperar settings de caché: {e}", extra=error_context)
                    # Continuar para regenerar
        
        # Si llegamos aquí, necesitamos crear una nueva configuración
        # Crear objeto Settings
        settings = Settings()
        
        # Actualizar timestamp de última actualización
        _settings_last_refresh[tenant_id] = time.time()
        
        # Actualizar el TTL desde la configuración
        _settings_ttl = settings.settings_ttl
        
        # Si está habilitado, cargar configuraciones desde Supabase
        if settings.load_config_from_supabase:
            try:
                # Importación tardía para evitar dependencias circulares
                from .supabase import get_tenant_config
                
                # Cargar configuraciones específicas de tenant desde Supabase
                tenant_config = get_tenant_config(tenant_id or settings.default_tenant_id)
                
                # Aplicar configuraciones
                if tenant_config:
                    for key, value in tenant_config.items():
                        if hasattr(settings, key) and settings.override_settings_from_env:
                            setattr(settings, key, value)
                            logger.debug(f"Configuración de Supabase aplicada: {key}={value}")
            except Exception as e:
                error_message = f"Error al cargar configuraciones desde Supabase: {e}"
                logger.warning(error_message, extra=error_context)
                # Continuar con la configuración predeterminada
        
        # Si estamos en modo desarrollo y ha fallado Supabase, usar mocks
        environment = settings.environment
        if settings.mock_supabase:
            try:
                # Importación tardía para evitar dependencias circulares
                from .mock_data import get_mock_config
                
                # Aplicar configuraciones mock
                mock_config = get_mock_config(tenant_id or settings.default_tenant_id)
                if mock_config:
                    for key, value in mock_config.items():
                        if hasattr(settings, key):
                            setattr(settings, key, value)
                    logger.debug("Configuraciones de mock aplicadas")
            except Exception as e:
                error_message = f"Error al cargar configuraciones mock: {e}"
                logger.warning(error_message, extra=error_context)
        
        # Actualizar timestamp de última actualización
        _settings_last_refresh[tenant_id] = time.time()
        
        # Guardar en caché LRU
        _add_settings_to_lru(tenant_id, settings)
        
        return settings
        
    except Exception as e:
        error_message = f"Error al obtener configuraciones: {e}"
        logger.error(error_message, extra=error_context, exc_info=True)
        raise ConfigurationError(
            message=error_message,
            error_code=ErrorCode.CONFIGURATION_ERROR
        )

@lru_cache(maxsize=100)
def _get_settings_lru(tenant_id: Optional[str]) -> Settings:
    """Caché LRU para objetos Settings."""
    # Función auxiliar para el sistema de caché LRU
    # Cuando se llama por primera vez con un tenant_id, retornará una instancia de Settings
    # Las llamadas posteriores con el mismo tenant_id retornarán la instancia cacheada
    return Settings()

def _add_settings_to_lru(tenant_id: Optional[str], settings: Settings) -> None:
    """Agrega un objeto Settings a la caché LRU."""
    try:
        # En Python 3.10, los objetos decorados con lru_cache
        # tienen una estructura interna diferente.
        # La forma más segura de gestionar la caché es simplemente
        # limpiarla y permitir que se regenere en la siguiente llamada
        _get_settings_lru.cache_clear()
        
        # La próxima vez que get_settings llame a _get_settings_lru
        # con el mismo tenant_id, se almacenará el resultado en caché
    except Exception as e:
        logger.warning(f"Error manipulando caché LRU: {e}")

def get_service_settings(service_name: str, service_version: Optional[str] = None, tenant_id: Optional[str] = None) -> Settings:
    """
    Obtiene la configuración específica para un servicio, extendiendo la configuración base.
    
    Esta función centraliza las configuraciones específicas de cada servicio,
    evitando duplicación de código y manteniendo una única fuente de verdad.
    
    Args:
        service_name: Nombre del servicio (agent-service, embedding-service, etc.)
        service_version: Versión opcional del servicio
        tenant_id: ID opcional del tenant
        
    Returns:
        Settings: Configuración personalizada para el servicio
        
    Raises:
        ConfigurationError: Si hay un problema al obtener las configuraciones
    """
    # Importación tardía para evitar dependencias circulares
    from ..errors.handlers import handle_errors
    from ..errors.exceptions import ConfigurationError
    
    # Aplicamos el decorador dinámicamente
    @handle_errors
    async def _get_service_settings_impl(service_name: str, service_version: Optional[str] = None, tenant_id: Optional[str] = None) -> Settings:
        # Obtener configuración base
        settings = get_settings(tenant_id=tenant_id)
        
        # Establecer nombre y versión del servicio
        settings.service_name = service_name
        if service_version:
            settings.service_version = service_version
        else:
            settings.service_version = os.getenv("SERVICE_VERSION", "1.0.0")
        
        # Aplicar configuraciones específicas según el servicio
        if service_name == "agent-service":
            # Configuraciones específicas para agentes
            settings.agent_default_message_limit = int(os.getenv("AGENT_DEFAULT_MESSAGE_LIMIT", "50"))
            settings.agent_streaming_timeout = int(os.getenv("AGENT_STREAMING_TIMEOUT", "300"))
            settings.model_capacity = {
                "gpt-3.5-turbo": 4096,
                "gpt-4": 8192,
                "gpt-4-turbo": 16384,
                "llama3": 8192,
            }
        
        elif service_name == "embedding-service":
            # Configuraciones específicas para embeddings
            settings.embedding_cache_enabled = os.getenv("EMBEDDING_CACHE_ENABLED", "true").lower() in ["true", "1", "yes"]
            settings.embedding_batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
            settings.max_embedding_batch_size = int(os.getenv("MAX_EMBEDDING_BATCH_SIZE", "10"))
        
        elif service_name == "query-service":
            # Configuraciones específicas para queries
            settings.default_similarity_top_k = int(os.getenv("DEFAULT_SIMILARITY_TOP_K", "4"))
            settings.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
            settings.max_query_retries = int(os.getenv("MAX_QUERY_RETRIES", "3"))
        
        elif service_name == "ingestion-service":
            # Configuraciones específicas para ingestion
            settings.max_doc_size_mb = int(os.getenv("MAX_DOC_SIZE_MB", "10"))
            settings.chunk_size = int(os.getenv("CHUNK_SIZE", "512"))
            settings.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "51"))
            settings.max_workers = int(os.getenv("MAX_WORKERS", "4"))
        
        logger.debug(f"Configuración específica para {service_name} cargada correctamente")
        return settings
    
    # Devolvemos una instancia directamente para uso sincrónico
    # Esta implementación evita el warning de coroutine no esperada
    settings = get_settings(tenant_id=tenant_id)
    
    # Establecer nombre y versión del servicio
    settings.service_name = service_name
    if service_version:
        settings.service_version = service_version
    else:
        settings.service_version = os.getenv("SERVICE_VERSION", "1.0.0")
    
    # Aplicar configuraciones específicas según el servicio
    if service_name == "agent-service":
        # Configuraciones específicas para agentes
        settings.agent_default_message_limit = int(os.getenv("AGENT_DEFAULT_MESSAGE_LIMIT", "50"))
        settings.agent_streaming_timeout = int(os.getenv("AGENT_STREAMING_TIMEOUT", "300"))
        settings.model_capacity = {
            "gpt-3.5-turbo": 4096,
            "gpt-4": 8192,
            "gpt-4-turbo": 16384,
            "llama3": 8192,
        }
    
    elif service_name == "embedding-service":
        # Configuraciones específicas para embeddings se manejan en embedding-service/config/settings.py
        # No asignamos configuraciones específicas aquí para evitar errores con campos no definidos
        pass
    
    elif service_name == "query-service":
        # Configuraciones específicas para queries
        settings.default_similarity_top_k = int(os.getenv("DEFAULT_SIMILARITY_TOP_K", "4"))
        settings.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
        settings.max_query_retries = int(os.getenv("MAX_QUERY_RETRIES", "3"))
    
    elif service_name == "ingestion-service":
        # Configuraciones específicas para ingestion
        settings.max_doc_size_mb = int(os.getenv("MAX_DOC_SIZE_MB", "10"))
        settings.chunk_size = int(os.getenv("CHUNK_SIZE", "512"))
        settings.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "51"))
        settings.max_workers = int(os.getenv("MAX_WORKERS", "4"))
    
    logger.debug(f"Configuración específica para {service_name} cargada correctamente")
    return settings

def invalidate_settings_cache(tenant_id: Optional[str] = None) -> None:
    """
    Fuerza la recarga de configuraciones en la próxima llamada a get_settings().
    
    Esta función puede ser llamada cuando se sabe que las configuraciones
    han cambiado en Supabase o cuando se desea forzar una recarga.
    
    Args:
        tenant_id: ID del tenant específico o None para todos
    """
    global _force_settings_reload, _settings_last_refresh
    
    if tenant_id is None:
        # Invalidar todas las configuraciones
        _force_settings_reload = True
        _settings_last_refresh = {}
        # Limpiar toda la caché LRU
        _get_settings_lru.cache_clear()
        logger.info("Cache de configuraciones global invalidada")
    else:
        # Invalidar solo el tenant específico
        if tenant_id in _settings_last_refresh:
            del _settings_last_refresh[tenant_id]
            # Forzamos recarga para el próximo acceso
            _force_settings_reload = True
            logger.info(f"Cache de configuraciones para tenant {tenant_id} invalidada")