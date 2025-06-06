# Common Helpers

Este directorio contiene utilidades compartidas para todos los servicios backend, centralizando patrones de código comunes.

## Organización

- **health.py** - Funciones estandarizadas para endpoints de salud y estado:
  - `basic_health_check()` - Verificación rápida para health/liveness probes
  - `detailed_status_check()` - Estado detallado con uptime y métricas
  - `get_service_health()` - Genera respuesta HealthResponse basada en componentes

- **swagger.py** - Configuración de Swagger/OpenAPI:
  - `configure_swagger_ui()` - Configura documentación estándar
  - `add_example_to_endpoint()` - Añade ejemplos a endpoints específicos
  - `generate_docstring_template()` - Genera docstrings consistentes

## Implementación de endpoints /health y /status

### ¿Cuál es la diferencia?

- **/health** - Endpoint ligero para verificación de liveness:
  - Responde en milisegundos
  - Comprueba componentes críticos (cache, DB)
  - Ideal para Kubernetes readiness/liveness probes
  - Devuelve `HealthResponse`

- **/status** - Endpoint detallado para observabilidad:
  - Incluye uptime, métricas y dependencias
  - Comprueba componentes específicos del servicio
  - Ideal para dashboards y debugging
  - Devuelve `ServiceStatusResponse`

### Ejemplo de implementación

```python
# En el archivo main.py o routes/health.py de cada servicio:
import time
from fastapi import APIRouter
from common.helpers.health import basic_health_check, detailed_status_check, get_service_health
from common.models import HealthResponse, ServiceStatusResponse
from common.errors import handle_errors
from common.context import with_context, Context

router = APIRouter()

# Variable global para registrar el inicio del servicio
service_start_time = time.time()

@router.get("/health", response_model=None)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def health_check(ctx: Context = None) -> HealthResponse:
    """Verifica el estado básico del servicio (liveness check)."""
    # Obtener componentes básicos
    components = await basic_health_check()
    
    # Generar respuesta estandarizada
    return get_service_health(
        components=components,
        service_version=settings.service_version
    )

@router.get("/status", response_model=None)
@with_context(tenant=False)
@handle_errors(error_type="simple", log_traceback=False)
async def service_status(ctx: Context = None) -> ServiceStatusResponse:
    """Obtiene estado detallado del servicio con métricas y dependencias."""
    # Definir verificaciones específicas del servicio (opcional)
    async def check_my_service():
        # Lógica específica de verificación
        return "available"  # o "degraded", "unavailable"
    
    # Usar el helper común con verificaciones específicas
    return await detailed_status_check(
        service_name="my-service",
        service_version=settings.service_version,
        start_time=service_start_time,
        extra_checks={
            "my_component": check_my_service
            # Añadir más verificaciones específicas aquí
        }
    )
```

## Buenas Prácticas

1. **Mantén la consistencia**: Usa estos helpers en todos los servicios.
2. **Separa preocupaciones**:
   - El código específico del servicio pertenece al servicio
   - El código común pertenece a estos helpers
3. **Extiende, no modifiques**: Si necesitas funcionalidad adicional, crea funciones nuevas en tu servicio que usen estos helpers.
4. **Respeta la jerarquía**:
   - Los endpoints básicos son `/health` y `/status`
   - Para endpoint adicionales, usa subrutas como `/status/scheduler`

## Helpers futuros

Considera añadir más helpers comunes para:
- Métricas de rendimiento
- Logging estandarizado
- Procesamiento de errores
- Otros patrones comunes entre servicios
