import logging
import time
from typing import Dict, List, Any, Optional, Union, Tuple

from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManager
from langchain_core.output_parsers import StrOutputParser
from langchain.chains.query_constructor.base import QueryConstructorChain
from langchain.schema import Document
from langchain.retrievers import RetrieverQueryEngine
from llama_index.callbacks import LlamaDebugHandler

from common.config import get_settings
from common.context import with_context
from common.errors import (
    ErrorCode, ServiceError, 
    QueryProcessingError, CollectionNotFoundError, 
    RetrievalError, GenerationError, InvalidQueryParamsError,
    EmbeddingGenerationError, EmbeddingModelError, TextTooLargeError
)
from common.tracking import track_token_usage
from common.llm.token_counters import count_tokens
from common.cache.manager import CacheManager

logger = logging.getLogger(__name__)

class QueryContextItem:
    """Estructura para almacenar items de contexto de consulta con metadatos."""
    
    def __init__(self, text: str, metadata: Dict[str, Any], score: float = 0.0):
        self.text = text
        self.metadata = metadata
        self.score = score
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata,
            "score": self.score
        }


@with_context(tenant=True, collection=True, agent=True)
async def process_query_with_sources(
    query_engine: RetrieverQueryEngine,
    debug_handler: LlamaDebugHandler,
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    similarity_top_k: int = 4,
    response_mode: str = "compact",
    ctx=None
) -> Dict[str, Any]:
    """Procesa una consulta y devuelve la respuesta con fuentes."""
    
    tenant_id = ctx.get_tenant_id()
    collection_id = ctx.get_collection_id()
    agent_id = ctx.get_agent_id()
    
    # Verificar caché primero con manejo de errores
    try:
        cached_result = await CacheManager.get_query_result(
            query=query,
            collection_id=collection_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            similarity_top_k=similarity_top_k,
            response_mode=response_mode
        )
        if cached_result:
            logger.info(f"Resultado de consulta obtenido de caché para '{query[:30]}...'")
            return cached_result
    except Exception as cache_err:
        logger.debug(f"Error accediendo a caché de consulta: {str(cache_err)}")
    
    try:
        start_time = time.time()
        
        # Ejecutar consulta
        query_result = await query_engine.aquery(query)
        
        # Extraer respuesta
        response = query_result.response
        
        # Calcular tokens aproximados
        model_used = getattr(query_result, "model", "unknown")
        if not model_used or model_used == "unknown":
            # Intentar extraer del LLM
            try:
                model_used = query_engine.response_synthesizer.llm.model_name
            except:
                # Usar el modelo por defecto si no podemos extraerlo
                model_used = get_settings().default_llm_model
        
        tokens_in = count_tokens(query, model_name=model_used)
        tokens_out = count_tokens(response, model_name=model_used)
        tokens_total = tokens_in + tokens_out
        
        # Tracking de tokens async
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=tokens_total,
            model=model_used,
            collection_id=collection_id,
            token_type="rag"
        )
        
        # Extraer fuentes si están disponibles
        sources = []
        try:
            for node_with_score in query_result.source_nodes:
                source_text = node_with_score.node.get_content()
                source_meta = node_with_score.node.metadata.copy()
                source_score = node_with_score.score
                
                # Limpiar metadatos (opcional)
                if "embedding" in source_meta:
                    del source_meta["embedding"]
                
                # Agregar a fuentes
                sources.append(
                    QueryContextItem(
                        text=source_text[:500] + "..." if len(source_text) > 500 else source_text,
                        metadata=source_meta,
                        score=source_score
                    ).to_dict()
                )
        except Exception as e:
            logger.warning(f"Error extrayendo fuentes: {str(e)}")
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Construir resultado final
        result = {
            "response": response,
            "sources": sources,
            "model": model_used,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_total": tokens_total,
            "processing_time": processing_time
        }
        
        # Guardar en caché (1 hora) con manejo de errores
        try:
            await CacheManager.set_query_result(
                query=query,
                result=result,
                collection_id=collection_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                similarity_top_k=similarity_top_k,
                response_mode=response_mode,
                ttl=3600
            )
        except Exception as cache_set_err:
            logger.debug(f"Error guardando resultado de consulta en caché: {str(cache_set_err)}")
        
        return result
    
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}")
        raise QueryProcessingError(
            message=f"Error procesando consulta: {str(e)}",
            details={
                "query": query,
                "filters": filters,
                "similarity_top_k": similarity_top_k,
                "response_mode": response_mode
            }
        )


@with_context(tenant=True, collection=True, agent=True)
async def create_query_engine(
    ctx=None,
    llm_model: Optional[str] = None,
    similarity_top_k: int = 4,
    response_mode: str = "compact"
) -> Tuple[RetrieverQueryEngine, LlamaDebugHandler]:
    """
    Crea un motor de consulta para una colección específica.
    
    Args:
        ctx: Contexto de la consulta
        llm_model: Modelo de lenguaje a utilizar (opcional)
        similarity_top_k: Número de documentos a recuperar
        response_mode: Modo de respuesta (compact, verbose, etc.)
        
    Returns:
        Tuple[RetrieverQueryEngine, LlamaDebugHandler]: Motor de consulta y handler de debug
        
    Raises:
        CollectionNotFoundError: Si la colección no existe
        EmbeddingGenerationError: Si hay problemas generando embeddings
        RetrievalError: Si hay problemas recuperando documentos
    """
    from services.vector_store import get_vector_store_for_collection
    from services.llm import get_llm_for_model
    from common.llm.llamaindex import create_response_synthesizer
    
    tenant_id = ctx.get_tenant_id()
    collection_id = ctx.get_collection_id()
    settings = get_settings()
    
    try:
        # Crear handler para debugging y tracking
        debug_handler = LlamaDebugHandler()
        callback_manager = CallbackManager([debug_handler])
        
        # Obtener vector store para la colección
        vector_store = await get_vector_store_for_collection(
            tenant_id=tenant_id,
            collection_id=collection_id
        )
        
        if not vector_store:
            logger.error(f"Vector store no encontrado para colección {collection_id}")
            raise CollectionNotFoundError(
                message=f"Colección no encontrada: {collection_id}",
                details={"tenant_id": tenant_id, "collection_id": collection_id}
            )
        
        # Crear retriever a partir del vector store
        try:
            retriever = vector_store.as_retriever(
                search_kwargs={"k": similarity_top_k}
            )
        except Exception as e:
            logger.error(f"Error creando retriever: {str(e)}")
            raise RetrievalError(
                message=f"Error configurando sistema de recuperación: {str(e)}",
                details={"collection_id": collection_id, "error_details": str(e)}
            )
        
        # Configurar el LLM para generar respuestas
        try:
            # Si no se especifica modelo, usar el default
            model_name = llm_model if llm_model else settings.default_llm_model
            llm = get_llm_for_model(model_name)
            
            # Crear sintetizador de respuestas
            response_synthesizer = create_response_synthesizer(
                llm=llm,
                response_mode=response_mode,
                callback_manager=callback_manager
            )
            
            # Crear motor de consulta
            query_engine = RetrieverQueryEngine(
                retriever=retriever,
                response_synthesizer=response_synthesizer,
                callback_manager=callback_manager
            )
            
            return query_engine, debug_handler
            
        except EmbeddingGenerationError as e:
            # Re-propagar errores específicos de embedding
            logger.error(f"Error de embedding al crear motor de consulta: {e.message}")
            raise
        
        except EmbeddingModelError as e:
            # Re-propagar errores específicos del modelo de embedding
            logger.error(f"Error de modelo de embedding al crear motor de consulta: {e.message}")
            raise
        
        except TextTooLargeError as e:
            # Re-propagar errores de texto demasiado grande
            logger.error(f"Texto demasiado grande para embeddings: {e.message}")
            raise
        
        except Exception as e:
            # Convertir otros errores a tipo específico
            if "llm" in str(e).lower() or "lenguaje" in str(e).lower():
                logger.error(f"Error con modelo LLM: {str(e)}")
                raise GenerationError(
                    message=f"Error con modelo de lenguaje: {str(e)}",
                    details={"model": model_name, "error_details": str(e)}
                )
            else:
                logger.error(f"Error creando motor de consulta: {str(e)}")
                raise QueryProcessingError(
                    message=f"Error configurando motor de consulta: {str(e)}",
                    details={
                        "collection_id": collection_id,
                        "model": model_name if 'model_name' in locals() else None,
                        "similarity_top_k": similarity_top_k,
                        "response_mode": response_mode
                    }
                )
    
    except (CollectionNotFoundError, RetrievalError, EmbeddingGenerationError, 
            EmbeddingModelError, TextTooLargeError, GenerationError):
        # Re-propagar errores específicos
        raise
    
    except Exception as e:
        logger.error(f"Error inesperado creando motor de consulta: {str(e)}")
        raise QueryProcessingError(
            message=f"Error inesperado configurando motor de consulta: {str(e)}",
            details={"collection_id": collection_id}
        )