"""
Utilidades para trabajar con código asíncrono.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar('T')


async def run_sync_as_async(sync_func: Callable[..., T], *args, **kwargs) -> T:
    """
    Ejecuta una función síncrona en un contexto asíncrono.
    
    Útil para funciones síncronas que bloquean como operaciones de E/S
    (especialmente operaciones de bases de datos que no tienen API asíncrona).
    
    Args:
        sync_func: La función síncrona a ejecutar
        *args: Argumentos posicionales para la función
        **kwargs: Argumentos nominados para la función
        
    Returns:
        El resultado de la función síncrona
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        return await loop.run_in_executor(
            executor,
            lambda: sync_func(*args, **kwargs)
        )


def sync_to_async(func: Callable[..., T]) -> Callable[..., Coroutine[None, None, T]]:
    """
    Decorador para convertir una función síncrona en asíncrona.
    
    Args:
        func: La función síncrona a convertir
        
    Returns:
        Una versión asíncrona de la función
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await run_sync_as_async(func, *args, **kwargs)
    return wrapper
