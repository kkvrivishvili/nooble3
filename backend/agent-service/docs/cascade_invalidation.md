# Invalidación en Cascada de Caché en Agent Service

## Resumen

Este documento describe la implementación de un sistema de invalidación en cascada para la caché del Agent Service, que permite eliminar de forma coordinada todas las cachés relacionadas con un recurso (agente, conversación) cuando este es modificado.

## Implementación

### 1. Funciones de Invalidación en Cascada

Se han implementado funciones especializadas para invalidar recursos relacionados en `services/cache_utils.py`:

```python
async def invalidate_agent_cache_cascade(tenant_id, agent_id, invalidate_conversations=False):
    """Invalida en cascada todas las cachés relacionadas con un agente."""

async def invalidate_conversation_cache_cascade(tenant_id, conversation_id, agent_id=None):
    """Invalida en cascada todas las cachés relacionadas con una conversación."""
```

### 2. Jerarquía de Dependencias

El sistema reconoce las siguientes dependencias entre recursos en caché:

- **Agente**:
  - Configuración del agente
  - Herramientas del agente
  - Estado de ejecución
  - Conversaciones asociadas (opcional)

- **Conversación**:
  - Memoria de conversación
  - Lista de mensajes
  - Mensajes individuales

### 3. Implementación de `invalidate_agent_cache_cascade`

```python
async def invalidate_agent_cache_cascade(
    tenant_id: str,
    agent_id: str,
    invalidate_conversations: bool = False,
    ctx = None
) -> Dict[str, Any]:
    """
    Invalida en cascada todas las cachés relacionadas con un agente.
    
    Args:
        tenant_id: ID del tenant
        agent_id: ID del agente
        invalidate_conversations: Si es True, también invalida la caché de conversaciones
        ctx: Contexto opcional
        
    Returns:
        Diccionario con resultados de invalidación (número de claves invalidadas por tipo)
    """
    invalidation_results = {
        "agent": 0,
        "agent_config": 0,
        "agent_tools": 0,
        "conversations": 0,
        "messages": 0
    }
    
    # 1. Invalidar configuración del agente
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT, 
        resource_id=agent_id
    )
    invalidation_results["agent"] += 1
    
    # 2. Invalidar configuración de herramientas
    await CacheManager.invalidate(
        tenant_id=tenant_id, 
        data_type=CACHE_TYPE_AGENT_CONFIG, 
        resource_id=agent_id
    )
    invalidation_results["agent_config"] += 1
    
    # ... (invalidación de otros recursos)
    
    # Registrar métricas de invalidación
    await track_cache_metrics(
        data_type="agent_cascade", 
        tenant_id=tenant_id, 
        operation="invalidate", 
        hit=True,
        latency_ms=0
    )
    
    return invalidation_results
```

## Patrón de Uso en el Código

```python
# En routes/agents.py, endpoint de actualización
@router.put("/{agent_id}", response_model=AgentResponse)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def update_agent(
    update_data: AgentUpdate,
    agent_id: str = Path(...),
    agent_service: LangChainAgentService = Depends(),
    ctx: Context = None
):
    # ... código existente ...
    
    # Usar invalidación en cascada en lugar de invalidar solo el agente
    from services.cache_utils import invalidate_agent_cache_cascade
    invalidation_results = await invalidate_agent_cache_cascade(
        tenant_id=tenant_id,
        agent_id=agent_id,
        invalidate_conversations=False  # Solo invalidar conversaciones si es necesario
    )
    logger.debug(f"Cache invalidation results: {invalidation_results}")
    
    return AgentResponse(
        success=True,
        message="Agent updated successfully",
        data=updated_agent
    )
```

## Beneficios

- **Coherencia de datos**: Garantiza que todas las cachés relacionadas se invalidan juntas
- **Prevención de estados inconsistentes**: Evita que algunos recursos estén actualizados y otros no
- **Trazabilidad**: Proporciona métricas sobre el número de cachés invalidadas
- **Eficiencia**: Permite realizar invalidaciones selectivas según el caso de uso

## Métricas y Monitoreo

El sistema registra métricas detalladas sobre las invalidaciones en cascada:

- **Número de recursos invalidados**: Por tipo (agente, configuración, herramientas, conversaciones)
- **Latencia**: Tiempo que toma completar toda la cascada de invalidación
- **Fallos**: Registro de cualquier error durante el proceso de invalidación

Estas métricas pueden visualizarse en el dashboard de monitoreo para detectar patrones y optimizar el rendimiento.
