"""
Decoradores y clases para gestionar el contexto en diferentes ámbitos de ejecución.

Proporciona decoradores para funciones asíncronas y administradores de contexto
para bloques de código que necesitan mantener información de contexto.
"""

import logging
import contextvars
import functools
from typing import TypeVar, Callable, Awaitable, Optional, List, Tuple, Any
from .vars import (
    current_tenant_id, current_agent_id, current_conversation_id, current_collection_id,
    set_current_tenant_id, set_current_agent_id, set_current_conversation_id, set_current_collection_id,
    reset_context, get_full_context
)
from ..errors.exceptions import ServiceError, ErrorCode

logger = logging.getLogger(__name__)

# Tipo para funciones asíncronas
T = TypeVar('T')
AsyncFunc = Callable[..., Awaitable[T]]

class ContextTokens:
    """Contenedor para tokens de contexto que facilita su gestión."""
    tenant_token: Optional[contextvars.Token] = None
    agent_token: Optional[contextvars.Token] = None
    conversation_token: Optional[contextvars.Token] = None
    collection_token: Optional[contextvars.Token] = None

class Context:
    """
    Administrador de contexto unificado para establecer cualquier combinación de
    valores de contexto durante la ejecución de un bloque de código.
    
    Ejemplo:
        ```python
        with Context(tenant_id="t123", agent_id="a456", conversation_id="c789"):
            # Código que ejecutará con estos valores de contexto
            result = await function_that_needs_context()
        ```
    
    Opciones avanzadas:
        ```python
        # Para validar tenant (garantizar que no sea "default" o None)
        with Context(tenant_id="t123", validate_tenant=True):
            # Lanzará error si tenant_id es inválido
            ...
        
        # Para usar el tenant actual pero validándolo
        with Context(validate_tenant=True):
            # Lanzará error si el tenant actual es inválido
            ...
        ```
    """
    
    def __init__(
        self, 
        tenant_id: Optional[str] = None, 
        agent_id: Optional[str] = None, 
        conversation_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        validate_tenant: bool = False
    ):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.collection_id = collection_id
        self.validate_tenant = validate_tenant
        self.tokens = ContextTokens()
        self.tokens_with_names: List[Tuple[contextvars.Token, str]] = {}
        self._metrics = {}
    
    def __enter__(self):
        # Si se solicita validación de tenant pero no se proporciona uno específico,
        # validar el tenant del contexto actual
        if self.validate_tenant and self.tenant_id is None:
            self._validate_current_tenant()
        
        # Guardar tokens para restaurar después
        tokens = []
        
        if self.tenant_id is not None:
            # Validar el tenant si es necesario
            if self.validate_tenant:
                self._validate_tenant(self.tenant_id)
            tokens.append((set_current_tenant_id(self.tenant_id), "tenant_id"))
        
        if self.agent_id is not None:
            tokens.append((set_current_agent_id(self.agent_id), "agent_id"))
        
        if self.conversation_id is not None:
            tokens.append((set_current_conversation_id(self.conversation_id), "conversation_id"))
        
        if self.collection_id is not None:
            tokens.append((set_current_collection_id(self.collection_id), "collection_id"))
        
        # Guardar todos los tokens para restaurar en el exit
        self.tokens_with_names = tokens
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restaurar contexto previo (en orden inverso para mejor encadenamiento)
        for token, name in reversed(self.tokens_with_names):
            reset_context(token, name)

    async def __aenter__(self):
        """
        Entra en el contexto asincrónico y establece los valores especificados.
        """
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Sale del contexto asincrónico y restaura los valores anteriores.
        """
        self.__exit__(exc_type, exc_val, exc_tb)
    
    def _validate_tenant(self, tenant_id: str) -> None:
        """Valida que el tenant_id sea válido (no None, no "default")"""
        from .validator import validate_tenant_id
        validate_tenant_id(tenant_id)
    
    def _validate_current_tenant(self) -> None:
        """Valida el tenant_id del contexto actual"""
        from .validator import validate_current_tenant
        validate_current_tenant()
    
    def get_tenant_id(self) -> str:
        """
        Obtiene el tenant_id del contexto actual y lo valida.
        
        Returns:
            str: ID del tenant validado (nunca será "default" ni None)
            
        Raises:
            ServiceError: Si no hay un tenant_id válido en el contexto
        """
        tenant_id = current_tenant_id.get()
        self._validate_tenant(tenant_id)
        return tenant_id
    
    def get_agent_id(self) -> Optional[str]:
        """Obtiene el agent_id del contexto actual"""
        return current_agent_id.get()
    
    def get_conversation_id(self) -> Optional[str]:
        """Obtiene el conversation_id del contexto actual"""
        return current_conversation_id.get()
    
    def get_collection_id(self) -> Optional[str]:
        """Obtiene el collection_id del contexto actual"""
        return current_collection_id.get()

    def add_metric(self, name: str, value: Any):
        """Registra métricas en el contexto"""
        self._metrics[name] = value

# === DECORADORES PARA FUNCIONES ASÍNCRONAS ===

def with_context(
    tenant: bool = True,
    agent: bool = False,
    conversation: bool = False,
    collection: bool = False,
    validate_tenant: bool = True
) -> Callable[[AsyncFunc], AsyncFunc]:
    """
    Decorador unificado para gestionar el contexto multitenancy en la aplicación.
    
    Este decorador es la forma principal recomendada para gestionar el contexto.
    Propaga valores del contexto actual, permite validación de tenant, y provee
    una estructura consistente para todos los endpoints y servicios.
    
    IMPORTANTE: Para endpoints FastAPI, use este decorador ANTES de los decoradores de FastAPI:
    
    ```python
    # CORRECTO:
    @with_context(tenant=True)
    @router.post("/endpoint", response_model=MyResponse)
    async def my_endpoint(request: MyRequest, tenant_info: TenantInfo = Depends(verify_tenant)):
        # Usar ctx aquí
        ...
        
    # INCORRECTO (causará error en FastAPI):
    @router.post("/endpoint", response_model=MyResponse)
    @with_context(tenant=True)
    async def my_endpoint(request: MyRequest, tenant_info: TenantInfo = Depends(verify_tenant)):
        # Esto fallará
        ...
    ```
    
    En caso de conflictos con FastAPI, use get_context() con Depends() en su lugar.
    
    Args:
        tenant: Si debe propagar tenant_id
        agent: Si debe propagar agent_id
        conversation: Si debe propagar conversation_id
        collection: Si debe propagar collection_id
        validate_tenant: Si debe validar que el tenant sea válido (no None, no "default")
        
    Returns:
        Decorador configurado
    """
    def decorator(func: AsyncFunc) -> AsyncFunc:
        # Guarda la información original de la función para que FastAPI pueda inspeccionarla
        if not hasattr(func, "__fastapi_compatible__"):
            setattr(func, "__fastapi_compatible__", True)
            
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extrae parámetros de contexto a propagar
            context_params = {
                # Standardizar validación de tenant: siempre validar cuando tenant=True
                "validate_tenant": tenant
            }
            
            if tenant:
                context_params["tenant_id"] = current_tenant_id.get()
            if agent:
                context_params["agent_id"] = current_agent_id.get()
            if conversation:
                context_params["conversation_id"] = current_conversation_id.get()
            if collection:
                context_params["collection_id"] = current_collection_id.get()
            
            # Añade ctx al primer argumento si es una función de clase (método)
            is_method = args and hasattr(args[0], '__class__')
            
            # Ejecuta la función con el contexto
            ctx = Context(**context_params)
            async with ctx:
                # Verifica si 'ctx' ya está presente en los argumentos de la función
                # o si está definido como None (situación común en FastAPI)
                if 'ctx' in kwargs and kwargs['ctx'] is None:
                    # Reemplaza el valor None con la instancia de Context
                    kwargs['ctx'] = ctx
                elif 'ctx' not in kwargs:
                    # Solo agrega ctx si no existe en kwargs
                    kwargs['ctx'] = ctx
                
                # Ejecuta la función original con el contexto
                return await func(*args, **kwargs)
        return wrapper
    return decorator

# === INTEGRACIÓN CON FASTAPI ===

def get_context(
    tenant: bool = True,
    agent: bool = False,
    conversation: bool = False,
    collection: bool = False,
    validate_tenant: bool = True
) -> Callable[..., Context]:
    """
    Proveedor de dependencias para FastAPI que crea un objeto Context.
    
    Esta función está diseñada para ser usada con Depends() de FastAPI,
    proporcionando una integración nativa con el sistema de inyección
    de dependencias de FastAPI.
    
    Ejemplo:
        ```python
        @app.get("/endpoint")
        async def my_endpoint(ctx: Context = Depends(get_context(tenant=True))):
            # Usar ctx aquí
            ...
        ```
    
    Args:
        tenant: Si debe propagar tenant_id
        agent: Si debe propagar agent_id
        conversation: Si debe propagar conversation_id
        collection: Si debe propagar collection_id
        validate_tenant: Si debe validar que el tenant sea válido
        
    Returns:
        Callable que produce un objeto Context
    """
    def dependency() -> Context:
        # Extrae parámetros de contexto a propagar
        context_params = {
            "validate_tenant": validate_tenant
        }
        
        if tenant:
            context_params["tenant_id"] = current_tenant_id.get()
        if agent:
            context_params["agent_id"] = current_agent_id.get()
        if conversation:
            context_params["conversation_id"] = current_conversation_id.get()
        if collection:
            context_params["collection_id"] = current_collection_id.get()
        
        # Crea y devuelve el contexto
        return Context(**context_params)
    
    return dependency