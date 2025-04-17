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
from ..errors.handlers import handle_errors
from ..errors.exceptions import ConfigurationError, ErrorCode

# Eliminamos importaciones a nivel de módulo para evitar ciclos
# Ya no importamos aquí:
# from .schema import get_service_configurations, get_mock_configurations
# from .tiers import default_tier_limits, get_tier_limits

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
    default_tenant_id: str = Field("default", description="ID del tenant por defecto")
    validate_tenant_access: bool = Field(False, description="Validar que el tenant esté activo")
    
    # =========== Logging ===========
    log_level: str = Field("INFO", description="Nivel de logging")
    
    # =========== Caching y Redis ===========
    redis_url: str = Field("redis://localhost:6379", description="URL de Redis")
    cache_ttl: int = Field(86400, description="Tiempo de vida de caché en segundos")
    
    # =========== Supabase ===========
    supabase_url: str = Field(..., env="SUPABASE_URL", description="URL de Supabase")
    supabase_key: str = Field(..., env="SUPABASE_KEY", description="Clave de Supabase")
    supabase_service_key: Optional[str] = Field(None, env="SUPABASE_SERVICE_KEY", description="Clave de servicio de Supabase (service role)")
    supabase_jwt_secret: str = Field("super-secret-jwt-token-with-at-least-32-characters-long", description="JWT Secret para verificación de tokens")
    
    # =========== Rate Limiting ===========
    rate_limit_enabled: bool = Field(True, description="Habilitar límite de tasa")
    rate_limit_free_tier: int = Field(600, description="Número de solicitudes permitidas en el periodo para el plan gratuito")
    rate_limit_pro_tier: int = Field(1200, description="Número de solicitudes permitidas en el periodo para el plan pro")
    rate_limit_business_tier: int = Field(3000, description="Número de solicitudes permitidas en el periodo para el plan empresarial")
    rate_limit_period: int = Field(60, description="Periodo en segundos para el límite de tasa")
    
    # =========== OpenAI / Ollama ===========
    openai_api_key: str = Field(..., env="OPENAI_API_KEY", description="Clave API de OpenAI")
    use_ollama: bool = Field(False, description="Usar Ollama en lugar de OpenAI")
    ollama_base_url: str = Field("http://ollama:11434", description="URL base de Ollama")
    
    # =========== Configuración de LLM ===========
    default_llm_model: str = Field("gpt-3.5-turbo", description="Modelo LLM por defecto")
    agent_default_temperature: float = Field(0.7, description="Temperatura para LLM")
    max_tokens_per_response: int = Field(2048, description="Máximo de tokens por respuesta")
    system_prompt_template: str = Field("Eres un asistente AI llamado {agent_name}. {agent_instructions}", description="Plantilla para prompt de sistema")
    agent_default_message_limit: int = Field(50, description="Número máximo de mensajes por defecto para el agente")
    
    # =========== Configuración de Embeddings ===========
    default_embedding_model: str = Field("text-embedding-3-small", description="Modelo de embeddings por defecto")
    embedding_cache_enabled: bool = Field(True, description="Habilitar caché de embeddings")
    embedding_batch_size: int = Field(100, description="Tamaño de lote para embeddings")
    max_embedding_batch_size: int = Field(200, description="Tamaño máximo de lote para embeddings")
    max_tokens_per_batch: int = Field(50000, description="Número máximo de tokens por lote de embeddings")
    max_token_length_per_text: int = Field(8000, description="Límite de tokens para textos individuales en embeddings")
    default_embedding_dimension: int = Field(1536, description="Dimensión del vector de embedding por defecto")
    
    # =========== Configuración de Consultas ===========
    default_similarity_top_k: int = Field(4, description="Número de resultados similares a recuperar por defecto")
    default_response_mode: str = Field("compact", description="Modo de respuesta por defecto")
    similarity_threshold: float = Field(0.7, description="Umbral de similitud mínima")
    
    # =========== Flags de carga de configuración ===========
    load_config_from_supabase: bool = Field(False, description="Cargar configuración desde Supabase")
    use_mock_config: bool = Field(False, description="Usar configuración mock si no hay datos en Supabase")
    
    # =========== Flags de tracking ===========
    enable_usage_tracking: bool = Field(True, description="Habilitar tracking de uso")
    model_cost_factors: Dict[str, float] = Field(default_factory=lambda: {
        "gpt-4": 2.0,
        "gpt-4-turbo": 1.5,
        "gpt-3.5-turbo": 1.0,
        "text-embedding-3-small": 0.8,
        "text-embedding-3-large": 1.2,
    }, description="Factores de costo por modelo para contabilización de tokens")
    
    # =========== Métodos de ayuda ===========
    def get_service_configuration(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene el esquema de configuración para un servicio específico.
        """
        from .schema import get_service_configurations
        return get_service_configurations(service_name or self.service_name)
    
    def get_mock_configuration(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene configuraciones mock para un servicio específico.
        """
        from .schema import get_mock_configurations
        return get_mock_configurations(service_name or self.service_name)
    
    def use_mock_if_empty(self, service_name: Optional[str] = None, tenant_id: Optional[str] = None):
        """
        Establece configuraciones mock si no hay datos en Supabase.
        """
        if not self.use_mock_config:
            return
            
        # Obtener configuraciones del tenant
        tenant_id = tenant_id or self.default_tenant_id
        
        from ..db.supabase import get_tenant_configurations
        configs = get_tenant_configurations(tenant_id=tenant_id, environment=self.environment)
        
        # Si no hay configuraciones, usar mock
        if not configs:
            logger.warning(f"No hay configuraciones para tenant {tenant_id}. Usando configuración mock.")
            mock_configs = self.get_mock_configuration(service_name or self.service_name)
            
            # Establecer las configuraciones mock en esta instancia
            for key, value in mock_configs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
    
    @validator('default_llm_model')
    def get_effective_llm_model(cls, v, values):
        """
        Determina el modelo LLM efectivo basado en la configuración.
        """
        if values.get('use_ollama', False):
            return values.get('default_ollama_llm_model', "llama3")
        return values.get('default_openai_llm_model', v)
    
    @validator('default_embedding_model')
    def get_effective_embedding_model(cls, v, values):
        """
        Determina el modelo de embedding efectivo basado en la configuración.
        """
        if values.get('use_ollama', False):
            return values.get('default_ollama_embedding_model', "nomic-embed-text")
        return values.get('default_openai_embedding_model', v)
    
    def get_tenant_rate_limit(self, tenant_id: str, tier: str, service_name: Optional[str] = None) -> int:
        """
        Obtiene el límite de tasa específico para un tenant, considerando las configuraciones personalizadas.
        
        Args:
            tenant_id: ID del tenant
            tier: Nivel de suscripción ('free', 'pro', 'business')
            service_name: Nombre del servicio (opcional)
            
        Returns:
            int: Límite de solicitudes personalizado para el tenant
        """
        # Llamamos a la función centralizada en tiers.py
        from .tiers import get_tier_rate_limit
        
        try:
            # Intentar obtener de manera asíncrona, pero con fallback 
            # para contextos sincrónicos
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Estamos en contexto asíncrono
                    return asyncio.create_task(get_tier_rate_limit(
                        tenant_id=tenant_id,
                        tier=tier,
                        service_name=service_name
                    ))
                else:
                    # Contexto sincrónico pero tenemos event loop
                    return loop.run_until_complete(get_tier_rate_limit(
                        tenant_id=tenant_id,
                        tier=tier,
                        service_name=service_name
                    ))
            except RuntimeError:
                # No hay event loop disponible, usar valores por defecto
                pass
        except Exception as e:
            logger.warning(f"Error obteniendo límite de tasa para {tenant_id}: {str(e)}")
        
        # Valores por defecto según tier si falla la obtención asíncrona
        tier_limits = {
            "free": self.rate_limit_free_tier,
            "pro": self.rate_limit_pro_tier,
            "business": self.rate_limit_business_tier,
            "enterprise": 5000  # Valor alto por defecto
        }
        return tier_limits.get(tier.lower(), self.rate_limit_free_tier)
    
    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        extra = "allow"  # Permitir campos adicionales no declarados en el modelo


@lru_cache(maxsize=100)  # Limitar tamaño del caché
@handle_errors(error_type="config")
async def get_settings() -> Settings:
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
    global _force_settings_reload, _settings_last_refresh
    
    # Preparar contexto para errores
    error_context = {"function": "get_settings"}
    
    # Determinar el tenant_id antes de todo
    tenant_id = "default"
    try:
        from ..context.vars import get_current_tenant_id
        context_tenant_id = get_current_tenant_id()
        if context_tenant_id and context_tenant_id != "default":
            tenant_id = context_tenant_id
            error_context["tenant_id"] = tenant_id
    except Exception as e:
        # Si falla la obtención del tenant_id del contexto, usar default
        logger.debug(f"No se pudo obtener tenant_id del contexto: {str(e)}")
    
    # Verificar si necesitamos recargar por TTL
    current_time = time.time()
    if tenant_id in _settings_last_refresh:
        time_since_refresh = current_time - _settings_last_refresh[tenant_id]
        if time_since_refresh > _settings_ttl:
            logger.debug(f"TTL excedido para tenant {tenant_id}, forzando recarga de configuraciones")
            _force_settings_reload = True
    
    # Si se ha solicitado recargar, invalidar la función cacheada
    if _force_settings_reload:
        get_settings.cache_clear()
        _force_settings_reload = False
        logger.info("Recargando configuraciones desde cero")
    
    settings = Settings()
    error_context["service"] = settings.service_name
    error_context["environment"] = settings.environment
    
    # Determinar si debemos cargar configuraciones desde Supabase
    should_load_from_supabase = settings.load_config_from_supabase
    
    if should_load_from_supabase:
        try:
            # Importar aquí para evitar dependencias circulares
            from .supabase_loader import override_settings_from_supabase
            from ..context.vars import get_current_tenant_id
            
            # Determinar el tenant_id a utilizar (priorizar contexto si está disponible)
            tenant_id_to_use = getattr(settings, "tenant_id", "default")
            try:
                context_tenant_id = get_current_tenant_id()
                if context_tenant_id and context_tenant_id != "default":
                    tenant_id_to_use = context_tenant_id
                    logger.debug(f"Usando tenant_id del contexto: {tenant_id_to_use}")
            except Exception as e:
                logger.debug(f"No se pudo obtener tenant_id del contexto: {str(e)}")
            
            error_context["tenant_id_to_use"] = tenant_id_to_use
            
            # Cargar configuraciones específicas del tenant desde Supabase
            try:
                settings = override_settings_from_supabase(
                    settings, 
                    tenant_id_to_use,
                    settings.environment
                )
                logger.info(f"Configuración para tenant {tenant_id_to_use} cargada desde Supabase")
            except Exception as supabase_err:
                logger.error(f"Error al cargar configuraciones desde Supabase: {str(supabase_err)}", extra=error_context)
                raise ConfigurationError(
                    message=f"Error al cargar configuraciones desde Supabase: {str(supabase_err)}",
                    error_code=ErrorCode.CONFIGURATION_ERROR.value,
                    context=error_context
                )
        except ImportError as import_err:
            error_context["missing_module"] = str(import_err).split(" ")[-1]
            logger.error(f"Error al importar módulo para configuraciones: {str(import_err)}", extra=error_context)
            raise ConfigurationError(
                message=f"Error al importar módulo para configuraciones: {str(import_err)}", 
                error_code=ErrorCode.MISSING_CONFIGURATION.value,
                context=error_context
            )
    
    # Actualizar timestamp de última recarga
    _settings_last_refresh[tenant_id] = current_time
    
    return settings


def invalidate_settings_cache(tenant_id: Optional[str] = None):
    """
    Fuerza la recarga de configuraciones en la próxima llamada a get_settings().
    
    Esta función puede ser llamada cuando se sabe que las configuraciones
    han cambiado en Supabase o cuando se desea forzar una recarga.
    
    Args:
        tenant_id: ID del tenant específico o None para todos
    """
    global _force_settings_reload, _settings_last_refresh
    
    _force_settings_reload = True
    
    if tenant_id:
        # Eliminar timestamp de tenant específico
        if tenant_id in _settings_last_refresh:
            del _settings_last_refresh[tenant_id]
        logger.info(f"Caché de configuraciones invalidado para tenant {tenant_id}")
    else:
        # Limpiar todos los timestamps
        _settings_last_refresh.clear()
        logger.info("Caché de configuraciones invalidado para todos los tenants")