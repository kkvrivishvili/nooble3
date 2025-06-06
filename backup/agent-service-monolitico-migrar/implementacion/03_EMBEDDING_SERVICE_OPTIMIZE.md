# Fase 3: Optimización del Embedding Service

## Visión General

Esta fase se centra en optimizar el Embedding Service para que funcione eficientemente con el Agent Service, mejorando el tracking de tokens, optimizando la caché, y asegurando que solo exponga endpoints internos siguiendo la arquitectura de microservicios establecida.

## 3.1 Reforzar Tracking de Tokens

### 3.1.1 Mejora de Tracking en `provider/openai.py`

```python
from typing import Dict, List, Any, Optional, Tuple
from common.context import Context
from common.errors.handlers import handle_errors
from common.tracking import track_token_usage, OPERATION_EMBEDDING
from common.errors.service_errors import EmbeddingGenerationError
import hashlib
import time

@handle_errors(error_type="service", log_traceback=True)
async def get_openai_embedding(
    text: str, 
    model: str = "text-embedding-3-small",
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Context = None
) -> Tuple[List[float], Dict[str, Any]]:
    """Genera embeddings usando OpenAI con tracking completo.
    
    Args:
        text: Texto para generar embedding
        model: Modelo de OpenAI a utilizar
        metadata: Metadatos adicionales
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Tupla con (embedding, metadata)
        
    Raises:
        EmbeddingGenerationError: Si hay error al generar el embedding
    """
    if not text or not text.strip():
        raise ValueError("El texto no puede estar vacío")
        
    # Obtener tenant_id del contexto
    tenant_id = ctx.get_tenant_id() if ctx else None
    
    # Preparar metadata enriquecida
    metadata = metadata or {}
    text_hash = hashlib.md5(text.encode()).hexdigest()
    enriched_metadata = {
        "text_hash": text_hash,
        "text_length": len(text),
        "model": model
    }
    
    # Añadir IDs relevantes si están disponibles en el contexto
    if ctx:
        if ctx.get_collection_id():
            enriched_metadata["collection_id"] = ctx.get_collection_id()
        if ctx.get_agent_id():
            enriched_metadata["agent_id"] = ctx.get_agent_id()
        if ctx.get_conversation_id():
            enriched_metadata["conversation_id"] = ctx.get_conversation_id()
            
    # Añadir metadata del llamador
    enriched_metadata.update(metadata)
    
    # Generar embedding con OpenAI
    try:
        response = await openai_client.embeddings.create(
            input=[text],
            model=model
        )
        
        embedding = response.data[0].embedding
        
        # Extraer tokens de la respuesta de la API
        token_count = 0
        token_source = "estimated"
        
        if hasattr(response, "usage") and response.usage:
            token_count = response.usage.total_tokens
            token_source = "api"
        else:
            # Estimación local de tokens como fallback
            token_count = len(text.split()) * 1.3  # Aproximación simple
        
        # Validar que el número de tokens sea > 0
        if token_count <= 0:
            logger.warning(f"Número de tokens inválido: {token_count}, usando valor predeterminado")
            # Usar estimación basada en longitud como fallback seguro
            token_count = max(1, len(text) // 4)  # Garantizar al menos 1 token
        
        # Enriquecer metadata con dimensiones y otras métricas
        enriched_metadata.update({
            "dimensions": len(embedding),
            "token_source": token_source,
            "token_count": token_count
        })
        
        # Registrar tokens usando el sistema de tracking centralizado
        if tenant_id:
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=int(token_count),
                model=model,
                token_type="embedding",
                operation=OPERATION_EMBEDDING,
                metadata=enriched_metadata
            )
        
        return embedding, enriched_metadata
        
    except Exception as e:
        raise EmbeddingGenerationError(f"Error al generar embedding: {str(e)}") from e
```

### 3.1.2 Implementación de Métricas Detalladas

```python
from common.tracking.metrics import track_performance_metric

async def track_embedding_metrics(
    tenant_id: str,
    model: str,
    text_length: int,
    token_count: int,
    dimensions: int,
    time_taken_ms: float,
    token_source: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Registra métricas detalladas sobre generación de embeddings
    
    Args:
        tenant_id: ID del tenant
        model: Modelo de embedding utilizado
        text_length: Longitud del texto procesado
        token_count: Número de tokens procesados
        dimensions: Dimensiones del embedding generado
        time_taken_ms: Tiempo de procesamiento en ms
        token_source: Origen del conteo de tokens ('api' o 'estimated')
        metadata: Metadatos adicionales
    """
    # Registrar tiempo de generación
    await track_performance_metric(
        metric_type="embedding_generation_time",
        value=time_taken_ms,
        tenant_id=tenant_id,
        metadata={
            "model": model,
            "text_length": text_length,
            "token_count": token_count,
            "dimensions": dimensions,
            "token_source": token_source,
            **(metadata or {})
        }
    )
    
    # Registrar eficiencia de tokens (tokens/character)
    if text_length > 0:
        token_efficiency = token_count / text_length
        await track_performance_metric(
            metric_type="embedding_token_efficiency",
            value=token_efficiency,
            tenant_id=tenant_id,
            metadata={
                "model": model,
                **(metadata or {})
            }
        )
```

## 3.2 Validar que Solo Existan Endpoints Internos

### 3.2.1 Endpoints Internos para Embedding Service

```python
from fastapi import APIRouter, Body, Depends
from common.context import Context, with_context
from common.errors.handlers import handle_errors
from common.models.base import BaseResponse

router = APIRouter()

@router.post("/internal/embed", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_embed(
    request: InternalEmbeddingRequest = Body(...),
    ctx: Context = None
):
    """Genera embedding para un texto usando OpenAI (exclusivamente para uso interno)"""
    start_time = time.time()
    
    embedding, metadata = await get_openai_embedding(
        text=request.text,
        model=request.model,
        metadata=request.metadata,
        ctx=ctx
    )
    
    # Calcular tiempo de procesamiento
    time_taken_ms = (time.time() - start_time) * 1000
    
    # Registrar métricas detalladas
    tenant_id = ctx.get_tenant_id() if ctx else None
    if tenant_id:
        await track_embedding_metrics(
            tenant_id=tenant_id,
            model=request.model,
            text_length=len(request.text),
            token_count=metadata.get("token_count", 0),
            dimensions=metadata.get("dimensions", 0),
            time_taken_ms=time_taken_ms,
            token_source=metadata.get("token_source", "unknown"),
            metadata={
                "service_origin": request.metadata.get("service_origin", "unknown") if request.metadata else "unknown"
            }
        )
    
    # Añadir tiempo de procesamiento a los metadatos
    metadata.update({"time_taken_ms": time_taken_ms})
    
    return BaseResponse(
        success=True,
        message="Embedding generado con éxito",
        data={"embedding": embedding},
        metadata=metadata
    )

@router.post("/internal/batch", response_model=None)
@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def internal_batch_embed(
    request: BatchEmbeddingRequest = Body(...),
    ctx: Context = None
):
    """Genera embeddings por lotes para múltiples textos (uso interno)"""
    start_time = time.time()
    
    results = []
    total_tokens = 0
    
    # Procesar cada texto en paralelo con límite de concurrencia
    async def process_text(text, index):
        try:
            embedding, metadata = await get_openai_embedding(
                text=text,
                model=request.model,
                metadata={"batch_index": index, **(request.metadata or {})},
                ctx=ctx
            )
            return {"embedding": embedding, "metadata": metadata, "index": index, "error": None}
        except Exception as e:
            logger.error(f"Error generando embedding para índice {index}: {str(e)}")
            return {"embedding": None, "metadata": {}, "index": index, "error": str(e)}
    
    # Limitar concurrencia para evitar sobrecarga de API
    from asyncio import Semaphore
    sem = Semaphore(5)  # Máximo 5 llamadas concurrentes
    
    async def limited_process(text, index):
        async with sem:
            return await process_text(text, index)
    
    # Generar embeddings en paralelo
    tasks = [limited_process(text, i) for i, text in enumerate(request.texts)]
    results = await asyncio.gather(*tasks)
    
    # Calcular total de tokens y filtrar resultados exitosos
    successful_results = []
    failed_results = []
    
    for result in results:
        if result["error"] is None:
            total_tokens += result["metadata"].get("token_count", 0)
            successful_results.append(result)
        else:
            failed_results.append(result)
    
    # Registrar métricas
    tenant_id = ctx.get_tenant_id() if ctx else None
    if tenant_id:
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=request.model,
            token_type="embedding",
            operation=OPERATION_BATCH,
            metadata={
                "batch_size": len(request.texts),
                "success_count": len(successful_results),
                "failure_count": len(failed_results),
                "service_origin": request.metadata.get("service_origin", "unknown") if request.metadata else "unknown"
            }
        )
    
    # Calcular tiempo total
    time_taken_ms = (time.time() - start_time) * 1000
    
    return BaseResponse(
        success=True,
        message=f"Batch completado: {len(successful_results)} éxitos, {len(failed_results)} errores",
        data={
            "embeddings": [r["embedding"] for r in successful_results],
            "failures": [{"index": r["index"], "error": r["error"]} for r in failed_results]
        },
        metadata={
            "total_tokens": total_tokens,
            "time_taken_ms": time_taken_ms,
            "success_rate": len(successful_results) / len(request.texts) if request.texts else 0
        }
    )

@router.get("/health", response_model=None)
async def health_check():
    """Endpoint de verificación de salud (puede ser público)"""
    return BaseResponse(
        success=True,
        message="Embedding Service functioning properly",
        data={"status": "ok", "version": "1.0.0"}
    )
```

### 3.2.2 Eliminar Endpoints Públicos

Se deberá verificar y eliminar cualquier endpoint público que permita acceso directo al Embedding Service que no sea `/health`. Ejemplos de endpoints a eliminar:

```python
# ENDPOINTS A ELIMINAR - No debe existir acceso público directo al Embedding Service
@router.post("/embed")  # Reemplazar por uso a través del Agent Service
@router.post("/models")  # Reemplazar por uso a través del Agent Service
@router.post("/batch-embed")  # Reemplazar por uso a través del Agent Service
```

## 3.3 Optimizar Caché

### 3.3.1 Implementación de Patrón Cache-Aside Estándar

```python
from common.cache import CacheManager, get_with_cache_aside, serialize_for_cache
import hashlib

async def get_embedding_with_cache(text: str, model: str, ctx: Context = None) -> List[float]:
    """Obtiene embedding usando el patrón Cache-Aside estándar
    
    Args:
        text: Texto para generar embedding
        model: Modelo de embedding a utilizar
        ctx: Contexto con tenant_id y otros valores
        
    Returns:
        Embedding como lista de float
        
    Raises:
        ValueError: Si el contexto es requerido pero no se proporciona
    """
    # Validar contexto
    if not ctx:
        raise ValueError("Contexto requerido para obtener embedding con caché")
        
    tenant_id = ctx.get_tenant_id()
    
    # Generar resource_id consistente
    text_hash = hashlib.md5(text.encode()).hexdigest()
    resource_id = f"{model}:{text_hash}"
    
    # Función para generar el embedding si no existe
    async def generate_embedding(resource_id, tenant_id, **kwargs):
        embedding, _ = await get_openai_embedding(
            text=text,
            model=model,
            metadata={"source": "cache_miss", **(kwargs.get("metadata", {}))},
            ctx=ctx
        )
        return embedding
    
    # Función para buscar en base de datos (opcional)
    async def fetch_embedding_from_db(resource_id, tenant_id):
        # Implementación para buscar en Supabase si se necesita...
        # En muchos casos para embeddings esto es opcional
        return None
    
    # Implementación del patrón Cache-Aside
    embedding, metrics = await get_with_cache_aside(
        data_type="embedding",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=fetch_embedding_from_db,
        generate_func=generate_embedding,
        ttl=CacheManager.ttl_extended,  # 24 horas para embeddings
        agent_id=ctx.get_agent_id() if ctx else None,
        collection_id=ctx.get_collection_id() if ctx else None,
        metadata={
            "model": model,
            "text_hash": text_hash
        }
    )
    
    return embedding
```

### 3.3.2 Optimizaciones de Serialización para Embeddings

```python
from common.cache.serializers import register_serializer

def register_embedding_serializers():
    """Registra serializadores especializados para embeddings"""
    
    @register_serializer("embedding")
    def serialize_embedding(embedding):
        """Serializa embeddings a listas Python"""
        if embedding is None:
            return None
            
        # Si es numpy array o tensor, convertir a lista
        if hasattr(embedding, "tolist"):
            return embedding.tolist()
            
        # Si ya es lista, retornar directamente
        if isinstance(embedding, list):
            return embedding
            
        # Otros casos, intentar convertir
        return list(embedding)
    
    @register_serializer("embedding_batch")
    def serialize_embedding_batch(embeddings):
        """Serializa lotes de embeddings"""
        if embeddings is None:
            return None
            
        # Convertir cada embedding a lista
        return [serialize_embedding(emb) for emb in embeddings]
```

### 3.3.3 Integración con Sistema de Métricas

```python
from common.cache.metrics import track_cache_hit, track_cache_size

async def track_embedding_cache_metrics(
    data_type: str,
    tenant_id: str,
    hit: bool,
    size_bytes: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Registra métricas específicas para caché de embeddings
    
    Args:
        data_type: Tipo de datos (embedding)
        tenant_id: ID del tenant
        hit: True si fue un acierto de cache, False si fue fallo
        size_bytes: Tamaño aproximado en bytes
        metadata: Metadatos adicionales
    """
    # Registrar acierto/fallo de caché
    await track_cache_hit(
        data_type=data_type,
        tenant_id=tenant_id,
        hit=hit,
        metadata=metadata
    )
    
    # Registrar tamaño si está disponible
    if size_bytes:
        await track_cache_size(
            data_type=data_type,
            tenant_id=tenant_id,
            size_bytes=size_bytes,
            metadata=metadata
        )
    
    # Registrar métrica especializada para dimensiones de embedding
    if metadata and "dimensions" in metadata:
        await track_performance_metric(
            metric_type="embedding_dimensions",
            value=metadata["dimensions"],
            tenant_id=tenant_id,
            metadata={
                "model": metadata.get("model", "unknown"),
                "cache_hit": hit
            }
        )
```

## Tareas Pendientes

- [ ] Mejorar tracking de tokens en `get_openai_embedding` siguiendo las prácticas recomendadas
- [ ] Implementar métricas detalladas para generación de embeddings
- [ ] Revisar y asegurar que solo existan endpoints internos (excepto /health)
- [ ] Implementar el patrón Cache-Aside estándar optimizado para embeddings
- [ ] Implementar serializadores especializados para embeddings
