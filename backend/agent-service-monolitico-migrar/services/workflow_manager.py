"""
Gestor de flujos de trabajo complejos para agentes.

Implementa funcionalidad para workflows multi-paso con estado persistente.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from common.cache import CacheManager, get_with_cache_aside
from common.context.decorators import with_context, Context
from common.errors.handlers import handle_errors, ServiceError
from common.config import get_settings
from common.tracking import track_cache_metrics
from common.cache.helpers import standardize_llama_metadata
from common.db.supabase import get_supabase_client
from common.db.tables import get_table_name

logger = logging.getLogger(__name__)

class AgentWorkflowManager:
    """
    Gestor de flujos de trabajo complejos con interfaz simplificada.
    
    Permite definir y ejecutar workflows multi-paso para agentes,
    manteniendo estado entre ejecuciones y facilitando la creación
    de flujos complejos con una interfaz de usuario simple.
    """
    
    def __init__(self, service_registry):
        """Inicializa el gestor de workflows con acceso al registro de servicios."""
        self.service_registry = service_registry
        self.settings = get_settings()
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def create_workflow(self, tenant_id: str, workflow_definition: Dict[str, Any], ctx: Context = None) -> str:
        """
        Crea un nuevo workflow basado en una definición.
        
        Args:
            tenant_id: ID del tenant
            workflow_definition: Definición completa del workflow
            ctx: Contexto opcional
            
        Returns:
            ID del workflow creado
            
        Raises:
            ValueError: Si la definición es inválida
            ServiceError: Si hay errores en la creación
        """
        # Validar definición
        self._validate_workflow_definition(workflow_definition)
        
        # Crear ID único
        workflow_id = f"wf_{uuid.uuid4().hex}"
        
        # Preparar definición enriquecida
        enriched_definition = {
            **workflow_definition,
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "created_by": ctx.get_user_id() if ctx and hasattr(ctx, "get_user_id") else "system",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                **workflow_definition.get("metadata", {})
            }
        }
        
        # Guardar definición en caché y BD
        await CacheManager.set(
            data_type="workflow_definition",
            resource_id=workflow_id,
            value=enriched_definition,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_standard  # 1 hora
        )
        
        # Crear estado inicial vacío
        initial_state = {
            "status": "created",
            "current_step": None,
            "completed_steps": [],
            "step_results": {},
            "variables": {},
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        # Guardar estado inicial
        await CacheManager.set(
            data_type="workflow_state",
            resource_id=workflow_id,
            value=initial_state,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_extended  # 24 horas para workflows de larga duración
        )
        
        # Guardar en BD también para persistencia
        await self._persist_workflow_to_db(tenant_id, workflow_id, enriched_definition, initial_state)
        
        return workflow_id
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_workflow_definition(self, tenant_id: str, workflow_id: str, ctx: Context = None) -> Dict[str, Any]:
        """
        Obtiene la definición de un workflow usando el patrón Cache-Aside.
        
        Args:
            tenant_id: ID del tenant
            workflow_id: ID del workflow
            ctx: Contexto opcional
            
        Returns:
            Definición del workflow
            
        Raises:
            ValueError: Si no se encuentra el workflow
            ServiceError: Si hay errores de acceso
        """
        definition, metrics = await get_with_cache_aside(
            data_type="workflow_definition",
            resource_id=workflow_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_workflow_definition_from_db,
            generate_func=None,  # No hay generación automática
            ttl=CacheManager.ttl_standard
        )
        
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")
            
        return definition
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def get_workflow_state(self, tenant_id: str, workflow_id: str, ctx: Context = None) -> Dict[str, Any]:
        """
        Obtiene el estado actual de un workflow usando el patrón Cache-Aside.
        
        Args:
            tenant_id: ID del tenant
            workflow_id: ID del workflow
            ctx: Contexto opcional
            
        Returns:
            Estado actual del workflow
            
        Raises:
            ValueError: Si no se encuentra el workflow
            ServiceError: Si hay errores de acceso
        """
        state, metrics = await get_with_cache_aside(
            data_type="workflow_state",
            resource_id=workflow_id,
            tenant_id=tenant_id,
            fetch_from_db_func=self._fetch_workflow_state_from_db,
            generate_func=None,  # No hay generación automática
            ttl=CacheManager.ttl_extended
        )
        
        if not state:
            raise ValueError(f"Estado de workflow no encontrado: {workflow_id}")
            
        return state
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def execute_workflow_step(
        self, 
        tenant_id: str, 
        workflow_id: str, 
        user_input: Optional[Dict[str, Any]] = None,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Ejecuta el siguiente paso del workflow basado en su estado actual.
        
        Args:
            tenant_id: ID del tenant
            workflow_id: ID del workflow
            user_input: Entrada del usuario para el paso actual
            ctx: Contexto opcional
            
        Returns:
            Resultado de la ejecución del paso
            
        Raises:
            ValueError: Si el workflow ya está completo
            ServiceError: Si hay errores de ejecución
        """
        # Obtener definición y estado actual
        definition = await self.get_workflow_definition(tenant_id, workflow_id, ctx)
        current_state = await self.get_workflow_state(tenant_id, workflow_id, ctx)
        
        # Verificar si el workflow ya está completo
        if current_state.get("status") == "completed":
            return {
                "status": "completed",
                "message": "El workflow ya está completo",
                "result": current_state.get("result", {}),
                "completed_at": current_state.get("completed_at")
            }
        
        # Determinar el siguiente paso a ejecutar
        next_step = self._determine_next_step(definition, current_state, user_input)
        if not next_step:
            # No hay más pasos, el workflow está completo
            final_state = {
                **current_state,
                "status": "completed",
                "current_step": None,
                "result": self._compile_final_result(definition, current_state),
                "completed_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            
            # Guardar estado final
            await CacheManager.set(
                data_type="workflow_state",
                resource_id=workflow_id,
                value=final_state,
                tenant_id=tenant_id,
                ttl=CacheManager.ttl_extended
            )
            
            # Persistir estado final en BD
            await self._persist_workflow_state_to_db(tenant_id, workflow_id, final_state)
            
            return {
                "status": "completed",
                "message": "Workflow completado exitosamente",
                "result": final_state.get("result", {})
            }
        
        # Actualizar estado con el paso actual
        updated_state = {
            **current_state,
            "status": "in_progress",
            "current_step": next_step["id"],
            "last_updated": datetime.now().isoformat()
        }
        
        # Si hay input del usuario, guardarlo en variables
        if user_input:
            updated_state["variables"] = {
                **updated_state.get("variables", {}),
                **user_input
            }
        
        # Guardar estado actualizado
        await CacheManager.set(
            data_type="workflow_state",
            resource_id=workflow_id,
            value=updated_state,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_extended
        )
        
        # Preparar respuesta con información para frontend
        return {
            "status": "in_progress",
            "current_step": next_step,
            "user_input_required": next_step.get("requires_user_input", False),
            "message": next_step.get("message", ""),
            "progress": self._calculate_progress(definition, updated_state)
        }
    
    @handle_errors(error_type="service", log_traceback=True)
    @with_context(tenant=True)
    async def execute_agent_step(
        self, 
        tenant_id: str, 
        workflow_id: str, 
        agent_service: Any,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Ejecuta un paso de workflow que requiere interacción con un agente.
        
        Args:
            tenant_id: ID del tenant
            workflow_id: ID del workflow
            agent_service: Instancia del LangChainAgentService
            ctx: Contexto opcional
            
        Returns:
            Resultado de la ejecución con el agente
            
        Raises:
            ServiceError: Si hay errores de ejecución
        """
        # Obtener definición y estado actual
        definition = await self.get_workflow_definition(tenant_id, workflow_id, ctx)
        current_state = await self.get_workflow_state(tenant_id, workflow_id, ctx)
        
        # Verificar que hay un paso actual de tipo "agent"
        current_step_id = current_state.get("current_step")
        if not current_step_id:
            raise ValueError("No hay paso actual definido en el workflow")
        
        # Encontrar paso actual en la definición
        current_step = None
        for step in definition.get("steps", []):
            if step.get("id") == current_step_id:
                current_step = step
                break
        
        if not current_step:
            raise ValueError(f"Paso {current_step_id} no encontrado en la definición")
            
        if current_step.get("type") != "agent":
            raise ValueError(f"El paso actual no es de tipo agent: {current_step.get('type')}")
        
        # Preparar parámetros para la ejecución
        agent_config = current_step.get("agent_config", {})
        agent_id = agent_config.get("agent_id")
        conversation_id = agent_config.get("conversation_id", f"wf_{workflow_id}_{current_step_id}")
        input_text = self._render_template(current_step.get("input_template", ""), current_state.get("variables", {}))
        
        # Ejecutar agente
        agent_result = await agent_service.execute_agent(
            input_text=input_text,
            agent_id=agent_id,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            ctx=ctx
        )
        
        # Actualizar estado con el resultado
        step_result = {
            "output": agent_result.response,
            "executed_at": datetime.now().isoformat(),
            "metadata": agent_result.metadata
        }
        
        updated_state = {
            **current_state,
            "step_results": {
                **current_state.get("step_results", {}),
                current_step_id: step_result
            },
            "completed_steps": [*current_state.get("completed_steps", []), current_step_id],
            "current_step": None,  # Marcar como listo para el siguiente paso
            "last_updated": datetime.now().isoformat()
        }
        
        # Si el paso define variables de salida, extraerlas
        if "output_variables" in current_step:
            # Aquí podríamos implementar extracción de variables mediante LLM
            # Por ahora simplemente guardamos la respuesta completa
            updated_state["variables"][current_step.get("output_variable", "agent_response")] = agent_result.response
        
        # Guardar estado actualizado
        await CacheManager.set(
            data_type="workflow_state",
            resource_id=workflow_id,
            value=updated_state,
            tenant_id=tenant_id,
            ttl=CacheManager.ttl_extended
        )
        
        # Persistir en BD para durabilidad
        await self._persist_workflow_state_to_db(tenant_id, workflow_id, updated_state)
        
        return {
            "status": "step_completed",
            "step_id": current_step_id,
            "result": step_result,
            "progress": self._calculate_progress(definition, updated_state)
        }
    
    def _validate_workflow_definition(self, definition: Dict[str, Any]) -> None:
        """Valida que la definición del workflow sea correcta."""
        if not isinstance(definition, dict):
            raise ValueError("La definición debe ser un diccionario")
            
        if "steps" not in definition or not isinstance(definition["steps"], list):
            raise ValueError("La definición debe contener una lista de pasos")
            
        if not definition["steps"]:
            raise ValueError("La definición debe contener al menos un paso")
            
        # Validar que cada paso tenga ID único
        step_ids = set()
        for step in definition["steps"]:
            if "id" not in step:
                raise ValueError("Cada paso debe tener un ID")
                
            if step["id"] in step_ids:
                raise ValueError(f"ID de paso duplicado: {step['id']}")
                
            step_ids.add(step["id"])
    
    def _determine_next_step(self, definition: Dict[str, Any], state: Dict[str, Any], user_input: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Determina el siguiente paso a ejecutar en el workflow."""
        steps = definition.get("steps", [])
        completed_steps = set(state.get("completed_steps", []))
        current_step_id = state.get("current_step")
        
        # Si hay un paso actual, verificar si tiene dependencias pendientes
        if current_step_id:
            # El paso actual sigue siendo válido
            for step in steps:
                if step.get("id") == current_step_id:
                    return step
        
        # Buscar el siguiente paso viable
        for step in steps:
            step_id = step.get("id")
            
            # Saltar pasos ya completados
            if step_id in completed_steps:
                continue
                
            # Verificar dependencias
            dependencies = step.get("depends_on", [])
            if all(dep in completed_steps for dep in dependencies):
                return step
        
        # No hay más pasos viables
        return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _persist_workflow_state_to_db(self, tenant_id: str, workflow_id: str, state: Dict[str, Any]) -> None:
        """
        Persiste el estado del workflow en la base de datos.
        
        Args:
            tenant_id: ID del tenant
            workflow_id: ID del workflow
            state: Estado del workflow a persistir
        """
        try:
            # Usar formato estandarizado para nombres de tablas
            workflow_table = get_table_name("workflows")
            state_table = get_table_name("workflow_states")
            supabase = get_supabase_client()
            
            # Buscar si ya existe un registro de estado
            result = await supabase.table(state_table)\
                .select("id")\
                .eq("tenant_id", tenant_id)\
                .eq("workflow_id", workflow_id)\
                .execute()
                
            # Preparar datos para inserción/actualización
            state_data = {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "state": state,
                "updated_at": datetime.now().isoformat()
            }
            
            # Crear o actualizar
            if result.data and len(result.data) > 0:
                # Actualizar registro existente
                await supabase.table(state_table)\
                    .update(state_data)\
                    .eq("tenant_id", tenant_id)\
                    .eq("workflow_id", workflow_id)\
                    .execute()
            else:
                # Crear nuevo registro
                state_data["id"] = str(uuid.uuid4())
                state_data["created_at"] = datetime.now().isoformat()
                await supabase.table(state_table).insert(state_data).execute()
                
            logger.info(f"Estado de workflow persistido: {workflow_id}", 
                      extra={"tenant_id": tenant_id, "workflow_id": workflow_id})
                      
        except Exception as e:
            # Log del error pero no interrumpir el flujo principal
            logger.error(f"Error persistiendo estado de workflow: {str(e)}", 
                       extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "error": str(e)})
            # No relanzar la excepción para evitar interrumpir el flujo
    
    def _calculate_progress(self, definition: Dict[str, Any], state: Dict[str, Any]) -> float:
        """Calcula el progreso actual del workflow como porcentaje (0-100)."""
        if state.get("status") == "completed":
            return 100.0
            
        total_steps = len(definition.get("steps", []))
        if total_steps == 0:
            return 100.0
            
        completed_steps = len(state.get("completed_steps", []))
        return min(100.0, (completed_steps / total_steps) * 100)
    
    def _compile_final_result(self, definition: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Compila el resultado final del workflow."""
        # Por defecto, devolver todas las variables y resultados de pasos
        result = {
            "variables": state.get("variables", {}),
            "step_results": state.get("step_results", {})
        }
        
        # Si hay un template de resultado final, usarlo
        if "result_template" in definition:
            # Aquí podríamos implementar plantillas avanzadas
            # Por ahora simplemente devolvemos el resultado completo
            pass
            
        return result
    
    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Renderiza un template con variables."""
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _fetch_workflow_definition_from_db(self, workflow_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Recupera definición de workflow desde la base de datos."""
        try:
            table_name = self.settings.TABLES["workflows"]
            supabase = get_supabase_client()
            
            result = (supabase.table(table_name)
                     .select("definition")
                     .eq("tenant_id", tenant_id)
                     .eq("workflow_id", workflow_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                return result.data[0].get("definition", {})
            
            return None
        except Exception as e:
            logger.error(f"Error recuperando workflow de BD: {str(e)}")
            return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _fetch_workflow_state_from_db(self, workflow_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Recupera estado de workflow desde la base de datos."""
        try:
            table_name = self.settings.TABLES["workflow_states"]
            supabase = get_supabase_client()
            
            result = (supabase.table(table_name)
                     .select("state")
                     .eq("tenant_id", tenant_id)
                     .eq("workflow_id", workflow_id)
                     .execute())
                     
            if result.data and len(result.data) > 0:
                return result.data[0].get("state", {})
            
            return None
        except Exception as e:
            logger.error(f"Error recuperando estado de workflow de BD: {str(e)}")
            return None
    
    @handle_errors(error_type="service", log_traceback=True)
    async def _persist_workflow_to_db(
        self, 
        tenant_id: str, 
        workflow_id: str, 
        definition: Dict[str, Any],
        initial_state: Dict[str, Any]
    ) -> None:
        """Persiste el workflow y su estado inicial en la base de datos."""
        try:
            workflow_table = self.settings.TABLES["workflows"]
            state_table = self.settings.TABLES["workflow_states"]
            supabase = get_supabase_client()
            
            # Guardar definición
            workflow_record = {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "definition": definition,
                "created_at": datetime.now().isoformat()
            }
            await supabase.table(workflow_table).insert(workflow_record).execute()
            
            # Guardar estado inicial
            state_record = {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "state": initial_state,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            await supabase.table(state_table).insert(state_record).execute()
            
            logger.info(f"Workflow persistido en BD: {workflow_id}", 
                       extra={"tenant_id": tenant_id, "workflow_id": workflow_id})
                       
        except Exception as e:
            logger.error(f"Error persistiendo workflow en BD: {str(e)}", 
                        extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "error": str(e)})
    
    @handle_errors(error_type="database", log_traceback=True)
    async def _persist_workflow_state_to_db(self, tenant_id: str, workflow_id: str, state: Dict[str, Any]) -> None:
        """Persiste el estado actualizado del workflow en la base de datos."""
        try:
            table_name = self.settings.TABLES["workflow_states"]
            supabase = get_supabase_client()
            
            # Verificar si existe para actualizar, o crear nuevo
            result = (supabase.table(table_name)
                     .select("workflow_id")
                     .eq("tenant_id", tenant_id)
                     .eq("workflow_id", workflow_id)
                     .execute())
                     
            record = {
                "state": state,
                "updated_at": datetime.now().isoformat()
            }
            
            if result.data and len(result.data) > 0:
                # Actualizar existente
                await supabase.table(table_name)\
                    .update(record)\
                    .eq("tenant_id", tenant_id)\
                    .eq("workflow_id", workflow_id)\
                    .execute()
            else:
                # Insertar nuevo (caso poco probable después de persistir inicial)
                record.update({
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "created_at": datetime.now().isoformat()
                })
                await supabase.table(table_name).insert(record).execute()
                
            logger.info(f"Estado de workflow persistido en BD: {workflow_id}", 
                       extra={"tenant_id": tenant_id, "workflow_id": workflow_id})
                       
        except Exception as e:
            logger.error(f"Error persistiendo estado de workflow en BD: {str(e)}", 
                        extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "error": str(e)})
