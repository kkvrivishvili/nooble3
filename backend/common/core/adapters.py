"""
Adaptadores para desacoplar servicios y componentes.

Este módulo implementa interfaces/adaptadores para los principales servicios,
permitiendo que los consumidores dependan de abstracciones en lugar de implementaciones concretas,
siguiendo el Principio de Inversión de Dependencias.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic, Union, Tuple, Type

# Tipos genéricos para los adaptadores
T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


# =========== Adaptadores de Configuración ===========

class ConfigAdapter(ABC):
    """Interfaz para operaciones de configuración."""
    
    @abstractmethod
    def get_value(self, key: str, default=None) -> Any:
        """Obtener valor de configuración."""
        pass
    
    @abstractmethod
    def get_section(self, section: str) -> Dict[str, Any]:
        """Obtener una sección completa de configuración."""
        pass
    
    @property
    @abstractmethod
    def all(self) -> Dict[str, Any]:
        """Obtener toda la configuración."""
        pass
    
    @abstractmethod
    def get_settings(self, tenant_id: Optional[str] = None) -> Any:
        """
        Obtener objeto de configuración para un tenant específico.
        
        Args:
            tenant_id: ID del tenant (opcional)
            
        Returns:
            Objeto de configuración
        """
        pass
    
    @abstractmethod
    def invalidate_cache(self, tenant_id: Optional[str] = None) -> None:
        """
        Invalidar caché de configuración.
        
        Args:
            tenant_id: ID del tenant (opcional)
        """
        pass


# =========== Adaptadores de Caché ===========

class CacheAdapter(ABC):
    """Interfaz para operaciones de caché."""
    
    @abstractmethod
    async def get(self, key: str, default=None) -> Any:
        """Obtener valor de la caché."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Almacenar valor en la caché."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Eliminar valor de la caché."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Verificar si la clave existe en la caché."""
        pass
    
    @abstractmethod
    async def get_with_cache_aside(
        self, 
        data_type: str,
        resource_id: str,
        tenant_id: Optional[str] = None,
        fetch_from_db_func: Optional[Callable] = None,
        generate_func: Optional[Callable] = None,
        **kwargs
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Implementar el patrón Cache-Aside completo.
        
        Args:
            data_type: Tipo de datos para determinar TTL adecuado
            resource_id: ID del recurso para formar la clave
            tenant_id: ID del tenant (opcional)
            fetch_from_db_func: Función para recuperar de base de datos si no está en caché
            generate_func: Función para generar si no está en DB
            **kwargs: Parámetros adicionales para funciones y clave de caché
            
        Returns:
            Tupla con (resultado, métricas)
        """
        pass


# =========== Adaptadores de Errores ===========

class ErrorAdapter(ABC):
    """Interfaz para operaciones de manejo de errores."""
    
    @abstractmethod
    def create_error(self, 
                    message: str, 
                    error_code: str, 
                    status_code: Optional[int] = None,
                    details: Optional[Dict[str, Any]] = None,
                    context: Optional[Dict[str, Any]] = None) -> Exception:
        """
        Crear un error con los detalles proporcionados.
        
        Args:
            message: Mensaje descriptivo del error
            error_code: Código de error estandarizado
            status_code: Código HTTP si aplica
            details: Detalles adicionales del error
            context: Información contextual
            
        Returns:
            Excepción preparada
        """
        pass
    
    @abstractmethod
    def handle_error(self, error: Exception) -> Dict[str, Any]:
        """
        Manejar un error y convertirlo a formato estándar.
        
        Args:
            error: Excepción a manejar
            
        Returns:
            Diccionario con información del error
        """
        pass
    
    @abstractmethod
    def setup_error_handlers(self, app: Any) -> None:
        """
        Configurar manejadores de error para una aplicación.
        
        Args:
            app: Aplicación (FastAPI) a configurar
        """
        pass
    
    @abstractmethod
    def error_handler_decorator(self, 
                               error_type: str = "service",
                               error_map: Optional[Dict[Type[Exception], Tuple[str, int]]] = None,
                               **kwargs) -> Callable:
        """
        Crear un decorador para manejar errores en funciones.
        
        Args:
            error_type: Tipo de error a manejar ('service', 'config', etc.)
            error_map: Mapeo de tipos de excepción a códigos de error
            **kwargs: Parámetros adicionales para el manejador
            
        Returns:
            Decorador configurado
        """
        pass


# =========== Adaptadores de Base de Datos ===========

class DatabaseAdapter(ABC):
    """Interfaz para operaciones de base de datos."""
    
    @abstractmethod
    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Ejecutar consulta SQL."""
        pass
    
    @abstractmethod
    async def get_by_id(self, table: str, id_value: str, id_field: str = "id") -> Optional[Dict[str, Any]]:
        """Obtener registro por ID."""
        pass
    
    @abstractmethod
    async def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insertar nuevo registro."""
        pass
    
    @abstractmethod
    async def update(self, table: str, id_value: str, data: Dict[str, Any], id_field: str = "id") -> Dict[str, Any]:
        """Actualizar registro existente."""
        pass
    
    @abstractmethod
    async def delete(self, table: str, id_value: str, id_field: str = "id") -> bool:
        """Eliminar registro."""
        pass
    
    @abstractmethod
    def get_client(self) -> Any:
        """
        Obtener cliente de base de datos.
        
        Returns:
            Cliente de base de datos (puede ser Supabase, SQLAlchemy, etc.)
        """
        pass
    
    @abstractmethod
    def get_table_name(self, table_base: str) -> str:
        """
        Obtener nombre completo de tabla.
        
        Args:
            table_base: Nombre base de la tabla
            
        Returns:
            Nombre completo de la tabla (puede incluir prefijos, etc.)
        """
        pass


# =========== Adaptadores para Métricas y Telemetría ===========

class MetricsAdapter(ABC):
    """Interfaz para operaciones de métricas y telemetría."""
    
    @abstractmethod
    def increment_counter(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Incrementar un contador."""
        pass
    
    @abstractmethod
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Registrar un valor de gauge."""
        pass
    
    @abstractmethod
    def timing(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Registrar un tiempo de ejecución."""
        pass
    
    @abstractmethod
    def start_span(self, name: str, tags: Optional[Dict[str, str]] = None) -> Any:
        """Iniciar un span de tracing."""
        pass
    
    @abstractmethod
    def track_token_usage(self, 
                         token_count: int, 
                         model_name: str, 
                         operation_type: str,
                         tenant_id: Optional[str] = None,
                         **kwargs) -> None:
        """
        Registrar uso de tokens.
        
        Args:
            token_count: Número de tokens utilizados
            model_name: Nombre del modelo usado
            operation_type: Tipo de operación (p.ej. 'embedding', 'completion')
            tenant_id: ID del tenant (opcional)
            **kwargs: Datos adicionales para el registro
        """
        pass


# =========== Adaptadores de Contexto ===========

class ContextAdapter(ABC):
    """Interfaz para operaciones de contexto."""
    
    @abstractmethod
    def get_context(self) -> Dict[str, Any]:
        """
        Obtener contexto actual.
        
        Returns:
            Diccionario con información de contexto
        """
        pass
    
    @abstractmethod
    def set_context(self, **kwargs) -> None:
        """
        Establecer valores en el contexto actual.
        
        Args:
            **kwargs: Valores a establecer en el contexto
        """
        pass
    
    @abstractmethod
    def clear_context(self) -> None:
        """Limpiar contexto actual."""
        pass
    
    @abstractmethod
    def with_context(self, **kwargs) -> Callable:
        """
        Crear un decorador para establecer contexto en funciones.
        
        Args:
            **kwargs: Valores a establecer en el contexto
            
        Returns:
            Decorador configurado
        """
        pass
    
    @abstractmethod
    def validate_tenant(self, tenant_id: Optional[str]) -> str:
        """
        Validar tenant ID.
        
        Args:
            tenant_id: ID del tenant a validar
            
        Returns:
            ID del tenant validado
            
        Raises:
            Exception: Si el tenant ID no es válido
        """
        pass
