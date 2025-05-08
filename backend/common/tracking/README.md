# Sistema Centralizado de Tracking y Contabilización

## Descripción General

Este módulo proporciona un sistema centralizado para el tracking, contabilización y atribución de recursos en la plataforma, con enfoque principal en el consumo de tokens LLM y embeddings. Está diseñado para garantizar precisión, auditabilidad y reconciliación entre los diferentes servicios backend y la base de datos.

### Características Principales

- **Tipos Estandarizados**: Uso de ENUM para categorías uniformes (`token_type`, `operation_type`)
- **Idempotencia**: Prevención de doble conteo en operaciones críticas y reintentos
- **Procedimiento Unificado**: Una sola función con fallback robusto para todos los servicios
- **Reporting Mejorado**: Tablas detalladas para análisis diario y mensual de consumo

## Arquitectura del Sistema

### Componentes Principales

1. **API de Tracking** (`_base.py`)
   - Interfaz unificada para el registro de uso de recursos
   - Implementación de políticas de rate limiting
   - Integración con sistema de caché para contadores rápidos

2. **Servicio de Atribución** (`attribution.py`)
   - Determina la propiedad de los tokens según el contexto
   - Maneja casos especiales como agentes compartidos
   - Implementa reglas de negocio para atribución de costos

3. **Sistema de Reconciliación** (`reconciliation.py`)
   - Garantiza consistencia entre contadores en memoria y base de datos
   - Ejecuta tareas de consolidación periódicas
   - Resuelve discrepancias en contadores

4. **Alertas y Notificaciones** (`alerts.py`)
   - Monitorea umbrales de consumo
   - Notifica sobre anomalías o uso excesivo
   - Registra eventos para auditoría

### Flujo de Datos

```
Servicio Backend → track_token_usage → TokenAttributionService → RPC track_token_usage → Base de Datos
                          |                                     ↓
                          ↓                          Tablas de tracking diario/mensual
                    Verificación Idempotencia              ↓
                          |                       Actualización de tenant_stats
                          ↓                               ↓
                   Rate Limiting Cache → Alertas/Métricas → Reconciliación periódica
```

## Sistema Unificado de Tracking

### Función Principal

**Nueva Implementación:** `track_token_usage()`

```python
async def track_token_usage(
    tenant_id: Optional[str] = None,
    tokens: int = 0,
    model: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    token_type: str = "llm",  # Usar constantes TOKEN_TYPE_*
    operation: str = "query", # Usar constantes OPERATION_*
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None
) -> bool:
    # Implementación con soporte de idempotencia y tipos estandarizados
)
```

**Características:**
- Obtiene contexto automáticamente si no se proporciona
- Implementa verificación de límites de rate
- Enriquece metadatos con información contextual
- Maneja atribución de tokens a través de TokenAttributionService
- Registra métricas detalladas
- Captura excepciones y garantiza observabilidad

### Sistema RPC Supabase

**Función Principal:** `increment_token_usage_raw()`

```python
async def increment_token_usage_raw(
    tenant_id: str, 
    tokens: int,
    agent_id: Optional[str] = None,
    # ...más parámetros
)
```

**Características:**
- Llamada directa al procedimiento almacenado
- Sin lógica de negocio, solo persistencia
- Diferencia entre tipos de tokens (llm/embedding)
- Atomicidad garantizada por la base de datos
- Enfoque puramente transaccional

### Procedimientos Almacenados en Supabase

```sql
-- Ejemplo de increment_token_usage en Supabase
create or replace function increment_token_usage(
    p_tenant_id text,
    p_tokens integer
) returns void as $$
begin
    -- Actualizar contador diario
    insert into daily_token_usage (tenant_id, date, tokens)
    values (p_tenant_id, current_date, p_tokens)
    on conflict (tenant_id, date) 
    do update set tokens = daily_token_usage.tokens + p_tokens;
    
    -- Actualizar contador mensual
    insert into monthly_token_usage (tenant_id, year_month, tokens)
    values (p_tenant_id, to_char(current_date, 'YYYY-MM'), p_tokens)
    on conflict (tenant_id, year_month) 
    do update set tokens = monthly_token_usage.tokens + p_tokens;
end;
$$ language plpgsql;
```

## Análisis de Consistencia

| Aspecto | Sistema Centralizado | Sistema RPC | Estado |
|---------|----------------------|------------|--------|
| **Contabilización básica** | ✅ Implementada | ✅ Implementada | **Consistente** |
| **Tipos de tokens** | ✅ LLM, Embedding | ✅ LLM, Embedding | **Consistente** |
| **Atribución** | ✅ Con lógica avanzada | ⚠️ Solo persistencia | **Complementario** |
| **Rate Limiting** | ✅ Implementado | ❌ No aplicable | **N/A** |
| **Metadatos** | ✅ Enriquecidos | ⚠️ Básicos | **Parcial** |
| **Manejo de errores** | ✅ Robusto | ⚠️ Básico | **Mejora posible** |
| **Reconciliación** | ✅ Implementada | ❌ No aplicable | **N/A** |

## Fortalezas y Debilidades

### Fortalezas

1. **Arquitectura en Capas:**
   - Clara separación entre lógica de negocio (tracking) y persistencia (RPC)
   - Facilita pruebas y mantenimiento

2. **Manejo de Contexto:**
   - Extracción automática de tenant_id, agent_id, etc.
   - Validación consistente de parámetros

3. **Atribución Inteligente:**
   - Determina correctamente quién debe ser facturado
   - Maneja escenarios complejos como agentes compartidos

4. **Observabilidad:**
   - Registro detallado de errores y excepciones
   - Métricas enriquecidas para análisis

### Debilidades

1. **Posibles Inconsistencias:**
   - El procedimiento RPC y el servicio de atribución podrían divergir en sus reglas
   - Dependencia de transaccionalidad en base de datos

2. **Complejidad:**
   - Sistema multinivel con varios componentes
   - Curva de aprendizaje para nuevos desarrolladores

3. **Overhead Potencial:**
   - Múltiples capas pueden añadir latencia
   - Verificaciones adicionales en cada llamada

## Recomendaciones para Mejora

### 1. Unificación de Definiciones

**Problema:**
Las definiciones de tipos de tokens y operaciones están dispersas entre el código backend y los procedimientos RPC.

**Solución:**
Implementar un sistema centralizado de constantes compartidas entre backend y procedimientos RPC.

```python
# En constants.py centralizado
TOKEN_TYPES = {
    "LLM": "llm",
    "EMBEDDING": "embedding",
    "FINE_TUNING": "fine_tuning"
}

# Igual constante en SQL
-- En migrations de Supabase
CREATE TYPE token_type AS ENUM ('llm', 'embedding', 'fine_tuning');
```

### 2. Implementación de Idempotencia

**Problema:**
El sistema actual podría contabilizar dos veces en casos de reintentos o reconexiones.

**Solución:**
Implementar tokens de idempotencia para garantizar que cada operación se contabilice una sola vez.

```python
async def track_token_usage(
    # ...
    idempotency_key: Optional[str] = None
):
    if idempotency_key:
        # Verificar si ya se procesó esta operación
        from ..cache import CacheManager
        processed = await CacheManager.get("idempotency", idempotency_key)
        if processed:
            return True
    # ...
```

### 3. Mejora en Reconciliación

**Problema:**
La reconciliación actual puede generar inconsistencias temporales.

**Solución:**
Implementar un sistema de doble escritura con verificación periódica.

```python
async def track_token_usage():
    # ...
    # Registrar en caché para contabilización rápida
    await CacheManager.increment("token_counter", f"{tenant_id}:{token_type}", tokens)
    
    # Registrar en base de datos (puede fallar sin bloquear)
    try:
        await rpc_increment_token_usage(...)
    except Exception as e:
        # Marcar para reconciliación posterior
        await register_for_reconciliation(...)
    # ...
```

### 4. Validación Cruzada

**Problema:**
No hay verificación cruzada entre contadores incrementales y totales almacenados.

**Solución:**
Implementar validaciones periódicas entre sumas de incrementos y totales.

```sql
-- En Supabase, crear función de validación
create function validate_token_counters(tenant_id text) returns table (
    counter_type text,
    expected_total bigint,
    actual_total bigint,
    difference bigint
) as $$
    -- Comparar sumas de incrementos vs totales almacenados
    -- ...
$$ language plpgsql;
```

## Decisiones de Diseño

1. **¿Por qué separar tracking y RPC?**
   - **Separación de responsabilidades:** Tracking maneja lógica de negocio, RPC maneja persistencia
   - **Flexibilidad:** Permite cambiar la implementación de persistencia sin afectar la lógica
   - **Testabilidad:** Facilita pruebas unitarias y mocks

2. **¿Por qué atribución centralizada?**
   - **Consistencia:** Garantiza reglas uniformes de atribución
   - **Evolución:** Facilita cambios en políticas de negocio
   - **Trazabilidad:** Permite auditoría clara de decisiones de atribución

3. **¿Rate limiting en memoria vs. base de datos?**
   - **Rendimiento:** Rate limiting en memoria es órdenes de magnitud más rápido
   - **Precisión:** Aunque menos preciso en entornos multi-instancia, suficiente para la mayoría de casos
   - **Degradación elegante:** Falla abierto si el sistema de caché no está disponible

4. **¿Reconciliación periódica vs. tiempo real?**
   - **Eficiencia:** Reconciliación por lotes es más eficiente
   - **Carga de sistema:** Reduce presión en base de datos
   - **Precisión eventual:** Suficiente para facturación y auditoría

## Conclusión

El sistema actual presenta una arquitectura sólida con clara separación de responsabilidades. La relación entre el tracking centralizado y los procedimientos RPC es complementaria, donde cada componente aporta sus fortalezas. El tracking proporciona lógica de negocio, contexto y observabilidad, mientras que los RPC garantizan atomicidad y persistencia.

Las mejoras propuestas buscan reforzar esta arquitectura, añadiendo garantías adicionales de consistencia e idempotencia, sin cambiar fundamentalmente el diseño actual.

La implementación actual representa un buen equilibrio entre rendimiento y precisión, priorizando la experiencia del usuario (mediante caché y rate limiting en memoria) mientras garantiza precisión eventual para propósitos de facturación y auditoría (mediante reconciliación periódica).
