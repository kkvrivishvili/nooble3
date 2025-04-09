# Guía Técnica: Rate Limiting Estandarizado

## Introducción

Este documento técnico explica cómo se ha implementado el sistema estandarizado de rate limiting en los servicios backend, siguiendo los principios de:

1. Manejo consistente de errores
2. Gestión adecuada de contexto
3. Centralización de configuración
4. Logging estructurado

## Implementación Técnica

### 1. Módulos Principales

El sistema se compone de tres módulos principales:

- **`common/utils/rate_limiting.py`**: Implementación del middleware y funciones centrales
- **`common/config/tiers.py`**: Configuración de límites por tier y servicio
- **`common/errors/exceptions.py`**: Excepciones específicas para rate limiting

### 2. Estándares Aplicados

#### 2.1 Manejo de Errores

Seguimos el estándar de excepciones tipadas con:

```python
# Excepción específica para rate limiting
RateLimitExceeded(
    message="Has excedido el límite de solicitudes por minuto",
    error_code=ErrorCode.RATE_LIMIT_EXCEEDED.value,
    status_code=429,
    context={...}  # Contexto enriquecido
)
```

#### 2.2 Gestión de Contexto

El módulo utiliza el sistema de contexto para obtener información relevante:

```python
# Obtención de contexto
from common.context.vars import get_full_context

error_context = {...}
error_context.update(get_full_context())  # Añade tenant_id, conversation_id, etc.
```

El middleware también obtiene automáticamente el tenant_id del contexto o los headers.

#### 2.3 Centralización de Configuración

La función `get_tier_rate_limit` sigue el patrón de centralización:

```python
@handle_errors()
async def get_tier_rate_limit(tenant_id: str, tier: str, service_name: Optional[str] = None) -> int:
    # Obtener configuración personalizada del tenant
    tenant_rate_limit_config = await get_tenant_configurations(
        tenant_id=tenant_id,
        scope="rate_limit",
        scope_id=service_name or "default"
    )
    
    # Usar configuración personalizada o valores predeterminados
    # ...
```

#### 2.4 Logging Consistente

Todo el módulo utiliza logging estructurado:

```python
logger.debug(f"Límite de tasa para tenant {tenant_id}, tier {tier}: {base_limit} req/min",
            extra=error_context)
```

### 3. Componentes Principales

#### 3.1 Middleware de FastAPI

El middleware intercepta cada solicitud HTTP y aplica los límites:

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    # ...
    async def dispatch(self, request: Request, call_next):
        # Obtener tenant_id y tier
        # Aplicar rate limiting
        # Agregar headers a la respuesta
```

#### 3.2 Funciones Principales

| Función | Propósito |
|---------|-----------|
| `get_tier_rate_limit` | Obtener límite para un tenant/tier/servicio |
| `apply_rate_limit` | Verificar y aplicar el límite |
| `_add_rate_limit_headers` | Agregar headers estándar a respuestas |

### 4. Integración con Redis

El módulo usa `CacheManager` para mantener contadores distribuidos:

```python
# Incrementar contador de solicitudes
await CacheManager.increment(
    tenant_id=tenant_id,
    data_type="rate_limit",
    resource_id=f"{limit_key}:count"
)
```

## Guía de Implementación

### 1. Activación del Middleware

En cada servicio, activar el middleware en `main.py`:

```python
from common.utils.rate_limiting import setup_rate_limiting

app = FastAPI()
setup_rate_limiting(app)
```

### 2. Verificación Manual en Operaciones Críticas

```python
@router.post("/important-endpoint")
@with_context()  # Obtiene automáticamente el contexto
async def important_operation(data: ImportantData):
    tenant_id = get_current_tenant_id()
    tier = get_tenant_tier(tenant_id)
    
    # Verificación adicional para operaciones críticas
    await apply_rate_limit(tenant_id, tier, "important_operation")
    
    # Continuar con la operación...
```

### 3. Personalización por Servicio

Para personalizar los límites en un servicio específico:

```python
# En settings.json o Supabase:
{
  "rate_limit": {
    "agent": {
      "max_requests": 1000
    }
  }
}
```

## Buenas Prácticas

1. **No duplicar límites**: Usar siempre `get_tier_rate_limit` para obtener límites
2. **Enriquecer el contexto**: Añadir información relevante al contexto de error
3. **Usar el decorador `@handle_errors()`**: Para manejo consistente de errores
4. **Logging estructurado**: Usar siempre `extra=error_context`
5. **Headers estándar**: Incluir los headers de rate limit en todas las respuestas

## Troubleshooting

### Problema: Falsos Positivos

Si hay falsos positivos (bloqueos incorrectos), verificar:

1. La consistencia de los identificadores de tenant entre servicios
2. El correcto funcionamiento de Redis
3. La sincronización de tiempo entre instancias

### Problema: Logging Excesivo

Ajustar niveles de log:
- ERROR: Solo para errores reales que impiden el funcionamiento
- WARNING: Para límites excedidos
- DEBUG: Para información detallada (desactivar en producción)

## Evolución Futura

Próximas mejoras planificadas:

1. Implementación de ventanas deslizantes para límites más precisos
2. Integración con sistema de métricas para monitoreo en tiempo real
3. Configuración dinámica de límites sin reinicio de servicios

---

*Documento mantenido por el equipo de backend - Abril 2025*
