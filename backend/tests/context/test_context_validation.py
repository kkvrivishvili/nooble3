"""
Pruebas para el sistema de contexto multi-tenant.

Estas pruebas validan el comportamiento del decorador with_context
y la clase Context después de las mejoras de la Fase 1.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

from common.context import Context, with_context
from common.context.vars import (
    current_tenant_id, current_collection_id,
    get_current_tenant_id, get_current_collection_id
)
from common.errors import TenantRequired, TenantMismatchError

# ============================================================
# Pruebas para validación del decorador with_context
# ============================================================

@pytest.mark.asyncio
async def test_context_validation_tenant_required():
    """Verifica que se requiera tenant_id cuando tenant=True y validate_tenant=True."""
    
    # Configuración: tenant=True, validate_tenant=True, tenant_id=None
    @with_context(tenant=True, validate_tenant=True)
    async def test_func():
        return get_current_tenant_id()
    
    # Debe lanzar excepción TenantRequired porque no proporcionamos tenant_id
    with pytest.raises(TenantRequired):
        await test_func()


@pytest.mark.asyncio
async def test_context_validation_tenant_not_required():
    """Verifica que se permita tenant_id=None cuando validate_tenant=False."""
    
    # Configuración: tenant=True, validate_tenant=False, tenant_id=None
    @with_context(tenant=True, validate_tenant=False)
    async def test_func():
        return get_current_tenant_id()
    
    # No debe lanzar excepción, debe retornar None
    assert await test_func() is None


@pytest.mark.asyncio
async def test_context_validation_default_tenant():
    """Verifica que el tenant 'default' sea válido cuando validate_tenant=False."""
    
    # Establecemos tenant_id='default' en el contexto
    default_tenant = "00000000-0000-0000-0000-000000000000"
    
    @with_context(tenant=True, validate_tenant=False)
    async def test_func():
        return get_current_tenant_id()
    
    # Ejecutar con tenant='default' en contexto
    with Context(tenant_id=default_tenant):
        result = await test_func()
        assert result == default_tenant


@pytest.mark.asyncio
async def test_context_propagation():
    """Verifica que los valores de contexto se propaguen correctamente entre funciones."""
    
    test_tenant_id = "11111111-1111-1111-1111-111111111111"
    test_collection_id = "22222222-2222-2222-2222-222222222222"
    
    @with_context(tenant=True, collection=True)
    async def inner_function(ctx=None):
        # Verificar que los valores se propagaron correctamente
        assert ctx.get_tenant_id() == test_tenant_id
        assert ctx.get_collection_id() == test_collection_id
        return True
    
    @with_context(tenant=True, collection=True)
    async def outer_function(ctx=None):
        # Usar explícitamente valores del contexto
        assert ctx.get_tenant_id() == test_tenant_id
        assert ctx.get_collection_id() == test_collection_id
        # Llamar a función interna que debería heredar el contexto
        return await inner_function()
    
    # Ejecutar con valores de contexto establecidos
    with Context(tenant_id=test_tenant_id, collection_id=test_collection_id):
        result = await outer_function()
        assert result is True


@pytest.mark.asyncio
async def test_context_explicit_usage():
    """Verifica que el acceso explícito a ctx.get_X() funcione correctamente."""
    
    test_tenant_id = "33333333-3333-3333-3333-333333333333"
    
    @with_context(tenant=True)
    async def function_with_explicit_context_usage(ctx=None):
        # Acceso explícito usando ctx
        tenant_id = ctx.get_tenant_id()
        assert tenant_id == test_tenant_id
        # Evitar acceso directo a variables contextuales
        return tenant_id
    
    # Ejecutar con tenant_id establecido
    with Context(tenant_id=test_tenant_id):
        result = await function_with_explicit_context_usage()
        assert result == test_tenant_id


# ============================================================
# Pruebas de integración simulando un endpoint
# ============================================================

@pytest.mark.asyncio
async def test_endpoint_with_context():
    """Simula un endpoint FastAPI con el patrón @with_context correcto."""
    
    test_tenant_id = "44444444-4444-4444-4444-444444444444"
    test_collection_id = "55555555-5555-5555-5555-555555555555"
    
    # Mock para TenantInfo que normalmente vendría de verify_tenant
    mock_tenant_info = MagicMock()
    mock_tenant_info.tenant_id = test_tenant_id
    
    @with_context(tenant=True, collection=True)
    async def mock_endpoint(collection_id, mock_tenant_info, ctx=None):
        # Validar que el contexto se estableció correctamente
        assert ctx.get_tenant_id() == test_tenant_id
        assert ctx.get_collection_id() == test_collection_id
        # Simular lógica del endpoint
        return {
            "tenant_id": ctx.get_tenant_id(),
            "collection_id": ctx.get_collection_id(),
            "success": True
        }
    
    # Ejecutar simulando un request a un endpoint
    result = await mock_endpoint(
        collection_id=test_collection_id,
        mock_tenant_info=mock_tenant_info
    )
    
    # Verificar respuesta
    assert result["tenant_id"] == test_tenant_id
    assert result["collection_id"] == test_collection_id
    assert result["success"] is True


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
