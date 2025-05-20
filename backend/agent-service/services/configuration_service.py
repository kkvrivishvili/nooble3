"""
Servicio de configuración para agentes con soporte para editor visual.

Implementa funcionalidades para gestionar configuraciones de agentes
desde un editor visual en el frontend.
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from common.context.decorators import with_context, Context
from common.errors.handlers import handle_errors, ServiceError
from common.cache import CacheManager, get_with_cache_aside
from common.config import get_settings
from common.config.tiers import get_tier_limits
from common.db.supabase import get_supabase_client
from common.cache.helpers import standardize_llama_metadata

logger = logging.getLogger(__name__)

class AgentConfigurationService:
    """
    Servicio para configuración de agentes con soporte para editor visual.
    
    Permite gestionar configuraciones de agentes, validar opciones según tier
    del tenant, y soportar un editor visual en el frontend.
    """
    
    def __init__(self, service_registry):
        """Inicializa el servicio de configuración con acceso al registro de servicios."""
        self.service_registry = service_registry
        self.settings = get_settings()
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_agent_configuration(self, tenant_id: str, agent_id: str, ctx: Context = None) -> Dict[str, Any]:
        """
        Obtiene la configuración completa de un agente con soporte para editor visual.
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID del agente
            ctx: Contexto opcional
            
        Returns:
            Configuración completa del agente
            
        Raises:
            ValueError: Si no se encuentra el agente
            ServiceError: Si hay errores de acceso
        """
        config, metrics = await get_with_cache_aside(
            data_type="agent_editor_config",
            resource_id=agent_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_agent_config_from_db,
            generate_func=None,  # No hay generación automática
            ttl=CacheManager.ttl_short  # 5 minutos para reflejar cambios rápido
        )
        
        if not config:
            raise ValueError(f"Agente no encontrado: {agent_id}")
            
        # Añadir metadatos para editor visual
        config["_editor"] = {
            "last_edited": datetime.now().isoformat(),
            "editor_version": "1.0",
            "visual_layout": config.get("_editor", {}).get("visual_layout", {})
        }
        
        return config
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def save_agent_configuration(
        self, 
        tenant_id: str, 
        agent_id: str, 
        config: Dict[str, Any],
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Guarda la configuración de un agente desde el editor visual.
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID del agente
            config: Nueva configuración del agente
            ctx: Contexto opcional
            
        Returns:
            Configuración guardada con metadatos actualizados
            
        Raises:
            ValueError: Si la configuración es inválida
            ServiceError: Si hay errores de acceso
        """
        # Validar configuración según tier
        await self._validate_config_for_tier(tenant_id, config)
        
        # Añadir metadatos de edición
        config["_editor"] = {
            **config.get("_editor", {}),
            "last_edited": datetime.now().isoformat(),
            "editor_version": "1.0",
            "edited_by": ctx.get_user_id() if ctx and hasattr(ctx, "get_user_id") else "system"
        }
        
        # Guardar en caché primero
        await CacheManager.set(
            data_type="agent_editor_config",
            resource_id=agent_id,
            value=config,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_short
        )
        
        # Luego persistir en BD
        await self._persist_agent_config_to_db(tenant_id, agent_id, config)
        
        # Invalidar otras cachés relacionadas
        await CacheManager.invalidate(
            tenant_id=tenant_id,
            data_type="agent_config",
            resource_id=agent_id
        )
        
        return {
            "agent_id": agent_id,
            "config": config,
            "saved_at": datetime.now().isoformat()
        }
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_available_tools(self, tenant_id: str, tenant_tier: Optional[str] = None, ctx: Context = None) -> List[Dict[str, Any]]:
        """
        Obtiene las herramientas disponibles para un tenant basado en su tier.
        
        Args:
            tenant_id: ID del tenant
            tenant_tier: Tier del tenant (si es None, se detectará automáticamente)
            ctx: Contexto opcional
            
        Returns:
            Lista de herramientas disponibles con metadatos para el editor
            
        Raises:
            ServiceError: Si hay errores de acceso
        """
        # Determinar tier si no se proporciona
        if not tenant_tier:
            tenant_info = await self._get_tenant_info(tenant_id)
            tenant_tier = tenant_info.get("tier", "free")
        
        # Clave de caché según tenant y tier
        cache_key = f"tools_{tenant_tier}"
        
        # Intentar obtener de caché
        tools = await CacheManager.get(
            data_type="available_tools",
            resource_id=cache_key,
            tenant_id=tenant_id
        )
        
        if tools:
            return tools
        
        # Si no está en caché, obtener límites según tier
        tier_limits = get_tier_limits(tenant_tier, tenant_id)
        max_tools = tier_limits.get("max_tools_per_agent", 2)
        
        # Obtener todas las herramientas disponibles
        all_tools = await self._get_all_tools()
        
        # Filtrar según tier
        available_tools = []
        for tool in all_tools:
            # Herramientas básicas siempre disponibles
            if tool.get("tier", "free") in ["free", tenant_tier]:
                # Añadir metadatos para editor visual
                tool_with_editor = {
                    **tool,
                    "_editor": {
                        "available": True,
                        "requires_configuration": tool.get("requires_configuration", False),
                        "ui_component": tool.get("ui_component", "DefaultToolCard"),
                        "category": tool.get("category", "general")
                    }
                }
                available_tools.append(tool_with_editor)
            else:
                # Incluir herramienta como no disponible para mostrar en el editor
                tool_with_editor = {
                    **tool,
                    "_editor": {
                        "available": False,
                        "requires_upgrade": True,
                        "min_tier": tool.get("tier", "pro"),
                        "ui_component": "LockedToolCard",
                        "category": tool.get("category", "general")
                    }
                }
                available_tools.append(tool_with_editor)
        
        # Guardar en caché
        await CacheManager.set(
            data_type="available_tools",
            resource_id=cache_key,
            value=available_tools,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard
        )
        
        return available_tools
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def create_agent_from_template(
        self, 
        tenant_id: str, 
        template_id: str,
        agent_name: str,
        customizations: Optional[Dict[str, Any]] = None,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Crea un nuevo agente basado en una plantilla predefinida.
        
        Args:
            tenant_id: ID del tenant
            template_id: ID de la plantilla
            agent_name: Nombre para el nuevo agente
            customizations: Personalizaciones específicas
            ctx: Contexto opcional
            
        Returns:
            Datos del agente creado
            
        Raises:
            ValueError: Si la plantilla no existe
            ServiceError: Si hay errores de acceso
        """
        # Obtener plantilla
        template = await self._get_template_by_id(template_id)
        if not template:
            raise ValueError(f"Plantilla no encontrada: {template_id}")
        
        # Crear ID para el nuevo agente
        agent_id = f"agent_{uuid.uuid4().hex}"
        
        # Combinar plantilla con customizaciones
        base_config = template.get("config", {})
        custom_config = customizations or {}
        
        # Aplicar personalizaciones
        merged_config = {**base_config}
        for key, value in custom_config.items():
            if key in merged_config and isinstance(merged_config[key], dict) and isinstance(value, dict):
                # Fusionar diccionarios anidados
                merged_config[key] = {**merged_config[key], **value}
            else:
                # Sobrescribir valor
                merged_config[key] = value
        
        # Añadir metadatos básicos
        merged_config["name"] = agent_name
        merged_config["created_at"] = datetime.now().isoformat()
        merged_config["created_by"] = ctx.get_user_id() if ctx and hasattr(ctx, "get_user_id") else "system"
        merged_config["template_id"] = template_id
        
        # Validar configuración según tier
        await self._validate_config_for_tier(tenant_id, merged_config)
        
        # Persistir en BD y caché
        await self._persist_agent_config_to_db(tenant_id, agent_id, merged_config)
        await CacheManager.set(
            data_type="agent_editor_config",
            resource_id=agent_id,
            value=merged_config,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_short
        )
        
        return {
            "agent_id": agent_id,
            "name": agent_name,
            "config": merged_config,
            "created_at": datetime.now().isoformat(),
            "template_id": template_id
        }
    
    async def _fetch_agent_config_from_db(self, agent_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Recupera configuración de agente desde la base de datos."""
        try:
            table_name = self.settings.TABLES["agents"]
            supabase = get_supabase_client()
            
            result = (supabase.table(table_name)
                     .select("*")
                     .eq("tenant_id", tenant_id)
                     .eq("agent_id", agent_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                agent_data = result.data[0]
                return agent_data.get("config", {})
            
            return None
        except Exception as e:
            logger.error(f"Error recuperando configuración de agente de BD: {str(e)}")
            return None
    
    async def _persist_agent_config_to_db(self, tenant_id: str, agent_id: str, config: Dict[str, Any]) -> None:
        """Persiste configuración de agente a la base de datos."""
        try:
            table_name = self.settings.TABLES["agents"]
            supabase = get_supabase_client()
            
            # Verificar si ya existe
            result = (supabase.table(table_name)
                     .select("agent_id")
                     .eq("tenant_id", tenant_id)
                     .eq("agent_id", agent_id)
                     .execute())
            
            record = {
                "config": config,
                "updated_at": datetime.now().isoformat()
            }
            
            if result.data and len(result.data) > 0:
                # Actualizar existente
                await supabase.table(table_name)\
                    .update(record)\
                    .eq("tenant_id", tenant_id)\
                    .eq("agent_id", agent_id)\
                    .execute()
            else:
                # Insertar nuevo
                record.update({
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "name": config.get("name", "Agente sin nombre"),
                    "created_at": datetime.now().isoformat(),
                    "status": "active"
                })
                await supabase.table(table_name).insert(record).execute()
                
            logger.info(f"Configuración de agente persistida en BD: {agent_id}", 
                       extra={"tenant_id": tenant_id, "agent_id": agent_id})
                       
        except Exception as e:
            logger.error(f"Error persistiendo configuración de agente en BD: {str(e)}", 
                        extra={"tenant_id": tenant_id, "agent_id": agent_id, "error": str(e)})
    
    async def _get_all_tools(self) -> List[Dict[str, Any]]:
        """Obtiene todas las herramientas disponibles en el sistema."""
        # En una implementación real, esto podría venir de una base de datos o archivo de configuración
        # Por ahora, retornamos una lista predefinida
        return [
            {
                "id": "rag_query",
                "name": "RAG Query",
                "description": "Consulta documentos relevantes en colecciones de conocimiento",
                "tier": "free",
                "category": "knowledge",
                "requires_configuration": True,
                "ui_component": "RAGToolConfig",
                "icon": "document-search"
            },
            {
                "id": "web_search",
                "name": "Web Search",
                "description": "Búsqueda en internet para información actualizada",
                "tier": "pro",
                "category": "internet",
                "requires_configuration": False,
                "ui_component": "SearchToolConfig",
                "icon": "globe"
            },
            {
                "id": "embedding_tool",
                "name": "Embedding Generator",
                "description": "Genera embeddings para texto en tiempo real",
                "tier": "free",
                "category": "utility",
                "requires_configuration": False,
                "ui_component": "DefaultToolConfig",
                "icon": "vector"
            },
            {
                "id": "external_api",
                "name": "External API",
                "description": "Integración con APIs externas",
                "tier": "business",
                "category": "integration",
                "requires_configuration": True,
                "ui_component": "APIToolConfig",
                "icon": "server"
            },
            {
                "id": "code_execution",
                "name": "Code Execution",
                "description": "Ejecuta código Python en un entorno aislado",
                "tier": "enterprise",
                "category": "developer",
                "requires_configuration": True,
                "ui_component": "CodeToolConfig",
                "icon": "code"
            }
        ]
    
    async def _get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene una plantilla de agente por su ID."""
        # En una implementación real, esto vendría de la base de datos
        # Por ahora, retornamos plantillas predefinidas
        templates = {
            "customer_service": {
                "id": "customer_service",
                "name": "Asistente de Atención al Cliente",
                "description": "Agente especializado en resolver dudas y problemas de clientes",
                "config": {
                    "name": "Asistente de Atención al Cliente",
                    "description": "Resuelve dudas y problemas de clientes",
                    "instructions": "Eres un asistente de atención al cliente amable y profesional. Tu objetivo es ayudar a resolver dudas y problemas de manera eficiente.",
                    "tools": ["rag_query"],
                    "model": "gpt-3.5-turbo",
                    "memory_enabled": True,
                    "max_tokens": 1000
                }
            },
            "knowledge_base": {
                "id": "knowledge_base",
                "name": "Asistente de Base de Conocimiento",
                "description": "Agente para consultar y responder preguntas sobre documentación",
                "config": {
                    "name": "Asistente de Base de Conocimiento",
                    "description": "Consulta y responde sobre documentación",
                    "instructions": "Eres un asistente especializado en buscar información en la documentación. Responde con precisión citando fuentes.",
                    "tools": ["rag_query", "embedding_tool"],
                    "model": "gpt-4",
                    "memory_enabled": True,
                    "max_tokens": 2000
                }
            },
            "workflow_agent": {
                "id": "workflow_agent",
                "name": "Agente de Flujo de Trabajo",
                "description": "Agente que guía a través de procesos multi-paso",
                "config": {
                    "name": "Agente de Flujo de Trabajo",
                    "description": "Guía a través de procesos multi-paso",
                    "instructions": "Eres un asistente que guía a los usuarios a través de procesos específicos paso a paso. Mantén al usuario enfocado en completar el proceso.",
                    "tools": ["rag_query"],
                    "model": "gpt-4",
                    "memory_enabled": True,
                    "max_tokens": 1500,
                    "workflow_enabled": True
                }
            }
        }
        
        return templates.get(template_id)
    
    async def _get_tenant_info(self, tenant_id: str) -> Dict[str, Any]:
        """Obtiene información del tenant, incluyendo su tier."""
        try:
            table_name = "tenants"  # Nombre de tabla en Supabase
            supabase = get_supabase_client()
            
            result = (supabase.table(table_name)
                     .select("tier")
                     .eq("tenant_id", tenant_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            # Si no se encuentra, asumir tier gratuito
            return {"tier": "free"}
        except Exception as e:
            logger.error(f"Error recuperando información de tenant: {str(e)}")
            return {"tier": "free"}
    
    async def _validate_config_for_tier(self, tenant_id: str, config: Dict[str, Any]) -> None:
        """
        Valida que la configuración sea compatible con el tier del tenant.
        
        Args:
            tenant_id: ID del tenant
            config: Configuración a validar
            
        Raises:
            ValueError: Si la configuración no es válida para el tier
        """
        # Obtener información del tenant
        tenant_info = await self._get_tenant_info(tenant_id)
        tier = tenant_info.get("tier", "free")
        
        # Obtener límites según tier
        tier_limits = get_tier_limits(tier, tenant_id)
        
        # Validar modelo LLM
        model = config.get("model", "gpt-3.5-turbo")
        allowed_models = tier_limits.get("allowed_llm_models", ["gpt-3.5-turbo"])
        if model not in allowed_models:
            raise ValueError(f"Modelo LLM '{model}' no disponible en tier {tier}. Modelos permitidos: {', '.join(allowed_models)}")
        
        # Validar herramientas
        tools = config.get("tools", [])
        max_tools = tier_limits.get("max_tools_per_agent", 2)
        if len(tools) > max_tools:
            raise ValueError(f"Máximo de {max_tools} herramientas permitidas en tier {tier}")
        
        # Verificar herramientas permitidas
        available_tools = await self.get_available_tools(tenant_id, tier)
        available_tool_ids = [t["id"] for t in available_tools if t["_editor"]["available"]]
        
        for tool_id in tools:
            if tool_id not in available_tool_ids:
                raise ValueError(f"Herramienta '{tool_id}' no disponible en tier {tier}")
        
        # Otras validaciones específicas según tier
        if tier == "free" and config.get("workflow_enabled", False):
            raise ValueError("Workflows no disponibles en tier gratuito")
        
        # Si llegamos aquí, la configuración es válida
        return
