# Implementación de Modelos para Agent Service

## Resumen

Este documento detalla la implementación de los modelos necesarios para el Agent Service siguiendo el plan de implementación del Bloque 1. Los modelos están diseñados para soportar las funcionalidades clave del servicio, incluyendo herramientas de agente, gestión de contexto, comunicación entre servicios y estrategias de colección.

## Modelos Implementados

### 1. Modelos para Herramientas (`tools.py`)

Estos modelos definen las herramientas disponibles para los agentes y sus esquemas de entrada/salida:

- `ToolType`: Enumeración de tipos de herramientas soportadas (RAG, API externa, etc.)
- `ToolExecutionMetadata`: Metadatos para tracking de ejecución de herramientas
- Esquemas de entrada/salida para cada tipo de herramienta:
  - RAG: `RAGQueryInput`, `RAGQueryOutput`, `RAGQuerySource`
  - Web Search: `WebSearchInput`, `WebSearchOutput`, `WebSearchResult`
  - APIs Externas: `ExternalAPIInput`, `ExternalAPIOutput`
  - Consulta a otros agentes: `ConsultAgentInput`, `ConsultAgentOutput`
- `ToolConfig`: Configuración genérica para cualquier herramienta

#### Ejemplo de Uso

```python
from models import RAGQueryInput, ToolType, ToolConfig

# Configurar herramienta RAG
rag_config = ToolConfig(
    tool_type=ToolType.RAG_QUERY,
    name="collection_search",
    description="Busca información relevante en colecciones de documentos",
    enabled=True,
    config={
        "default_collection_id": "col123",
        "similarity_top_k": 5
    }
)

# Crear entrada para consulta RAG
query_input = RAGQueryInput(
    query="¿Cuáles son las características del producto X?",
    collection_id="col123",
    top_k=4,
    threshold=0.75
)
```

### 2. Modelos para Gestión de Contexto (`context.py`)

Estos modelos permiten la propagación de contexto entre servicios:

- `ContextConfig`: Configuración para propagación de contexto
- `ContextPayload`: Datos a propagar entre servicios (tenant_id, user_id, etc.)
- `ContextManager`: Gestor de contexto para operaciones del Agent Service

#### Ejemplo de Uso

```python
from models import ContextPayload, ContextManager, ContextConfig

# Crear contexto para una solicitud
context = ContextPayload(
    tenant_id="tenant123",
    user_id="user456",
    conversation_id="conv789",
    agent_id="agent001",
    source_service="agent"
)

# Configurar gestor de contexto
context_manager = ContextManager(
    config=ContextConfig(
        propagate_tenant=True,
        propagate_user=True,
        propagate_conversation=True,
        max_context_size_kb=64
    ),
    context=context
)

# Generar headers para llamada a otro servicio
headers = context_manager.propagate(target_service="query")
```

### 3. Modelos para Service Registry (`services.py`)

Estos modelos permiten la comunicación estandarizada entre servicios:

- `ServiceType`: Tipos de servicios en el ecosistema (Query, Embedding, etc.)
- `ServiceConfig`: Configuración para servicios externos
- `RequestMethod`: Métodos HTTP para solicitudes
- `ServiceRequest`/`ServiceResponse`: Esquemas estandarizados para comunicación
- `ServiceRegistry`: Registro centralizado de servicios disponibles

#### Ejemplo de Uso

```python
from models import ServiceType, ServiceConfig, ServiceRegistry, ServiceRequest, RequestMethod

# Configurar registry de servicios
registry = ServiceRegistry()
registry.register_service(ServiceConfig(
    service_name="query",
    service_type=ServiceType.QUERY,
    base_url="http://query-service:8001",
    timeout_seconds=30,
    retry_count=3,
    is_internal=True
))

# Crear solicitud a otro servicio
request = ServiceRequest(
    endpoint="/api/v1/query",
    method=RequestMethod.POST,
    data={
        "query": "¿Qué es machine learning?",
        "collection_id": "col123"
    },
    context=context_payload
)

# Obtener config para llamada
query_config = registry.get_service_config("query")
```

### 4. Modelos para Colecciones (`collections.py`)

Estos modelos definen las estructuras para gestionar colecciones de documentos:

- `CollectionType`: Tipos de colecciones soportadas
- `EmbeddingModelType`: Tipos de modelos de embedding
- `CollectionMetadata`: Metadatos completos de una colección
- `SourceMetadata`/`CollectionSource`: Metadatos de fuentes y documentos
- `StrategyType`/`SelectionCriteria`: Enumeraciones para estrategias de selección
- `CollectionStrategyConfig`: Configuración para estrategias de selección
- `CollectionSelectionResult`: Resultado de la selección de colecciones

#### Ejemplo de Uso

```python
from models import CollectionStrategyConfig, StrategyType, SelectionCriteria

# Configurar estrategia de selección de colecciones
strategy_config = CollectionStrategyConfig(
    strategy_type=StrategyType.MULTI,
    collection_ids=["col123", "col456", "col789"],
    federate_results=True,
    per_collection_limit=3,
    selection_criteria=SelectionCriteria.SIMILARITY,
    similarity_threshold=0.7,
    max_collections=3
)
```

## Integración con Módulos Existentes

### Actualización del Archivo de Inicialización

Se ha actualizado el archivo `models/__init__.py` para importar y exportar correctamente todos los modelos:

```python
from .agent import (Agent, AgentCreate, ...)
from .response import (BaseResponse, ChatRequest, ...)
from .tools import (ToolType, RAGQueryInput, ...)
from .context import (ContextConfig, ContextPayload, ...)
from .services import (ServiceType, ServiceConfig, ...)
from .collections import (CollectionMetadata, StrategyType, ...)

__all__ = [
    # Lista completa de modelos exportados
    # ...
]
```

### Compatibilidad con Patrones Establecidos

Los modelos implementados siguen los patrones y estándares establecidos:

1. **Validación de Datos**:
   - Uso de `validator` y `root_validator` de Pydantic para validaciones complejas
   - Restricciones de rango en valores numéricos (scores, thresholds)
   - Validaciones de coherencia entre campos relacionados

2. **Documentación Completa**:
   - Docstrings detallados en todas las clases
   - Descripción en cada campo con `Field(..., description="...")`
   - Comentarios en validadores y métodos auxiliares

3. **Flexibilidad y Extensibilidad**:
   - Campos opcionales con valores por defecto sensatos
   - Soporte para metadatos personalizados en todos los modelos relevantes
   - Enumeraciones para tipos que pueden expandirse en el futuro

## Campos Obligatorios vs. Opcionales

### Campos Obligatorios Comunes

- `tenant_id`: Presente en casi todos los modelos para asegurar multitenancy
- Identificadores únicos (`agent_id`, `collection_id`, etc.) cuando es necesario
- Campos de configuración esenciales para cada tipo de operación

### Campos Opcionales Comunes

- `metadata`: Diccionario de metadatos adicionales
- `description`: Campo descriptivo textual
- `context`: En solicitudes entre servicios

## Consideraciones para Implementaciones Futuras

1. **Multi-Agente**: Los modelos implementados soportan las necesidades del sistema multi-agente, especialmente a través de `ConsultAgentInput/Output` y `ContextManager`.

2. **Colecciones Federadas**: La implementación de `CollectionStrategyConfig` permite estrategias avanzadas de selección y federación de colecciones.

3. **Extensiones de Herramientas**: El diseño de `ToolConfig` y los esquemas de entrada/salida de herramientas facilita la adición de nuevas herramientas en el futuro.

4. **Servicios Externos**: El `ServiceRegistry` está preparado para integrarse con cualquier servicio externo que se añada posteriormente.

## Conclusión

Los modelos implementados proporcionan una base sólida para el desarrollo del Agent Service, siguiendo las mejores prácticas del proyecto Nooble3 y permitiendo la escalabilidad y extensibilidad necesarias para las fases futuras del proyecto.
