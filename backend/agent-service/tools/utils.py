"""
Utilidades para trabajar con herramientas LangChain.
"""

import logging
from typing import Dict, Any, List, Optional, Union

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain_core.tools import BaseTool

from common.errors import handle_errors, ServiceError
from common.context import Context

from config import get_settings

logger = logging.getLogger(__name__)


@handle_errors(error_type="service", log_traceback=True)
def get_langchain_chat_model(
    model_name: str, 
    temperature: float = 0.7,
    max_tokens: Optional[int] = None
) -> BaseChatModel:
    """
    Obtiene una instancia del modelo de chat LangChain basado en el nombre.
    
    Args:
        model_name: Nombre del modelo (gpt-3.5-turbo, gpt-4, etc.)
        temperature: Temperatura para las respuestas
        max_tokens: Límite de tokens para las respuestas
        
    Returns:
        BaseChatModel: Modelo de chat de LangChain
    """
    settings = get_settings()
    
    # Determinar el proveedor según el nombre del modelo
    if model_name.startswith("gpt-"):
        # OpenAI
        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,
            openai_api_key=settings.openai_api_key
        )
    elif model_name.startswith("llama") or model_name.startswith("mixtral"):
        # Groq
        return ChatGroq(
            model_name=model_name, 
            temperature=temperature,
            max_tokens=max_tokens,
            groq_api_key=settings.groq_api_key
        )
    elif model_name.startswith("ollama:"):
        # Ollama local
        model_name = model_name.replace("ollama:", "")
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            num_ctx=max_tokens or 4096,
            base_url=settings.ollama_base_url
        )
    else:
        # Por defecto, usar OpenAI
        logger.warning(f"Modelo desconocido {model_name}, usando gpt-3.5-turbo por defecto")
        return ChatOpenAI(
            model_name="gpt-3.5-turbo",
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,
            openai_api_key=settings.openai_api_key
        )


def convert_to_langchain_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """
    Convierte una lista de mensajes en formato dict a mensajes de LangChain.
    
    Args:
        messages: Lista de mensajes en formato dict
        
    Returns:
        List[BaseMessage]: Lista de mensajes de LangChain
    """
    lc_messages = []
    
    for msg in messages:
        role = msg.get("role", "").lower()
        content = msg.get("content", "")
        
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        elif role in ["function", "tool"]:
            name = msg.get("name", "unknown_tool")
            lc_messages.append(FunctionMessage(content=content, name=name))
            
    return lc_messages


@handle_errors(error_type="service", log_traceback=True)
def create_langchain_agent(
    llm: BaseChatModel,
    tools: List[BaseTool],
    system_prompt: str
) -> AgentExecutor:
    """
    Crea un agente LangChain configurado para usar herramientas.
    
    Args:
        llm: Modelo de lenguaje a utilizar
        tools: Lista de herramientas disponibles
        system_prompt: Prompt de sistema para el agente
        
    Returns:
        AgentExecutor: Agente ejecutor de LangChain
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    agent = create_openai_tools_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
        early_stopping_method="force"
    )
    
    return agent_executor


@handle_errors(error_type="service", log_traceback=True)
async def run_agent_with_tools(
    agent_executor: AgentExecutor,
    user_input: str,
    chat_history: List[BaseMessage] = None,
    tenant_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """
    Ejecuta un agente con herramientas disponibles.
    
    Args:
        agent_executor: Agente ejecutor de LangChain
        user_input: Mensaje del usuario
        chat_history: Historial de chat en formato LangChain
        tenant_id: ID del tenant
        agent_id: ID del agente
        conversation_id: ID de la conversación
        ctx: Contexto de la operación
        
    Returns:
        Dict[str, Any]: Resultado de la ejecución del agente
    """
    # Preparar la configuración de ejecución con metadatos para contexto
    runnable_config = RunnableConfig(
        metadata={
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
        },
        callbacks=None  # Aquí se pueden agregar callbacks personalizados
    )
    
    # Inicializar el historial si es None
    if chat_history is None:
        chat_history = []
    
    # Ejecutar el agente
    result = await agent_executor.ainvoke(
        {
            "input": user_input,
            "chat_history": chat_history
        },
        config=runnable_config
    )
    
    # Formatear la respuesta
    response = {
        "output": result["output"],
        "intermediate_steps": result.get("intermediate_steps", []),
        "tool_calls": []
    }
    
    # Formatear las llamadas a herramientas para el tracking
    for step in result.get("intermediate_steps", []):
        if len(step) >= 2:
            tool_action = step[0]
            tool_output = step[1]
            
            response["tool_calls"].append({
                "tool": tool_action.tool,
                "tool_input": tool_action.tool_input,
                "output": tool_output
            })
    
    return response
