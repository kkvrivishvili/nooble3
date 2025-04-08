"""
Manejo de permisos y acceso autenticado a recursos.
"""

from typing import Dict, Any, Optional, List, TypeVar, Callable, Awaitable, Union
from fastapi import Request, HTTPException, Depends
import logging
from functools import wraps
from supabase import Client
import jwt
import base64
import json

from ..db.supabase import get_supabase_client, get_supabase_client_with_token, get_table_name
from ..context import get_current_tenant_id, Context

logger = logging.getLogger(__name__)

# Tipo para funciones asíncronas para decoradores
T = TypeVar('T')
AsyncFunc = Callable[..., Awaitable[T]]

async def get_auth_info(request: Request) -> Dict[str, Any]:
    """
    Obtiene información de autenticación desde los headers o parámetros de la request.
    
    Args:
        request: Objeto FastAPI Request
        
    Returns:
        Dict[str, Any]: Diccionario con información de autenticación
    """
    auth_info = {}
    
    # Extraer contexto (tenant_id, agent_id, etc.) de los headers
    from ..context.propagation import extract_context_from_headers
    context_info = extract_context_from_headers(dict(request.headers.items()))
    auth_info.update(context_info)
    
    # Si no hay tenant_id en headers, intentar obtenerlo de query params
    if "tenant_id" not in auth_info:
        tenant_id = request.query_params.get("tenant_id")
        if tenant_id:
            auth_info["tenant_id"] = tenant_id
    
    # Obtener API Key de los headers si existe
    api_key = request.headers.get("x-api-key")
    if api_key:
        auth_info["api_key"] = api_key
    
    # Obtener token de autenticación
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        auth_info["token"] = token
        
        # Intentar extraer información básica del token
        try:
            # No verificamos la firma aquí, solo extraemos la información
            # La verificación completa ocurre cuando se usa el token con Supabase
            
            # Decodificar el payload sin verificar firma
            parts = token.split(".")
            if len(parts) >= 2:
                # Decodificar el payload (segunda parte del token)
                padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload_json = base64.b64decode(padded)
                payload = json.loads(payload_json)
                
                # Extraer información útil
                if "sub" in payload:
                    auth_info["user_id"] = payload["sub"]
                if "email" in payload:
                    auth_info["email"] = payload["email"]
                if "role" in payload:
                    auth_info["role"] = payload["role"]
                    
                # Agregar payload completo por si es necesario
                auth_info["token_payload"] = payload
                
                logger.debug(f"Extraída información de token JWT: user_id={auth_info.get('user_id')}")
        except Exception as e:
            # Si falla la extracción, sólo lo registramos pero seguimos usando el token
            logger.warning(f"Error extrayendo información del token JWT: {str(e)}")
    
    return auth_info


async def get_auth_supabase_client(request: Request) -> Client:
    """
    Dependencia que obtiene un cliente Supabase autenticado con el token JWT del usuario si está disponible.
    Si no hay token, usa el cliente normal con la clave de servicio.
    
    Args:
        request: Objeto FastAPI Request
        
    Returns:
        Client: Cliente Supabase autenticado
    """
    auth_info = await get_auth_info(request)
    token = auth_info.get("token")
    
    # Crear un cliente con el token si está disponible
    return get_supabase_client_with_token(token=token)


def with_auth_client(endpoint_func: AsyncFunc) -> AsyncFunc:
    """
    Decorador que añade un cliente Supabase autenticado a los argumentos de un endpoint.
    
    Ejemplo de uso:
    ```python
    @app.get("/api/resources")
    @with_auth_client
    async def get_resources(supabase_client: Client, other_params: str):
        # Usar supabase_client...
    ```
    
    Args:
        endpoint_func: Función del endpoint a decorar
        
    Returns:
        Función decorada con cliente Supabase autenticado
    """
    @wraps(endpoint_func)
    async def wrapper(*args, **kwargs):
        # Obtener request del contexto o de los kwargs
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break
        
        if not request and "request" in kwargs:
            request = kwargs["request"]
        
        if not request:
            # Si no se encuentra request, lanzar excepción
            raise ValueError("No se encontró objeto Request en los argumentos del endpoint")
        
        # Obtener cliente autenticado
        auth_info = await get_auth_info(request)
        token = auth_info.get("token")
        client = get_supabase_client_with_token(token=token)
        
        # Añadir cliente a los kwargs
        kwargs["supabase_client"] = client
        
        # Establecer contexto a partir de auth_info
        tenant_id = auth_info.get("tenant_id")
        agent_id = auth_info.get("agent_id")
        conversation_id = auth_info.get("conversation_id")
        collection_id = auth_info.get("collection_id")
        
        # Ejecutar la función dentro del contexto apropiado
        ctx = Context(tenant_id, agent_id, conversation_id, collection_id)
        async with ctx:
            return await endpoint_func(*args, **kwargs)
    
    return wrapper


class AISchemaAccess:
    """
    Clase auxiliar que proporciona acceso autenticado a las tablas del esquema "ai" usando el token JWT.
    Las tablas del esquema "public" seguirán usando el cliente estándar.
    
    Esto garantiza que las operaciones en tablas del esquema "ai" contabilicen correctamente
    los tokens para el tenant propietario del agente.
    
    Permite especificar un owner_tenant_id para contabilizar recursos al propietario
    de un agente en caso de conversaciones públicas.
    
    Ejemplo de uso básico:
    ```python
    async def mi_funcion(request: Request):
        # Obtener acceso autenticado a tablas
        db = AISchemaAccess(request)
        
        # Operaciones en tablas "ai" usan el cliente autenticado
        result_ai = await db.table("agent_configs").select("*").execute()
        
        # Operaciones en tablas "public" usan el cliente estándar
        result_public = await db.table("tenants").select("*").execute()
    ```
    
    Ejemplo con propietario específico (para conversaciones públicas):
    ```python
    async def mi_funcion(request: Request, agent_id: str):
        # Obtener el propietario del agente
        agent_data = await supabase.table(get_table_name("agent_configs")).select("tenant_id").eq("agent_id", agent_id).execute()
        owner_tenant_id = agent_data.data[0]["tenant_id"]
        
        # Usar el propietario para contabilizar recursos
        db = AISchemaAccess(request, owner_tenant_id=owner_tenant_id)
        
        # Todas las operaciones ahora contabilizarán al propietario del agente
        result = await db.table("conversations").select("*").execute()
    ```
    """
    def __init__(self, request: Request, owner_tenant_id: Optional[str] = None):
        """
        Inicializa el acceso a tablas Supabase con soporte para autenticación JWT.
        
        Args:
            request: El objeto Request de FastAPI que contiene el token JWT
            owner_tenant_id: Optional. ID del tenant propietario al que contabilizar recursos.
                             Esto es útil para conversaciones públicas donde queremos contabilizar
                             al propietario del agente, no al usuario que interactúa.
        """
        self.request = request
        self.owner_tenant_id = owner_tenant_id
        self._auth_client = None
        self._standard_client = None
        self._auth_info = None
        self._owner_auth_client = None
    
    async def _get_auth_info(self):
        """
        Obtiene la información de autenticación del request si aún no se ha obtenido.
        """
        if self._auth_info is None:
            self._auth_info = await get_auth_info(self.request)
        return self._auth_info
    
    async def _get_auth_client(self):
        """
        Obtiene el cliente Supabase autenticado con el token JWT si está disponible.
        """
        if self._auth_client is None:
            auth_info = await self._get_auth_info()
            token = auth_info.get("token")
            self._auth_client = get_supabase_client_with_token(token=token)
        return self._auth_client
        
    async def _get_owner_auth_client(self):
        """
        Obtiene un cliente Supabase especial que usará el propietario para contabilización.
        Este cliente se usará cuando se proporcione owner_tenant_id en la inicialización.
        """
        if self.owner_tenant_id and self._owner_auth_client is None:
            # Usamos el service_role para operaciones con el owner_tenant_id
            # ya que no tenemos un token JWT del propietario
            self._owner_auth_client = get_supabase_client(use_service_role=True)
        return self._owner_auth_client if self.owner_tenant_id else None
    
    async def _get_standard_client(self):
        """
        Obtiene el cliente Supabase estándar sin token JWT.
        """
        if self._standard_client is None:
            self._standard_client = get_supabase_client()
        return self._standard_client
    
    async def table(self, table_base_name: str):
        """
        Accede a una tabla usando el cliente apropiado según la tabla y el contexto de contabilización.
        
        Args:
            table_base_name: Nombre base de la tabla sin prefijo
            
        Returns:
            Referencia a la tabla con el cliente apropiado
        """
        # Tablas que deben estar en el esquema public
        public_tables = ["tenants", "users", "auth", "public_sessions"]
        
        # Tablas que deben estar en el esquema ai
        ai_tables = [
            "tenant_configurations", "tenant_subscriptions", "tenant_stats",
            "agent_configs", "conversations", "chat_history", "chat_feedback",
            "collections", "document_chunks", "agent_collections", 
            "embedding_metrics", "query_logs", "user_preferences"
        ]
        
        # Tablas que deben contabilizarse al propietario del agente
        owner_tables = [
            "conversations", "chat_history", "chat_feedback", "query_logs", 
            "embedding_metrics", "tenant_stats"
        ]
        
        full_table_name = get_table_name(table_base_name)
        
        # 1. Si hay un owner_tenant_id y la tabla debe contabilizarse al propietario
        if self.owner_tenant_id and (table_base_name in owner_tables):
            # Usar cliente especial para contabilizar al propietario
            client = await self._get_owner_auth_client() or await self._get_standard_client()
            logger.debug(f"Usando contabilización al propietario {self.owner_tenant_id} para tabla {full_table_name}")
            return client.table(full_table_name)
        
        # 2. Usar cliente estándar para tablas "public"
        if table_base_name in public_tables or table_base_name.startswith("public."):
            client = await self._get_standard_client()
            return client.table(full_table_name)
        
        # 3. Usar cliente autenticado para tablas "ai"
        if table_base_name in ai_tables or table_base_name.startswith("ai.") or not table_base_name.startswith("public."):
            client = await self._get_auth_client()
            return client.table(full_table_name)
        
        # 4. Por defecto, usar cliente autenticado
        client = await self._get_auth_client()
        return client.table(full_table_name)
    
    async def from_(self, table_base_name: str):
        """
        Alias para table(), mantiene compatibilidad con la API de Supabase.
        """
        return await self.table(table_base_name)
    
    async def rpc(self, function_name: str, params: Dict[str, Any] = None):
        """
        Ejecuta una función RPC usando el cliente apropiado.
        Por defecto usa el cliente autenticado, pero si hay owner_tenant_id y la función
        está relacionada con operaciones de contabilización, usará el cliente del propietario.
        
        Args:
            function_name: Nombre de la función RPC a ejecutar
            params: Parámetros para la función RPC
            
        Returns:
            Resultado de la operación RPC
        """
        # Funciones que deben contabilizarse al propietario del agente
        owner_functions = [
            "create_conversation", "add_chat_message", "add_chat_history",
            "increment_token_usage", "process_query", "generate_embedding",
            "create_public_conversation", "add_public_chat_message"
        ]
        
        # Si hay owner_tenant_id y la función debe contabilizarse al propietario
        if self.owner_tenant_id and (function_name in owner_functions):
            client = await self._get_owner_auth_client() or await self._get_standard_client()
            # Modificar los parámetros para incluir el tenant propietario si es necesario
            params_copy = dict(params or {})
            if "p_tenant_id" in params_copy and not "p_owner_tenant_id" in params_copy:
                params_copy["p_owner_tenant_id"] = self.owner_tenant_id
            logger.debug(f"Usando contabilización al propietario {self.owner_tenant_id} para RPC {function_name}")
            return client.rpc(function_name, params_copy)
        else:
            # Para otras funciones, usar el cliente autenticado
            client = await self._get_auth_client()
            return client.rpc(function_name, params or {})