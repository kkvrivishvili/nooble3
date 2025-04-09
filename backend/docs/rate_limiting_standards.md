# Estándares de Rate Limiting en Nooble3

Este documento define los estándares para la implementación y uso del rate limiting en todos los servicios de la plataforma Nooble3.

## Principios Generales

1. **Consistencia**: Todos los servicios deben aplicar rate limiting de manera uniforme
2. **Transparencia**: Las respuestas deben incluir headers que informen sobre el estado del rate limiting
3. **Configurabilidad**: Los límites deben ser configurables por tenant y tier
4. **Graceful degradation**: Proporcionar respuestas útiles cuando se excedan los límites

## Uso del Rate Limiting Middleware

Todos los servicios deben utilizar el middleware de rate limiting:

```python
from common.utils.rate_limiting import setup_rate_limiting
from fastapi import FastAPI

app = FastAPI()

# Configurar middleware de rate limiting
setup_rate_limiting(app)
```

## Rate Limiting Explícito en Endpoints Críticos

Para endpoints que requieren protección adicional:

```python
from common.utils.rate_limiting import apply_rate_limit
from common.auth import verify_tenant
from common.models import TenantInfo
from fastapi import APIRouter, Depends

router = APIRouter()

@router.post("/endpoint-intensivo")
async def endpoint_intensivo(
    request: SomeRequest,
    tenant_info: TenantInfo = Depends(verify_tenant)
):
    # Aplicar rate limiting específico para este endpoint
    await apply_rate_limit(
        tenant_id=tenant_info.tenant_id,
        tier=tenant_info.tier,
        limit_key="endpoint_intensivo"  # Clave específica para este endpoint
    )
    
    # Continuar con la lógica normal
    # ...
```

## Headers de Rate Limiting

Todos los servicios deben incluir estos headers en sus respuestas:

- `X-RateLimit-Limit`: Límite total de solicitudes
- `X-RateLimit-Remaining`: Solicitudes restantes en el periodo actual
- `X-RateLimit-Reset`: Tiempo en segundos hasta el reseteo del contador

El middleware `RateLimitMiddleware` se encarga de añadir estos headers automáticamente.

## Configuración de Límites

Los límites deben definirse en tres niveles:

1. **Nivel global**: En `common.config.settings`
2. **Nivel de servicio**: Específicos para cada servicio
3. **Nivel de tenant**: Personalizados por tenant en Supabase

Ejemplo de definición de límites:

```python
# En settings.py
class Settings(BaseSettings):
    # Límites globales por tier
    rate_limit_free_tier: int = Field(600, description="Solicitudes permitidas por minuto - free")
    rate_limit_pro_tier: int = Field(1200, description="Solicitudes permitidas por minuto - pro")
    rate_limit_business_tier: int = Field(3000, description="Solicitudes permitidas por minuto - business")
```

## Manejo de Excedentes de Límite

Cuando se excede un límite de tasa, se debe:

1. Retornar un código HTTP 429 (Too Many Requests)
2. Incluir un mensaje claro sobre por qué se rechazó la solicitud
3. Informar cuándo se reseteará el contador

La función `apply_rate_limit` ya implementa este comportamiento, lanzando una excepción `HTTPException` con el código 429 cuando se excede el límite.

## Personalización por Tenant

Para establecer límites personalizados por tenant:

```python
# En un endpoint de administración
async def update_tenant_rate_limit(
    tenant_id: str,
    service: str,
    new_limit: int
):
    # Guardar en Supabase
    await update_tenant_configuration(
        tenant_id=tenant_id,
        scope="rate_limit",
        scope_id=service,
        value={"max_requests": new_limit}
    )
```

## Rate Limiting en Trabajos en Segundo Plano

Para tareas asíncronas o trabajos en segundo plano:

```python
async def background_job(tenant_id: str):
    # Verificar límite de forma programática
    is_within_limit = await check_rate_limit_async(f"{tenant_id}:background")
    
    if not is_within_limit:
        logger.warning(f"Rate limit excedido para background job del tenant {tenant_id}")
        # Manejar la situación (ej: postponer tarea)
        return False
    
    # Continuar con la ejecución normal
    # ...
```

## Configuración por Entorno

Los límites pueden ajustarse según el entorno:

```python
# En settings.py
@validator("rate_limit_free_tier", "rate_limit_pro_tier", "rate_limit_business_tier")
def adjust_limits_for_environment(cls, v, values):
    # En desarrollo, usar límites más permisivos
    if values.get("environment") == "development":
        return v * 2  # Duplicar límites en desarrollo
    return v
```

## Buenas Prácticas Adicionales

1. **Considerar el costo**: Aplicar límites más estrictos a operaciones costosas
2. **Monitorización**: Registrar cuándo los tenants se acercan a sus límites
3. **Notificaciones**: Avisar a los usuarios cuando estén cerca de sus límites
4. **Degradación gradual**: Reducir funcionalidad en lugar de rechazar completamente

## Implementación en Servicios Existentes

Para implementar rate limiting en servicios existentes:

1. Añadir `setup_rate_limiting(app)` en la inicialización
2. Identificar endpoints críticos y aplicar `apply_rate_limit`
3. Verificar que los headers se añadan correctamente
4. Probar diferentes escenarios de límites excedidos
