# Fase 2: Refactorización del Query Service

## Visión General

Esta fase se centra en la refactorización del Query Service para optimizar su integración con el Agent Service, eliminando dependencias directas con el Embedding Service y mejorando el manejo de embeddings pre-generados, siguiendo la arquitectura de microservicios establecida.

## 2.1 Modificación de Modelos de Datos

### 2.1.1 Actualización de Modelos de Request para Soporte de Embeddings Pre-generados

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from common.models.base import BaseModel as CommonBaseModel

class InternalQueryRequest(CommonBaseModel):
    query: str = Field(..., description="Consulta textual") 
    collection_id: Optional[str] = Field(None, description="ID de la colección a consultar")
    k: int = Field(4, description="Número de resultados a retornar")
    query_embedding: Optional[List[float]] = Field(None, description="Embedding pre-generado (desde Agent Service)")
    llm_model: Optional[str] = Field(None, description="Modelo LLM a utilizar")
    response_mode: str = Field("compact", description="Modo de respuesta: compact, tree, etc.")
    similarity_threshold: Optional[float] = Field(None, description="Umbral mínimo de similitud")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadatos adicionales como service_origin")
```

### 2.1.2 Definición de Modelos de Respuesta Estandarizados

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from common.models.base import BaseResponse

class QueryResultItem(BaseModel):
    text: str = Field(..., description="Fragmento de texto relevante")
    document_id: Optional[str] = Field(None, description="ID del documento fuente")
    collection_id: Optional[str] = Field(None, description="ID de la colección origen")
    score: float = Field(..., description="Score de similitud")
    metadata: Optional[Dict[str, Any]] = Field({}, description="Metadatos del documento")

class InternalQueryResponse(BaseResponse):
    data: Dict[str, Any] = Field(
        ...,
        description="Datos de respuesta, incluyendo response y sources"
    )
    metadata: Dict[str, Any] = Field(
        {},
        description="Metadatos de la respuesta, como tokens_used, time_taken, etc."
    )
```

## 2.2 Actualización de `create_query_engine`

### 2.2.1 Refactorización para Aceptar Embeddings Pre-generados

```python
from common.context import Context
from common.errors.handlers import handle_errors
from common.cache import CacheManager, get_with_cache_aside

@handle_errors(error_type="service", log_traceback=True)
async def create_query_engine(
    collection_id: Optional[str] = None,
    query_embedding: Optional[List[float]] = None,  # Embedding pre-generado
    embedding_model_id: Optional[str] = None,  # Modelo utilizado para el embedding
    llm_model_id: Optional[str] = None,  # Modelo LLM a utilizar
    ctx: Context = None
):
    """Crea un motor de consulta para una colección dada.
    
    Args:
        collection_id: ID de la colección (opcional)
        query_embedding: Embedding pre-generado (opcional)
        embedding_model_id: ID del modelo usado para generar el embedding
        llm_model_id: ID del modelo LLM a utilizar para respuestas
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Motor de consulta configurado
        
    Raises:
        MissingEmbeddingError: Si se requiere embedding pero no se proporciona
        CollectionNotFoundError: Si la colección no existe
    """
    if not ctx:
        raise ValueError("Contexto requerido para crear query engine")
        
    tenant_id = ctx.get_tenant_id()
    
    # IMPORTANTE: NO generar embeddings directamente
    # Solo usar los embeddings pre-generados proporcionados por el Agent Service
    if not query_embedding and collection_id:
        # Si no hay embedding pero se requiere colección, es un error
        raise ValueError("Se requiere embedding para consultar colección")
    
    # Obtener vector store con posible caché
    if collection_id:
        vector_store = await get_vector_store_for_collection(
            tenant_id=tenant_id, 
            collection_id=collection_id, 
            ctx=ctx
        )
    else:
        vector_store = None
        
    # Configurar prompts según modelo LLM especificado
    from common.llm.prompts import get_prompts_for_model
    prompts = get_prompts_for_model(llm_model_id) if llm_model_id else get_default_prompts()
    
    # Crear LLM usando factory para asegurar el uso de Groq
    llm = create_llm_for_queries(model_id=llm_model_id, ctx=ctx)
    
    # Configurar query engine con embedding proporcionado
    query_engine = QueryEngineBuilder()\
        .with_vector_store(vector_store)\
        .with_embedding(query_embedding)\
        .with_llm(llm)\
        .with_prompts(prompts)\
        .with_context(ctx)\
        .build()
        
    return query_engine
```

### 2.2.2 Eliminación de Dependencias con Embedding Service

```python
# INCORRECTO - Este método debe ser eliminado del Query Service
# async def get_embedding(text: str, model: str, ctx: Context) -> List[float]:
#     """Obtiene embedding directamente del Embedding Service - ESTO DEBE ELIMINARSE"""
#     embedding_service_url = get_settings().embedding_service_url
#     # Resto del código que debe eliminarse...

# CORRECTO - Usar embeddings pre-generados
async def process_query_with_embedding(
    query: str,
    query_embedding: List[float],  # Usar embedding pre-generado que viene del request
    collection_id: str,
    llm_model: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """Procesa consulta utilizando embedding pre-generado proporcionado por el Agent Service
    
    Args:
        query: Consulta textual
        query_embedding: Embedding pre-generado (de Agent Service a través de Embedding Service)
        collection_id: ID de la colección a consultar
        llm_model: Modelo LLM a utilizar (opcional)
        ctx: Contexto con tenant_id
        
    Returns:
        Resultado de la consulta con fuentes
    """
    # Crear query engine con embedding pre-generado
    engine = await create_query_engine(
        collection_id=collection_id,
        query_embedding=query_embedding,
        llm_model_id=llm_model,
        ctx=ctx
    )
    
    # Procesar consulta
    result = await engine.query(query)
    
    # Registrar estadísticas (si hay servicio de métricas)
    await track_query_metrics(
        tenant_id=ctx.get_tenant_id() if ctx else None,
        collection_id=collection_id,
        query_text_length=len(query),
        result_tokens=result.get("tokens_used", 0),
        source_count=len(result.get("sources", [])),
        metadata={
            "embedding_provided": True,  # Importante: marcar que se usó embedding pre-generado
            "llm_model": llm_model
        }
    )
    
    return result
```

## 2.3 Actualización de Endpoints Internos

### 2.3.1 Refactorización de `/internal/query`

```python
from fastapi import APIRouter, Body, Depends
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.models.base import BaseResponse

router = APIRouter()

@router.post("/internal/query", response_model=None)
@with_context(tenant=True, collection=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_query(
    request: InternalQueryRequest = Body(...),
    ctx: Context = None
):
    """Endpoint interno para procesar consultas con embeddings pre-generados."""
    tenant_id = ctx.get_tenant_id()
    collection_id = ctx.get_collection_id() or request.collection_id
    
    # Extraer metadata de origen para tracking
    metadata = request.metadata or {}
    service_origin = metadata.get("service_origin", "unknown")
    
    # Validar que se proporciona embedding
    if not request.query_embedding and not request.skip_embedding:
        return BaseResponse(
            success=False,
            message="Se requiere embedding pre-generado para consultas internas",
            error={
                "code": "missing_embedding",
                "details": "Este endpoint requiere embeddings pre-generados desde el Agent Service"
            }
        )
    
    # Crear engine con embedding pre-generado
    result = await process_query_with_embedding(
        query=request.query,
        query_embedding=request.query_embedding,
        collection_id=collection_id,
        llm_model=request.llm_model,
        ctx=ctx
    )
    
    # Retornar respuesta estándar
    return BaseResponse(
        success=True,
        message="Query procesada con éxito",
        data=result,
        metadata={
            "service_origin": service_origin,
            "embedding_provided": request.query_embedding is not None,
            "collection_id": collection_id
        }
    )
```

### 2.3.2 Actualización de `/internal/search`

```python
@router.post("/internal/search", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_search(
    request: InternalSearchRequest = Body(...),
    ctx: Context = None
):
    """Endpoint interno para búsqueda semántica con embeddings pre-generados."""
    tenant_id = ctx.get_tenant_id()
    
    # Extraer metadata para tracking
    metadata = request.metadata or {}
    service_origin = metadata.get("service_origin", "unknown")
    
    # Validar embedding proporcionado
    if not request.query_embedding:
        return BaseResponse(
            success=False,
            message="Se requiere embedding pre-generado para búsqueda semántica",
            error={
                "code": "missing_embedding",
                "details": "Este endpoint requiere embeddings pre-generados desde el Agent Service"
            }
        )
    
    # Realizar búsqueda semántica
    results = await semantic_search(
        query_embedding=request.query_embedding,
        collection_id=request.collection_id,
        k=request.k,
        filters=request.filters,
        ctx=ctx
    )
    
    # Retornar respuesta estándar
    return BaseResponse(
        success=True,
        message="Búsqueda semántica completada",
        data={"results": results},
        metadata={
            "service_origin": service_origin,
            "collection_id": request.collection_id,
            "result_count": len(results)
        }
    )
```

## 2.4 Implementación de Factory de LLM

Para asegurar que el Query Service utilice exclusivamente Groq para modelos LLM:

```python
from common.context import Context
from common.errors.handlers import handle_errors
from common.config.tiers import get_llm_model_details

@handle_errors(error_type="service", log_traceback=True)
def create_llm_for_queries(model_id: Optional[str] = None, ctx: Context = None) -> Any:
    """Factory para crear instancias de LLM, asegurando que se use Groq exclusivamente
    
    Args:
        model_id: ID del modelo LLM a utilizar (opcional)
        ctx: Contexto con tenant_id para determinar tier
        
    Returns:
        Instancia de LLM configurada
        
    Raises:
        ModelNotAvailableError: Si el modelo solicitado no está disponible
    """
    from langchain.llms import Groq
    from common.config.settings import get_settings
    
    settings = get_settings()
    
    # Determinar modelo a usar (específico o por tier)
    if model_id:
        # Validar que el modelo solicitado esté disponible
        model_details = get_llm_model_details(model_id)
        if not model_details:
            raise ModelNotAvailableError(f"Modelo LLM no disponible: {model_id}")
        
        # Verificar que sea modelo de Groq
        if model_details.get("provider") != "groq":
            logger.warning(f"Modelo {model_id} no es de Groq, utilizando alternativa de Groq")
            model_id = "llama2-70b-4096"  # Modelo fallback de Groq
    else:
        # Si no se especifica, usar modelo default de tier
        model_id = "llama2-70b-4096"  # Default
    
    # Crear instancia LLM de Groq
    return Groq(
        api_key=settings.groq_api_key,
        model_name=model_id,
        temperature=0.2,  # Baja temperatura para queries RAG
        max_tokens=1024,
        streaming=False
    )
```

## Tareas Pendientes

- [ ] Actualizar la estructura de modelos para aceptar embeddings pre-generados
- [ ] Refactorizar `create_query_engine` para eliminar dependencia con Embedding Service
- [ ] Modificar endpoints internos para validar y utilizar embeddings proporcionados
- [ ] Implementar factory de LLM para asegurar el uso exclusivo de Groq
- [ ] Actualizar documentación interna para reflejar nuevos patrones de uso
