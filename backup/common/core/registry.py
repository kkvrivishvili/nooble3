"""
Registro central para servicios y componentes de la aplicación.

Este módulo implementa un patrón mediador/registro que permite a los diferentes
componentes de la aplicación registrarse y acceder a otros componentes sin
crear dependencias directas entre ellos.
"""

import logging
from typing import Dict, Any, Callable, Optional, TypeVar, Generic, Type, List

from .constants import (
    COMPONENT_PRIORITY_CORE,
    COMPONENT_PRIORITY_CONFIG,
    COMPONENT_PRIORITY_DB,
    COMPONENT_PRIORITY_CACHE,
    COMPONENT_PRIORITY_AUTH,
    COMPONENT_PRIORITY_ERROR,
    COMPONENT_PRIORITY_SERVICE,
    COMPONENT_PRIORITY_API
)

T = TypeVar('T')
logger = logging.getLogger(__name__)

class Registry:
    """Registro central para servicios y componentes."""
    
    _instance = None
    _components = {}
    _factories = {}
    _lazy_components = {}
    _initialized_components = set()
    _component_priorities = {}
    
    @classmethod
    def get_instance(cls):
        """Obtener instancia singleton del registro."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, name: str, component: Any, priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
        """
        Registrar un componente en el registro.
        
        Args:
            name: Identificador único del componente
            component: Instancia del componente a registrar
            priority: Prioridad para inicialización ordenada (menor = más prioritario)
        """
        self._components[name] = component
        self._component_priorities[name] = priority
        self._initialized_components.add(name)
        logger.debug(f"Componente registrado: {name} (prioridad: {priority})")
    
    def register_factory(self, name: str, factory: Callable[[], Any], priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
        """
        Registrar una fábrica para crear componentes bajo demanda.
        
        Args:
            name: Identificador único del componente
            factory: Función factory que creará el componente cuando sea necesario
            priority: Prioridad para inicialización ordenada (menor = más prioritario)
        """
        self._factories[name] = factory
        self._component_priorities[name] = priority
        logger.debug(f"Factory registrada: {name} (prioridad: {priority})")
    
    def register_lazy(self, name: str, module_path: str, class_or_func_name: str, priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
        """
        Registrar un componente para carga perezosa.
        
        Args:
            name: Identificador único del componente
            module_path: Ruta de importación al módulo
            class_or_func_name: Nombre de la clase o función a importar
            priority: Prioridad para inicialización ordenada (menor = más prioritario)
        """
        self._lazy_components[name] = (module_path, class_or_func_name)
        self._component_priorities[name] = priority
        logger.debug(f"Componente lazy registrado: {name} (prioridad: {priority})")
    
    def get(self, name: str, default=None) -> Any:
        """
        Obtener un componente del registro.
        
        Si el componente no está cargado pero hay una fábrica o carga perezosa
        configurada para él, se cargará automáticamente.
        
        Args:
            name: Identificador único del componente
            default: Valor por defecto si no se encuentra
            
        Returns:
            El componente solicitado o el valor por defecto
        """
        # Si ya está cargado, devolverlo
        if name in self._components:
            return self._components[name]
        
        # Si hay una fábrica, crear el componente
        if name in self._factories:
            try:
                component = self._factories[name]()
                self._components[name] = component
                self._initialized_components.add(name)
                logger.debug(f"Componente creado a través de factory: {name}")
                return component
            except Exception as e:
                logger.error(f"Error creando componente {name} a través de factory: {e}")
                return default
        
        # Si hay configuración para carga perezosa, importar y crear
        if name in self._lazy_components:
            module_path, class_or_func_name = self._lazy_components[name]
            try:
                import importlib
                module = importlib.import_module(module_path)
                component = getattr(module, class_or_func_name)
                
                # Si es una clase, instanciarla
                if isinstance(component, type):
                    component = component()
                
                self._components[name] = component
                self._initialized_components.add(name)
                logger.debug(f"Componente cargado de forma lazy: {name}")
                return component
            except (ImportError, AttributeError) as e:
                logger.error(f"Error cargando componente {name}: {e}")
                return default
        
        logger.warning(f"Componente no encontrado: {name}")
        return default
    
    def get_all(self) -> Dict[str, Any]:
        """
        Obtener todos los componentes registrados.
        
        Returns:
            Diccionario con todos los componentes
        """
        return self._components.copy()
    
    def get_sorted_component_names(self) -> List[str]:
        """
        Obtener nombres de componentes ordenados por prioridad.
        
        Returns:
            Lista de nombres de componentes ordenados por prioridad (menor a mayor)
        """
        # Combinar todos los nombres de componentes (registrados, factories y lazy)
        all_names = set(self._components.keys()) | set(self._factories.keys()) | set(self._lazy_components.keys())
        
        # Ordenar por prioridad (los valores más bajos son más prioritarios)
        return sorted(all_names, key=lambda name: self._component_priorities.get(name, COMPONENT_PRIORITY_SERVICE))
    
    def is_initialized(self, name: str) -> bool:
        """
        Verificar si un componente está inicializado.
        
        Args:
            name: Nombre del componente
            
        Returns:
            True si el componente está inicializado, False en caso contrario
        """
        return name in self._initialized_components
    
    def clear(self) -> None:
        """Limpiar todos los componentes registrados."""
        self._components.clear()
        self._factories.clear()
        self._lazy_components.clear()
        self._initialized_components.clear()
        self._component_priorities.clear()
        logger.debug("Registro limpiado completamente")


# Instancia global del registro
registry = Registry.get_instance()

# Funciones de conveniencia para acceder al registro
def register(name: str, component: Any, priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
    """Registrar un componente en el registro global."""
    registry.register(name, component, priority)

def register_factory(name: str, factory: Callable[[], Any], priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
    """Registrar una fábrica en el registro global."""
    registry.register_factory(name, factory, priority)

def register_lazy(name: str, module_path: str, class_or_func_name: str, priority: int = COMPONENT_PRIORITY_SERVICE) -> None:
    """Registrar un componente para carga perezosa en el registro global."""
    registry.register_lazy(name, module_path, class_or_func_name, priority)

def get(name: str, default=None) -> Any:
    """Obtener un componente del registro global."""
    return registry.get(name, default)

def get_all() -> Dict[str, Any]:
    """Obtener todos los componentes del registro global."""
    return registry.get_all()

def get_sorted_component_names() -> List[str]:
    """Obtener nombres de componentes ordenados por prioridad."""
    return registry.get_sorted_component_names()

def is_initialized(name: str) -> bool:
    """Verificar si un componente está inicializado."""
    return registry.is_initialized(name)

def clear() -> None:
    """Limpiar el registro global."""
    registry.clear()
