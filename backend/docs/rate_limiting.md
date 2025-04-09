# Sistema de Rate Limiting Estandarizado

Este documento describe la implementación centralizada del sistema de rate limiting para los servicios backend de Nooble.

## Índice

1. [Descripción General](#descripción-general)
2. [Arquitectura](#arquitectura)
3. [Componentes](#componentes)
4. [Guía de Uso](#guía-de-uso)
5. [Configuración](#configuración)
6. [Ejemplos](#ejemplos)

## Descripción General

El sistema de rate limiting protege los servicios contra el uso excesivo, garantizando la disponibilidad y equidad de recursos entre todos los tenants. Implementa los estándares establecidos para manejo de errores, gestión de contexto, centralización de configuración y logging.

### Características Principales

- **Límites personalizables por tenant y servicio**
- **Configuración centralizada** mediante Supabase
- **Manejo consistente de errores** con tipos específicos
- **Contexto enriquecido** en cada operación
- **Headers estándar** en las respuestas HTTP
- **Logging detallado** para monitoreo y auditoría

## Arquitectura

El rate limiting se implementa mediante:

1. **Middleware FastAPI** - Intercepta todas las solicitudes HTTP
2. **Cache distribuido** - Almacena contadores de solicitudes mediante Redis
3. **Configuración centralizada** - Obtiene límites específicos por tenant/servicio
4. **Manejo de excepciones** - Proporciona respuestas consistentes para límites excedidos

## Componentes

### 1. RateLimitMiddleware

Middleware de FastAPI que intercepta las solicitudes entrantes:

```python
from common.utils.rate_limiting import setup_rate_limiting

# En el archivo main.py de cada servicio
app = FastAPI()
setup_rate_limiting(app)
```

### 2. Funciones de Rate Limiting

#### `get_tier_rate_limit`

Obtiene el límite de tasa específico para un tenant y servicio:

```python
# Importación
from common.config.tiers import get_tier_rate_limit

# Uso
rate_limit = await get_tier_rate_limit(tenant_id="tenant123", tier="pro", service_name="chat")
```

#### `apply_rate_limit`

Aplica y verifica el límite de tasa para una operación:

```python
# Importación
from common.utils.rate_limiting import apply_rate_limit

# Uso en rutas o servicios
await apply_rate_limit(tenant_id="tenant123", tier="pro", limit_key="chat")
```

### 3. Excepciones

```python
# Importación de excepciones específicas
from common.errors.exceptions import RateLimitExceeded, ErrorCode

# Ejemplo de manejo
try:
    await apply_rate_limit(tenant_id, tier, "query")
except RateLimitExceeded as e:
    # Manejar límite excedido
    return JSONResponse(
        status_code=429,
        content={"message": e.message, "code": e.error_code}
    )
```

## Guía de Uso

### Implementación en Nuevos Servicios

1. **Configurar el middleware** en el archivo `main.py`:

```python
from fastapi import FastAPI
from common.utils.rate_limiting import setup_rate_limiting

app = FastAPI()
setup_rate_limiting(app)
```

2. **Aplicar rate limiting manual** en operaciones costosas o críticas:

```python
from common.utils.rate_limiting import apply_rate_limit
from common.context.vars import get_current_tenant_id

async def process_expensive_operation(data):
    tenant_id = get_current_tenant_id()
    tier = get_tenant_tier(tenant_id)
    
    # Verificar límites específicos antes de proceder
    await apply_rate_limit(tenant_id, tier, "expensive_operation")
    
    # Proceder con la operación...
```

### Exclusión de Rutas

Para excluir rutas específicas del rate limiting (como endpoints de salud o métricas):

```python
from common.utils.rate_limiting import setup_rate_limiting

app = FastAPI()
setup_rate_limiting(
    app, 
    exclude_paths=["/health", "/metrics", "/docs", "/openapi.json"]
)
```

## Configuración

### Límites por Tier

Los límites por defecto para cada tier están definidos en `common/config/tiers.py`:

| Tier | Límite (req/min) |
|------|------------------|
| free | 600 |
| pro | 1,200 |
| business | 3,000 |
| enterprise | 6,000 |

### Multiplicadores por Servicio

Algunos servicios tienen multiplicadores que ajustan los límites base:

| Servicio | Multiplicador |
|----------|---------------|
| agent | 0.5 |
| chat | 0.5 |
| embedding | 2.0 |
| query | 1.0 |
| ingestion | 0.3 |
| collection | 0.5 |

### Personalización por Tenant

Se pueden definir límites personalizados por tenant en Supabase:

```
{
  "max_requests": 1500,
  "limit_window_seconds": 60
}
```

## Ejemplos

### Ejemplo 1: Ruta con Rate Limiting

```python
from fastapi import APIRouter, Depends, HTTPException
from common.context.deps import with_context
from common.utils.rate_limiting import apply_rate_limit

router = APIRouter()

@router.post("/query")
@with_context()
async def process_query(query_data: QueryRequest):
    # Rate limiting ya aplicado por el middleware
    # Código de procesamiento...
    return {"result": "success"}
```

### Ejemplo 2: Verificación Manual

```python
from common.utils.rate_limiting import apply_rate_limit
from common.errors.exceptions import RateLimitExceeded

async def process_large_batch(items):
    try:
        # Verificar límites antes de procesar un lote grande
        await apply_rate_limit(tenant_id, tier, "batch_process")
        
        # Procesar el lote...
        return {"processed": len(items)}
    except RateLimitExceeded as e:
        # Manejar el error de manera específica
        logger.warning(f"Rate limit excedido para batch: {e.message}", extra=e.context)
        return {"error": e.message, "retry_after": e.context.get("reset_in_seconds")}
```

## Buenas Prácticas

1. **Siempre usar el middleware** para protección básica de endpoints
2. **Aplicar límites adicionales** para operaciones costosas
3. **Manejar RateLimitExceeded** de manera adecuada
4. **Usar parámetros de context** cuando estén disponibles
5. **Incluir información de rate limit** en la documentación API

---

*Última actualización: Abril 2025*
