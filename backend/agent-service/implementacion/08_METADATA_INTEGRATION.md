# Fase 8: Integración de Metadatos entre LlamaIndex y LangChain

## Visión General

Esta fase aborda la integración de metadatos entre los servicios basados en LlamaIndex (ingestion, query y embedding) y el servicio de agentes basado en LangChain. El objetivo principal es garantizar una comunicación estandarizada y unificada entre estos frameworks diferentes, manteniendo la coherencia en todo el sistema y facilitando el mantenimiento futuro.

## 8.1 Estandarización de Metadatos para LangChain

### 8.1.1 Función Central para Compatibilidad

```python
# common/langchain/metadata_helpers.py

from typing import Dict, Any, Optional
from common.context import Context
from common.cache import standardize_llama_metadata  # Reutilizar la función base

def standardize_langchain_metadata(
    metadata: Dict[str, Any],
    tenant_id: str = None,
    agent_id: str = None,
    conversation_id: str = None,
    collection_id: str = None,
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """
    Estandariza los metadatos para componentes LangChain manteniendo
    compatibilidad con el estándar de LlamaIndex.
    
    Garantiza interoperabilidad entre los servicios existentes y el Agent Service.
    
    Args:
        metadata: Metadatos originales a estandarizar
        tenant_id: ID de tenant (obligatorio)
        agent_id: ID del agente LangChain
        conversation_id: ID de la conversación  
        collection_id: ID de colección para mantener coherencia con LlamaIndex
        ctx: Contexto para valores por defecto
        
    Returns:
        Dict[str, Any]: Metadatos estandarizados compatibles con ambos sistemas
    """
    # Primero aplicar el estándar LlamaIndex para mantener compatibilidad base
    standardized = standardize_llama_metadata(
        metadata=metadata,
        tenant_id=tenant_id,
        collection_id=collection_id,
        ctx=ctx
    )
    
    # Añadir campos específicos de LangChain
    if agent_id:
        standardized["agent_id"] = agent_id
    elif ctx and ctx.get_agent_id():
        standardized["agent_id"] = ctx.get_agent_id()
    
    if conversation_id:
        standardized["conversation_id"] = conversation_id
    elif ctx and ctx.get_conversation_id():
        standardized["conversation_id"] = ctx.get_conversation_id()
    
    # Añadir indicador de origen para facilitar depuración
    standardized["source_framework"] = "langchain"
    
    return standardized
```

### 8.1.2 Exportación Centralizada

```python
# common/langchain/__init__.py

from .metadata_helpers import standardize_langchain_metadata

__all__ = [
    "standardize_langchain_metadata",
    # Otras exportaciones...
]
```

## 8.2 Integración con RAGQueryTool

### 8.2.1 Implementación de Adaptador

```python
# agent-service/tools/rag_query_tool.py

from common.langchain import standardize_langchain_metadata

class RAGQueryTool:
    # ...
    
    async def _run_query(self, query_text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Ejecuta una consulta RAG usando el Query Service, manteniendo
        compatibilidad con el estándar de metadatos.
        """
        metadata = metadata or {}
        
        # Estandarizar metadatos para asegurar compatibilidad con LlamaIndex
        try:
            standardized_metadata = standardize_langchain_metadata(
                metadata=metadata,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                collection_id=self.collection_id,
                ctx=self.ctx
            )
        except ValueError as ve:
            logger.warning(f"Error en estandarización de metadatos: {str(ve)}")
            # Estrategia de recuperación con metadatos mínimos
            standardized_metadata = standardize_langchain_metadata(
                metadata={},
                tenant_id=self.tenant_id,
                ctx=self.ctx
            )
            
        # Llamar al servicio de consulta con metadatos compatibles
        response = await self.query_service_client.query(
            query=query_text,
            metadata=standardized_metadata
        )
        
        # Procesar los resultados manteniendo la estructura de metadatos
        return self._process_query_response(response)
```

## 8.3 Actualización del Agent Service

### 8.3.1 Integración en LangChainAgentService

```python
# agent-service/core/langchain_agent_service.py

from common.langchain import standardize_langchain_metadata

class LangChainAgentService:
    # ...
    
    async def execute_agent(self, 
                          input_text: str, 
                          collection_id: Optional[str] = None,
                          collection_metadata: Optional[Dict[str, Any]] = None,
                          tenant_tier: Optional[str] = None,
                          embedding_model: Optional[str] = None,
                          llm_model: Optional[str] = None,
                          use_auto_federation: bool = False,
                          use_streaming: bool = False,
                          use_async: bool = False,
                          ctx: Context = None) -> AgentResponse:
        """Ejecuta un agente con metadatos estandarizados"""
        # ...
        
        # Estandarizar metadatos de colección para garantizar compatibilidad
        if collection_metadata:
            collection_metadata = standardize_langchain_metadata(
                metadata=collection_metadata,
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                collection_id=collection_id,
                ctx=ctx
            )
        
        # Crear herramientas con metadatos estandarizados
        tools = await self.create_tools(
            tenant_id=tenant_id,
            collection_id=collection_id,
            collection_metadata=collection_metadata,
            use_auto_federation=use_auto_federation
        )
        
        # Continuar con la ejecución del agente
        # ...
```

## 8.4 Compatibilidad Bidireccional

### 8.4.1 Procesamiento de Respuestas LlamaIndex

```python
# agent-service/tools/manifest_wrapper.py

class ManifestRAGTool(BaseTool):
    # ...
    
    def _process_llama_index_response(self, response, query):
        """
        Procesa la respuesta de LlamaIndex manteniendo la estructura de metadatos.
        """
        # Extraer información relevante
        answer = response.response
        sources = []
        
        # Procesar nodos fuente con metadatos estandarizados
        for node_with_score in response.source_nodes:
            source_metadata = node_with_score.node.metadata.copy()
            
            # Aplicar estandarización para garantizar compatibilidad
            try:
                standardized_metadata = standardize_langchain_metadata(
                    metadata=source_metadata,
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    conversation_id=self.conversation_id,
                    ctx=self.ctx
                )
            except Exception as e:
                logger.warning(f"Error estandarizando metadatos: {str(e)}")
                standardized_metadata = source_metadata
            
            # Crear estructura de fuente con metadatos compatibles
            sources.append({
                "text": node_with_score.node.get_content(),
                "metadata": standardized_metadata,
                "score": node_with_score.score
            })
        
        # Devolver resultado final
        return {
            "answer": answer,
            "sources": sources
        }
```

### 8.4.2 Integración con el Sistema de Colas

```python
# common/queue/work_queue.py

from common.langchain import standardize_langchain_metadata

class WorkQueueService:
    # ...
    
    async def register_job(self, tenant_id, job_type, params, task, ctx=None, ttl=None):
        """
        Registra un nuevo trabajo con metadatos estandarizados.
        """
        # ...
        
        # Estandarizar metadatos de parámetros para caché consistente
        if isinstance(params, dict) and any(k in params for k in ["metadata", "collection_metadata"]):
            metadata_key = next(k for k in ["metadata", "collection_metadata"] if k in params)
            original_metadata = params[metadata_key] or {}
            
            # Aplicar estandarización para garantizar compatibilidad con caché
            params[metadata_key] = standardize_langchain_metadata(
                metadata=original_metadata,
                tenant_id=tenant_id,
                ctx=ctx
            )
        
        # Continuar con el registro del trabajo
        # ...
```

## 8.5 Pruebas de Integración

### 8.5.1 Pruebas de Compatibilidad entre Frameworks

```python
# agent-service/tests/integration/test_metadata_integration.py

import pytest
from common.langchain import standardize_langchain_metadata

async def test_metadata_propagation_between_frameworks():
    """
    Verifica la correcta propagación de metadatos entre LlamaIndex y LangChain.
    """
    # Configuración inicial
    tenant_id = "test_tenant"
    collection_id = "test_collection"
    agent_id = "test_agent"
    
    # Crear metadatos con LangChain
    langchain_metadata = standardize_langchain_metadata(
        metadata={"custom_field": "value"},
        tenant_id=tenant_id,
        agent_id=agent_id,
        collection_id=collection_id
    )
    
    # Simular paso a servicio de consulta basado en LlamaIndex
    # ... código de consulta ...
    
    # Verificar que los campos clave se preservan en ambas direcciones
    assert result_metadata.get("tenant_id") == tenant_id
    assert result_metadata.get("collection_id") == collection_id
    assert result_metadata.get("agent_id") == agent_id
    assert result_metadata.get("custom_field") == "value"
```

## 8.6 Extensión de la Documentación Existente

### 8.6.1 Actualización de Estándares de Metadatos

Para completar la integración, se debe actualizar la documentación existente (`docs/metadata_standard.md`) con una nueva sección:

```markdown
## Integración con LangChain (Agent Service)

Se ha implementado `standardize_langchain_metadata` como equivalente a `standardize_llama_metadata` 
para mantener la compatibilidad bidireccional entre servicios basados en LlamaIndex y el nuevo 
Agent Service basado en LangChain.

### Campos adicionales para LangChain:

| Campo | Descripción | Obligatoriedad | Implicancia |
|-------|-------------|----------------|-------------|
| `agent_id` | ID del agente LangChain | Opcional | Enlace con el agente específico |
| `conversation_id` | ID de la conversación | Opcional | Trazabilidad de la conversación |
| `source_framework` | Origen del metadato | Auto-generado | Valor fijo "langchain" |

### Importación Correcta:

```python
from common.langchain import standardize_langchain_metadata
```
```

## Tareas Pendientes

- [ ] Crear estructura de directorios `common/langchain` con los archivos necesarios
- [ ] Implementar función `standardize_langchain_metadata` 
- [ ] Integrar función en RAGQueryTool para comunicación con Query Service
- [ ] Actualizar LangChainAgentService para usar metadatos estandarizados
- [ ] Implementar manejo de respuestas LlamaIndex en herramientas LangChain
- [ ] Integrar con el sistema de colas de trabajo (Fase 7)
- [ ] Crear pruebas de integración para verificar compatibilidad
- [ ] Actualizar documentación existente (`metadata_standard.md`)
