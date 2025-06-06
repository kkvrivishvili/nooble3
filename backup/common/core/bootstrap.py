"""
Sistema de inicialización ordenada de componentes.

Este módulo implementa un patrón bootstrap para garantizar que los
componentes de la aplicación se inicialicen en el orden correcto,
resolviendo dependencias de forma automática.
"""

import logging
import importlib
import inspect
import time
import asyncio
import traceback
from typing import Dict, List, Any, Optional, Callable, Set, Tuple, Type

from .registry import register, get, get_sorted_component_names
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

logger = logging.getLogger(__name__)

class DependencyNode:
    """Nodo para el grafo de dependencias."""
    
    def __init__(self, name: str):
        self.name = name
        self.dependencies = set()
        self.initialized = False
        self.failed = False
        self.error = None
    
    def add_dependency(self, dep_name: str):
        """Añadir una dependencia al nodo."""
        self.dependencies.add(dep_name)
    
    def mark_initialized(self):
        """Marcar el nodo como inicializado."""
        self.initialized = True
    
    def mark_failed(self, error):
        """Marcar el nodo como fallido."""
        self.failed = True
        self.error = error
    
    def __repr__(self):
        status = "✓" if self.initialized else ("✗" if self.failed else "?")
        return f"DependencyNode({self.name}, deps={list(self.dependencies)}, status={status})"


class DependencyGraph:
    """Grafo para representar dependencias entre componentes."""
    
    def __init__(self):
        self.nodes = {}  # name -> DependencyNode
    
    def add_node(self, name: str) -> DependencyNode:
        """Añadir un nodo al grafo."""
        if name not in self.nodes:
            self.nodes[name] = DependencyNode(name)
        return self.nodes[name]
    
    def add_dependency(self, node_name: str, dep_name: str):
        """Añadir una dependencia entre nodos."""
        node = self.add_node(node_name)
        self.add_node(dep_name)  # Asegurar que el nodo de dependencia existe
        node.add_dependency(dep_name)
    
    def get_initialization_order(self) -> List[str]:
        """
        Calcular el orden de inicialización de los nodos.
        
        Returns:
            Lista de nombres de componentes en el orden correcto
        """
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(node_name):
            if node_name in temp_visited:
                cycle = self._find_cycle(node_name)
                raise ValueError(f"Ciclo de dependencias detectado: {' -> '.join(cycle)}")
            
            if node_name in visited:
                return
            
            temp_visited.add(node_name)
            
            # Visitar primero las dependencias
            node = self.nodes[node_name]
            for dep_name in node.dependencies:
                visit(dep_name)
            
            temp_visited.remove(node_name)
            visited.add(node_name)
            result.append(node_name)
        
        # Visitar todos los nodos
        for node_name in self.nodes:
            if node_name not in visited:
                visit(node_name)
        
        return result
    
    def _find_cycle(self, start_node: str) -> List[str]:
        """
        Encontrar un ciclo que comienza con el nodo dado.
        
        Args:
            start_node: Nombre del nodo inicial
            
        Returns:
            Lista de nombres de nodos que forman el ciclo
        """
        path = []
        visited = set()
        
        def dfs(node_name, path_so_far):
            if node_name in path_so_far:
                # Encontramos un ciclo, extraer los nodos relevantes
                start_idx = path_so_far.index(node_name)
                return path_so_far[start_idx:]
            
            if node_name in visited:
                return None
            
            visited.add(node_name)
            new_path = path_so_far + [node_name]
            
            # Buscar en las dependencias
            node = self.nodes[node_name]
            for dep_name in node.dependencies:
                cycle = dfs(dep_name, new_path)
                if cycle:
                    return cycle
            
            return None
        
        return dfs(start_node, []) or []


class ComponentInitializer:
    """Inicializador de componentes con resolución de dependencias."""
    
    def __init__(self):
        self.components = {}  # name -> initializer
        self.dependencies = {}  # name -> [dep1, dep2, ...]
        self.initialized_components = set()
        self.initialization_hooks = []
        self.async_initialization_hooks = []
        self.shutdown_hooks = []
        
    def register_component(self, name: str, initializer: Callable, dependencies: List[str] = None, priority: int = COMPONENT_PRIORITY_SERVICE):
        """
        Registrar un componente y sus dependencias.
        
        Args:
            name: Nombre único del componente
            initializer: Función que inicializa el componente
            dependencies: Lista de nombres de componentes de los que depende
            priority: Prioridad de inicialización (menor = mayor prioridad)
        """
        self.components[name] = initializer
        self.dependencies[name] = dependencies or []
        
        # Registrar al componente en el registry global
        from .registry import register_factory
        register_factory(name, initializer, priority)
        
        logger.debug(f"Componente registrado: {name} (deps: {dependencies}, priority: {priority})")
    
    def register_initialization_hook(self, hook: Callable):
        """
        Registrar una función que se ejecutará después de inicializar todos los componentes.
        
        Args:
            hook: Función a ejecutar
        """
        self.initialization_hooks.append(hook)
    
    def register_async_initialization_hook(self, hook: Callable):
        """
        Registrar una función asíncrona que se ejecutará después de inicializar todos los componentes.
        
        Args:
            hook: Función asíncrona a ejecutar
        """
        self.async_initialization_hooks.append(hook)
    
    def register_shutdown_hook(self, hook: Callable):
        """
        Registrar una función que se ejecutará durante el apagado del sistema.
        
        Args:
            hook: Función a ejecutar
        """
        self.shutdown_hooks.append(hook)
    
    def initialize_all(self, fail_fast: bool = False) -> Dict[str, Any]:
        """
        Inicializar todos los componentes registrados en el orden correcto.
        
        Args:
            fail_fast: Si es True, aborta la inicialización ante el primer error
            
        Returns:
            Diccionario con los componentes inicializados
        """
        result = {}
        start_time = time.time()
        
        # Construir grafo de dependencias
        graph = DependencyGraph()
        for name, deps in self.dependencies.items():
            for dep in deps:
                graph.add_dependency(name, dep)
        
        try:
            # Determinar el orden de inicialización
            init_order = graph.get_initialization_order()
            logger.info(f"Orden de inicialización: {init_order}")
        except ValueError as e:
            logger.error(f"Error determinando orden de inicialización: {e}")
            raise
        
        # Inicializar componentes en orden
        for name in init_order:
            if name not in self.components:
                logger.warning(f"Componente {name} no tiene inicializador registrado")
                continue
            
            # Verificar que todas las dependencias estén inicializadas
            deps_ok = True
            for dep in self.dependencies.get(name, []):
                if dep not in self.initialized_components:
                    logger.error(f"La dependencia {dep} de {name} no está inicializada")
                    deps_ok = False
            
            if not deps_ok:
                if fail_fast:
                    raise ValueError(f"No se pueden satisfacer las dependencias para {name}")
                continue
            
            try:
                logger.info(f"Inicializando componente: {name}")
                component_start = time.time()
                initializer = self.components[name]
                component = initializer()
                component_time = time.time() - component_start
                result[name] = component
                self.initialized_components.add(name)
                logger.info(f"Componente inicializado: {name} ({component_time:.2f}s)")
            except Exception as e:
                logger.error(f"Error inicializando {name}: {e}")
                graph.nodes[name].mark_failed(e)
                if fail_fast:
                    raise
        
        # Ejecutar hooks de inicialización
        for hook in self.initialization_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"Error en hook de inicialización: {e}")
                if fail_fast:
                    raise
        
        total_time = time.time() - start_time
        logger.info(f"Inicialización completa ({total_time:.2f}s)")
        return result
    
    async def initialize_all_async(self, fail_fast: bool = False) -> Dict[str, Any]:
        """
        Inicializar todos los componentes registrados de forma asíncrona.
        
        Args:
            fail_fast: Si es True, aborta la inicialización ante el primer error
            
        Returns:
            Diccionario con los componentes inicializados
        """
        result = self.initialize_all(fail_fast)
        
        # Ejecutar hooks de inicialización asíncrona
        for hook in self.async_initialization_hooks:
            try:
                await hook()
            except Exception as e:
                logger.error(f"Error en hook de inicialización asíncrona: {e}")
                if fail_fast:
                    raise
        
        return result
    
    def shutdown(self):
        """Ejecutar hooks de apagado."""
        logger.info("Iniciando apagado ordenado de componentes")
        
        # Ejecutar hooks de apagado en orden inverso
        for hook in reversed(self.shutdown_hooks):
            try:
                hook()
            except Exception as e:
                logger.error(f"Error en hook de apagado: {e}")
        
        logger.info("Apagado completo")


# Singleton global
_initializer = ComponentInitializer()

# Funciones de conveniencia
def register_component(name: str, initializer: Callable, dependencies: List[str] = None, priority: int = COMPONENT_PRIORITY_SERVICE):
    """Registrar un componente en el inicializador global."""
    _initializer.register_component(name, initializer, dependencies, priority)

def register_initialization_hook(hook: Callable):
    """Registrar un hook de inicialización en el inicializador global."""
    _initializer.register_initialization_hook(hook)

def register_async_initialization_hook(hook: Callable):
    """Registrar un hook de inicialización asíncrona en el inicializador global."""
    _initializer.register_async_initialization_hook(hook)

def register_shutdown_hook(hook: Callable):
    """Registrar un hook de apagado en el inicializador global."""
    _initializer.register_shutdown_hook(hook)

def initialize_all(fail_fast: bool = False) -> Dict[str, Any]:
    """Inicializar todos los componentes registrados."""
    return _initializer.initialize_all(fail_fast)

async def initialize_all_async(fail_fast: bool = False) -> Dict[str, Any]:
    """Inicializar todos los componentes registrados de forma asíncrona."""
    return await _initializer.initialize_all_async(fail_fast)

def shutdown():
    """Ejecutar hooks de apagado."""
    _initializer.shutdown()

# Decorador para componentes
def component(name=None, dependencies=None, priority=COMPONENT_PRIORITY_SERVICE):
    """
    Decorador para marcar una función como un componente de la aplicación.
    
    Args:
        name: Nombre del componente (opcional, por defecto usa el nombre de la función)
        dependencies: Lista de nombres de componentes de los que depende
        priority: Prioridad de inicialización (menor = mayor prioridad)
    """
    def decorator(func):
        component_name = name or func.__name__
        register_component(component_name, func, dependencies, priority)
        return func
    
    # Permitir usar @component o @component()
    if callable(name):
        func = name
        name = None
        return decorator(func)
    
    return decorator

def initialize_from_modules(module_paths: List[str], fail_fast: bool = False) -> Dict[str, Any]:
    """
    Inicializar componentes desde módulos específicos.
    
    Busca funciones con el decorador @component en los módulos 
    especificados y las registra automáticamente.
    
    Args:
        module_paths: Lista de rutas a módulos
        fail_fast: Si es True, aborta la inicialización ante el primer error
        
    Returns:
        Diccionario con los componentes inicializados
    """
    # Registrar componentes desde módulos
    registered = []
    
    for module_path in module_paths:
        try:
            module = importlib.import_module(module_path)
            
            # Buscar funciones con decorador @component o función init_module
            for name, obj in inspect.getmembers(module):
                if hasattr(obj, "_is_component") and obj._is_component:
                    # El decorador @component ya ha registrado este componente
                    registered.append(name)
                elif name == "init_module" and callable(obj):
                    # Función convencional de inicialización de módulo
                    module_name = module_path.split(".")[-1]
                    component_name = f"{module_name}_module"
                    register_component(component_name, obj, priority=COMPONENT_PRIORITY_SERVICE)
                    registered.append(component_name)
                    
        except ImportError as e:
            logger.error(f"Error importando módulo {module_path}: {e}")
            if fail_fast:
                raise
    
    logger.info(f"Componentes registrados desde módulos: {', '.join(registered)}")
    return initialize_all(fail_fast)

async def initialize_from_modules_async(module_paths: List[str], fail_fast: bool = False) -> Dict[str, Any]:
    """
    Inicializar componentes desde módulos específicos de forma asíncrona.
    
    Args:
        module_paths: Lista de rutas a módulos
        fail_fast: Si es True, aborta la inicialización ante el primer error
        
    Returns:
        Diccionario con los componentes inicializados
    """
    # Registrar componentes
    initialize_from_modules(module_paths, fail_fast=False)
    
    # Inicializar de forma asíncrona
    return await initialize_all_async(fail_fast)
