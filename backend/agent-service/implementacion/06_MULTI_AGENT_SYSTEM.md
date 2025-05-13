# Fase 6: Sistema Multi-Agente

## Visión General

Esta fase aborda la implementación de capacidades multi-agente, permitiendo que varios agentes colaboren y se comuniquen entre sí para resolver tareas complejas que requerirían diferentes áreas de especialización.

## 6.1 Arquitectura Multi-Agente

### 6.1.1 Gestor de Orquestación

```python
from typing import Dict, List, Any, Optional
from common.context import Context
from common.errors.handlers import handle_errors
import asyncio
import uuid

class AgentOrchestrator:
    """
    Coordina la comunicación y ejecución de múltiples agentes especializados.
    
    Permite:
    - Ejecutar agentes en secuencia o en paralelo
    - Enrutar mensajes entre agentes
    - Compartir contexto y resultados
    """
    
    def __init__(self, tenant_id: str, ctx: Optional[Context] = None):
        """
        Inicializa el orquestador de agentes.
        
        Args:
            tenant_id: ID del tenant
            ctx: Contexto con información adicional
        """
        self.tenant_id = tenant_id
        self.ctx = ctx
        self.agent_service = None  # Se inicializa en setup
        self.agent_states = {}
        self.session_id = str(uuid.uuid4())
        self.execution_graph = {}
        
    @handle_errors(error_type="service", log_traceback=True)
    async def setup(self, agent_service):
        """
        Configura el orquestador con una instancia del servicio de agentes.
        
        Args:
            agent_service: Instancia del servicio de agentes
        """
        self.agent_service = agent_service
        return self
    
    @handle_errors(error_type="service", log_traceback=True)
    async def register_workflow(self, workflow_config: Dict[str, Any]):
        """
        Registra un flujo de trabajo multi-agente.
        
        Args:
            workflow_config: Configuración del flujo de trabajo
        """
        self.execution_graph = workflow_config.get("execution_graph", {})
        
        # Validar que todos los agentes existan
        for agent_id in self.execution_graph:
            if not await self.agent_service.agent_exists(self.tenant_id, agent_id):
                raise ValueError(f"Agente {agent_id} no existe para tenant {self.tenant_id}")
                
        return True
        
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_sequential(
        self, 
        agent_ids: List[str], 
        initial_input: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta agentes en secuencia, pasando la salida de uno como entrada al siguiente.
        
        Args:
            agent_ids: Lista de IDs de agentes a ejecutar en secuencia
            initial_input: Entrada inicial para el primer agente
            metadata: Metadatos adicionales
            
        Returns:
            Resultados de la ejecución secuencial
        """
        current_input = initial_input
        results = {}
        metadata = metadata or {}
        
        for idx, agent_id in enumerate(agent_ids):
            # Actualizar metadatos con información de secuencia
            step_metadata = {
                **metadata,
                "sequence_position": idx,
                "total_agents": len(agent_ids),
                "previous_results": results.copy()
            }
            
            # Crear contexto específico para este agente
            agent_ctx = await self._create_agent_context(agent_id)
            
            # Ejecutar agente (con opción de usar el sistema de colas - Fase 7)
            use_async = metadata.get("use_async", False)
            
            response = await self.agent_service.execute_agent(
                input_text=current_input,
                ctx=agent_ctx,
                collection_metadata=step_metadata,
                use_async=use_async
            )
            
            # Procesar respuesta según tipo (síncrona o asíncrona)
            if hasattr(response, 'is_async') and response.is_async:
                # Caso asíncrono: Esperar completitud del trabajo usando el Work Queue Service
                from common.queue.work_queue import WorkQueueService
                work_queue_service = WorkQueueService()
                
                # Registrar el resultado pendiente
                results[agent_id] = {
                    "input": current_input,
                    "status": "processing",
                    "job_id": response.async_job_id,
                    "metadata": {"is_async": True}
                }
                
                # Opcionalmente, esperar completitud si se requiere
                if metadata.get("wait_for_completion", True):
                    job_result = await work_queue_service.wait_for_job_completion(
                        job_id=response.async_job_id,
                        timeout=metadata.get("timeout", 300)  # 5 minutos por defecto
                    )
                    
                    # Actualizar resultado con la respuesta completa
                    if job_result and job_result.get("status") == "completed":
                        current_input = job_result.get("result", {}).get("answer", "")
                        results[agent_id] = {
                            "input": current_input,
                            "output": current_input,
                            "metadata": job_result.get("metadata", {}),
                            "from_async": True
                        }
                    else:
                        # Manejar caso de error o timeout
                        current_input = f"Error procesando respuesta del agente {agent_id}"
                        results[agent_id]["error"] = "Timeout o error en procesamiento asíncrono"
                
            else:
                # Caso síncrono: Procesar normalmente
                results[agent_id] = {
                    "input": current_input,
                    "output": response.answer,
                    "metadata": response.metadata
                }
                # La salida se convierte en entrada del siguiente agente
                current_input = response.answer
            
        return {
            "final_output": current_input,
            "execution_results": results,
            "metadata": {
                "execution_type": "sequential",
                "agent_count": len(agent_ids)
            }
        }
        
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_parallel(
        self, 
        agent_ids: List[str], 
        input_text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta agentes en paralelo con la misma entrada.
        
        Args:
            agent_ids: Lista de IDs de agentes a ejecutar en paralelo
            input_text: Entrada para todos los agentes
            metadata: Metadatos adicionales
            
        Returns:
            Resultados de la ejecución paralela
        """
        metadata = metadata or {}
        tasks = []
        
        # Crear tarea para cada agente
        for agent_id in agent_ids:
            agent_ctx = await self._create_agent_context(agent_id)
            
            # Metadatos específicos de esta ejecución paralela
            agent_metadata = {
                **metadata,
                "execution_type": "parallel",
                "parallel_agent_count": len(agent_ids)
            }
            
            # Crear tarea asíncrona
            task = self.agent_service.execute_agent(
                input_text=input_text,
                ctx=agent_ctx,
                collection_metadata=agent_metadata
            )
            
            tasks.append((agent_id, task))
            
        # Ejecutar todas las tareas en paralelo
        results = {}
        for agent_id, task in tasks:
            try:
                response = await task
                results[agent_id] = {
                    "success": True,
                    "input": input_text,
                    "output": response.answer,
                    "metadata": response.metadata
                }
            except Exception as e:
                results[agent_id] = {
                    "success": False,
                    "input": input_text,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
        
        return {
            "execution_results": results,
            "metadata": {
                "execution_type": "parallel",
                "agent_count": len(agent_ids),
                "success_count": sum(1 for r in results.values() if r.get("success", False))
            }
        }
        
    @handle_errors(error_type="service", log_traceback=True)
    async def execute_workflow(
        self, 
        workflow_id: str, 
        initial_input: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta un flujo de trabajo completo según el grafo de ejecución.
        
        Args:
            workflow_id: ID del flujo de trabajo
            initial_input: Entrada inicial
            metadata: Metadatos adicionales
            
        Returns:
            Resultados del flujo de trabajo completo
        """
        # Esta sería una implementación de un sistema de workflow completo
        # que puede incluir condiciones, bucles, etc.
        # Por ahora, se deja como tarea pendiente
        pass
    
    async def _create_agent_context(self, agent_id: str) -> Context:
        """
        Crea un contexto específico para un agente.
        
        Args:
            agent_id: ID del agente
            
        Returns:
            Contexto para el agente
        """
        # Clonar contexto base si existe
        if self.ctx:
            agent_ctx = self.ctx.clone()
        else:
            # Crear nuevo contexto
            from common.context import Context
            agent_ctx = Context()
            
        # Establecer valores específicos para este agente
        agent_ctx.set_tenant_id(self.tenant_id)
        agent_ctx.set_agent_id(agent_id)
        agent_ctx.set_value("orchestrator_session_id", self.session_id)
        
        return agent_ctx
```

### 6.1.2 Herramienta para Comunicación Entre Agentes

```python
from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any, List
from common.context import Context
from common.errors.handlers import handle_errors

class ConsultAgentTool(BaseTool):
    """
    Herramienta que permite a un agente consultar a otro agente especializado.
    """
    
    name = "consult_agent"
    description = "Consulta a un agente especializado para obtener ayuda con un tema específico."
    
    def __init__(
        self,
        tenant_id: str,
        agent_service,
        available_agents: Dict[str, str],
        ctx: Optional[Context] = None
    ):
        """
        Inicializa la herramienta.
        
        Args:
            tenant_id: ID del tenant
            agent_service: Servicio de agentes
            available_agents: Diccionario con {agent_id: descripción}
            ctx: Contexto con información adicional
        """
        super().__init__()
        self.tenant_id = tenant_id
        self.agent_service = agent_service
        self.available_agents = available_agents
        self.ctx = ctx
        
        # Actualizar descripción con agentes disponibles
        agents_desc = "\n".join([
            f"- {agent_id}: {desc}" for agent_id, desc in available_agents.items()
        ])
        self.description = f"""Consulta a un agente especializado para obtener ayuda.
        
Agentes disponibles:
{agents_desc}

Para usar esta herramienta, proporciona:
1. El ID del agente a consultar
2. La pregunta o instrucción para el agente
"""
    
    @handle_errors(error_type="tool", log_traceback=True)
    async def _arun(self, query: str) -> str:
        """
        Ejecuta la herramienta de forma asíncrona.
        
        Args:
            query: Consulta en formato "agent_id: pregunta"
            
        Returns:
            Respuesta del agente consultado
        """
        # Parsear la consulta
        try:
            agent_id, question = query.split(":", 1)
            agent_id = agent_id.strip()
            question = question.strip()
        except ValueError:
            return "Error: Formato incorrecto. Usa 'agent_id: pregunta'"
        
        # Verificar que el agente exista
        if agent_id not in self.available_agents:
            return f"Error: Agente '{agent_id}' no disponible. Agentes disponibles: {list(self.available_agents.keys())}"
        
        # Crear contexto para el agente
        from common.context import Context
        agent_ctx = Context()
        agent_ctx.set_tenant_id(self.tenant_id)
        agent_ctx.set_agent_id(agent_id)
        
        if self.ctx:
            # Propagar información relevante del contexto original
            if conversation_id := self.ctx.get_conversation_id():
                agent_ctx.set_conversation_id(conversation_id)
                
            # Añadir metadatos sobre la consulta
            agent_ctx.set_value("consulted_by_agent_id", self.ctx.get_agent_id())
            agent_ctx.set_value("is_consultation", True)
        
        # Ejecutar el agente consultado
        try:
            response = await self.agent_service.execute_agent(
                input_text=question,
                ctx=agent_ctx,
                collection_metadata={
                    "source": "agent_consultation",
                    "requesting_agent": self.ctx.get_agent_id() if self.ctx else None
                }
            )
            
            return f"Respuesta de {agent_id}:\n\n{response.answer}"
            
        except Exception as e:
            return f"Error al consultar al agente {agent_id}: {str(e)}"
```

## 6.2 Integración con LangChain Team

### 6.2.1 Implementación con LangChain Team

```python
from langchain.agents import initialize_agent, AgentType
from langchain.agents.agent_toolkits.conversational_retrieval.tool import CurrentDatetimeTool
from typing import List, Dict, Any, Optional
from common.context import Context
from common.errors.handlers import handle_errors

class TeamAgentExecutor:
    """
    Implementa un equipo de agentes usando LangChain Team.
    """
    
    def __init__(
        self,
        tenant_id: str,
        agent_service,
        supervisor_config: Dict[str, Any],
        agent_configs: Dict[str, Dict[str, Any]],
        ctx: Optional[Context] = None
    ):
        """
        Inicializa el executor de equipo.
        
        Args:
            tenant_id: ID del tenant
            agent_service: Servicio de agentes
            supervisor_config: Configuración del agente supervisor
            agent_configs: Configuraciones de los agentes del equipo
            ctx: Contexto con información adicional
        """
        self.tenant_id = tenant_id
        self.agent_service = agent_service
        self.supervisor_config = supervisor_config
        self.agent_configs = agent_configs
        self.ctx = ctx
        self.team = None
        
    @handle_errors(error_type="service", log_traceback=True)
    async def setup_team(self):
        """
        Configura el equipo de agentes.
        """
        # Crear LLMs para cada agente
        agent_llms = {}
        agent_tools = {}
        
        for agent_id, config in self.agent_configs.items():
            # Obtener modelo del agente
            llm_model = config.get("llm_model")
            
            # Crear LLM para este agente
            llm = await self.agent_service.create_llm(
                tenant_id=self.tenant_id,
                model=llm_model,
                ctx=self.ctx
            )
            
            agent_llms[agent_id] = llm
            
            # Crear herramientas específicas para este agente
            tools = await self.agent_service.create_tools(
                tenant_id=self.tenant_id,
                collection_id=config.get("default_collection_id"),
                embedding_model=config.get("embedding_model"),
                llm_model=llm_model,
                ctx=self.ctx
            )
            
            agent_tools[agent_id] = tools
        
        # Crear agente supervisor
        supervisor_llm = await self.agent_service.create_llm(
            tenant_id=self.tenant_id,
            model=self.supervisor_config.get("llm_model"),
            ctx=self.ctx
        )
        
        # Crear los agentes del equipo
        from langchain.agents import Agent
        team_agents = {}
        
        for agent_id, config in self.agent_configs.items():
            # Obtener sistema prompt para este agente
            system_prompt = config.get("system_prompt", "")
            
            # Crear agente
            agent = initialize_agent(
                tools=agent_tools[agent_id],
                llm=agent_llms[agent_id],
                agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
                verbose=True,
                max_iterations=config.get("max_iterations", 5),
                early_stopping_method="generate",
                handle_parsing_errors=True
            )
            
            # Configurar sistema prompt
            agent.agent.system_message = system_prompt
            
            team_agents[agent_id] = {
                "agent": agent,
                "description": config.get("description", ""),
                "name": config.get("name", agent_id)
            }
        
        # Crear equipo con LangChain
        from langchain.agents import AgentExecutor
        from langchain_experimental.agents.agent_toolkits import create_team_from_agents
        
        # Nombre y descripciones para cada agente
        agent_descriptions = {
            agent_id: {
                "name": config.get("name", agent_id),
                "description": config.get("description", "")
            }
            for agent_id, config in self.agent_configs.items()
        }
        
        # Crear team supervisor
        team = create_team_from_agents(
            team_agents,
            supervisor_llm=supervisor_llm,
            team_name=self.supervisor_config.get("team_name", "Equipo de agentes"),
            team_description=self.supervisor_config.get("team_description", ""),
            supervisor_prompt=self.supervisor_config.get("system_prompt", ""),
            verbose=True
        )
        
        self.team = team
        return True
    
    @handle_errors(error_type="service", log_traceback=True)
    async def execute(self, input_text: str) -> Dict[str, Any]:
        """
        Ejecuta el equipo de agentes.
        
        Args:
            input_text: Texto de entrada
            
        Returns:
            Resultado de la ejecución
        """
        if not self.team:
            await self.setup_team()
            
        # Ejecutar equipo
        result = await self.team.arun(input_text)
        
        # Procesar resultado
        return {
            "answer": result,
            "metadata": {
                "team_size": len(self.agent_configs),
                "supervisor": self.supervisor_config.get("name", "Supervisor")
            }
        }
```

## 6.3 Implementación de Agentes Especializados

### 6.3.1 Factory de Agentes Especializados

```python
from typing import Dict, Any, List, Optional
from common.context import Context
from common.errors.handlers import handle_errors

class SpecializedAgentFactory:
    """
    Factory para crear agentes especializados predefinidos.
    """
    
    def __init__(self, agent_service):
        """
        Inicializa el factory.
        
        Args:
            agent_service: Servicio de agentes
        """
        self.agent_service = agent_service
        self.specialized_templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Carga las plantillas predefinidas para agentes especializados.
        
        Returns:
            Diccionario con plantillas de agentes especializados
        """
        return {
            "researcher": {
                "name": "Agente Investigador",
                "description": "Especializado en búsqueda y análisis de información",
                "system_prompt": """Eres un agente investigador especializado en buscar y analizar información detallada. 
Tu objetivo es proporcionar respuestas exhaustivas y bien fundamentadas.
Utiliza las herramientas RAG disponibles para buscar información relevante.
Siempre cita tus fuentes y proporciona referencias para tus afirmaciones.""",
                "tools_config": {
                    "rag_query": {"enabled": True}
                },
                "llm_model": "groq/llama3-70b-8192"
            },
            "writer": {
                "name": "Agente Redactor",
                "description": "Especializado en redacción y generación de contenido",
                "system_prompt": """Eres un agente especializado en redacción y generación de contenido de alta calidad.
Tu objetivo es producir textos claros, concisos y adaptados al tono y estilo solicitados.
Puedes consultar información para asegurar precisión en tus redacciones.""",
                "tools_config": {
                    "rag_query": {"enabled": True}
                },
                "llm_model": "groq/llama3-70b-8192"
            },
            "analyzer": {
                "name": "Agente Analista",
                "description": "Especializado en análisis de datos e información",
                "system_prompt": """Eres un agente analista especializado en interpretación y análisis de datos e información.
Tu objetivo es extraer insights útiles, identificar patrones y proporcionar conclusiones basadas en evidencia.
Utiliza fuentes para verificar tus análisis y proporciona explicaciones detalladas.""",
                "tools_config": {
                    "rag_query": {"enabled": True}
                },
                "llm_model": "groq/llama3-70b-8192"
            }
        }
    
    @handle_errors(error_type="service", log_traceback=True)
    async def create_specialized_agent(
        self,
        tenant_id: str,
        agent_id: str,
        specialization: str,
        custom_config: Optional[Dict[str, Any]] = None,
        ctx: Optional[Context] = None
    ) -> bool:
        """
        Crea un agente especializado basado en plantillas predefinidas.
        
        Args:
            tenant_id: ID del tenant
            agent_id: ID para el nuevo agente
            specialization: Tipo de especialización
            custom_config: Configuraciones personalizadas (opcionales)
            ctx: Contexto con información adicional
            
        Returns:
            True si se creó correctamente
            
        Raises:
            ValueError: Si la especialización no existe
        """
        # Verificar que la especialización exista
        if specialization not in self.specialized_templates:
            available = list(self.specialized_templates.keys())
            raise ValueError(f"Especialización '{specialization}' no disponible. Disponibles: {available}")
        
        # Obtener plantilla base
        template = self.specialized_templates[specialization].copy()
        
        # Aplicar configuraciones personalizadas
        if custom_config:
            # Actualizar campos simples
            for key in ["name", "description", "llm_model"]:
                if key in custom_config:
                    template[key] = custom_config[key]
            
            # Actualizar sistema prompt (añadir al existente)
            if "additional_prompt" in custom_config:
                template["system_prompt"] += f"\n\n{custom_config['additional_prompt']}"
            
            # Actualizar configuración de herramientas
            if "tools_config" in custom_config:
                template["tools_config"].update(custom_config["tools_config"])
        
        # Registrar agente en el sistema
        await self.agent_service.register_agent_from_frontend(
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_config=template,
            ctx=ctx
        )
        
        return True
```

## 6.4 Endpoint para Ejecuciones Multi-Agente

```python
@router.post("/multi-agent/execute", response_model=None)
@with_context(tenant=True, conversation=True)
@handle_errors(error_type="api", log_traceback=True)
async def execute_multi_agent(
    request: MultiAgentExecutionRequest,
    ctx: Context = None
):
    """
    Endpoint para ejecutar un flujo multi-agente.
    
    Args:
        request: Configuración de la ejecución multi-agente
        ctx: Contexto con información adicional
    """
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para execute_multi_agent")
    
    tenant_id = ctx.get_tenant_id()
    
    # Crear orquestador
    orchestrator = AgentOrchestrator(tenant_id, ctx)
    await orchestrator.setup(agent_service)
    
    # Determinar tipo de ejecución
    if request.execution_type == "sequential":
        result = await orchestrator.execute_sequential(
            agent_ids=request.agent_ids,
            initial_input=request.input,
            metadata=request.metadata
        )
    elif request.execution_type == "parallel":
        result = await orchestrator.execute_parallel(
            agent_ids=request.agent_ids,
            input_text=request.input,
            metadata=request.metadata
        )
    elif request.execution_type == "workflow":
        # Registrar workflow
        await orchestrator.register_workflow(request.workflow_config)
        
        # Ejecutar workflow
        result = await orchestrator.execute_workflow(
            workflow_id=request.workflow_id,
            initial_input=request.input,
            metadata=request.metadata
        )
    else:
        raise ValueError(f"Tipo de ejecución '{request.execution_type}' no válido")
    
    return {
        "success": True,
        "message": "Multi-agent execution completed",
        "data": result
    }
```

## Tareas Pendientes

- [ ] Implementar AgentOrchestrator para coordinar agentes
- [ ] Desarrollar ConsultAgentTool para comunicación entre agentes
- [ ] Integrar con LangChain Team para ejecuciones complejas
- [ ] Crear SpecializedAgentFactory con plantillas predefinidas
- [ ] Implementar endpoints para ejecuciones multi-agente
- [ ] Desarrollar sistema de workflows para secuencias complejas
