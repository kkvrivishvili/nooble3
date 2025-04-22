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
from common.context import with_context, Context
from common.errors import (
    ErrorCode,
    ServiceError, 
    QueryProcessingError, CollectionNotFoundError, 
    RetrievalError, GenerationError, InvalidQueryParamsError,
    EmbeddingGenerationError, EmbeddingModelError, TextTooLargeError
)
from common.tracking import track_token_usage, estimate_prompt_tokens
from common.llm.token_counters import count_tokens
from common.models import TenantInfo
from common.cache import (
    get_with_cache_aside,
    generate_resource_id_hash
)

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
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Procesa una consulta y devuelve la respuesta con fuentes.
    
    Implementa el patrón Cache-Aside centralizado para optimizar la recuperación
    de resultados previamente calculados para la misma consulta.
    
    Args:
        query_engine: Motor de consulta configurado
        debug_handler: Handler para depuración
        query: Consulta a procesar
        filters: Filtros adicionales (opcional)
        similarity_top_k: Número de documentos a recuperar
        response_mode: Modo de respuesta (compact, verbose, etc.)
        ctx: Contexto de la consulta
        
    Returns:
        Dict[str, Any]: Resultado procesado con respuesta y fuentes
    """
    # Acceder de forma segura al contexto
    tenant_id = ctx.get_tenant_id() if ctx else None
    collection_id = ctx.get_collection_id() if ctx else None
    agent_id = ctx.get_agent_id() if ctx else None
    
    if not tenant_id:
        raise ValueError("Se requiere tenant_id para procesar la consulta")
        
    if not collection_id:
        raise ValueError("Se requiere collection_id para procesar la consulta")
    
    # Generar un identificador único para esta consulta
    query_hash = generate_resource_id_hash(f"{query}_{similarity_top_k}_{response_mode}")
    resource_id = f"{collection_id}:{query_hash}"
    
    # Función para ejecutar la consulta si no está en caché
    async def execute_query(resource_id, tenant_id, ctx):
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
            
            # Tracking de tokens directamente usando la función centralizada
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=tokens_total,
                model=model_used,
                agent_id=agent_id,
                conversation_id=None,
                collection_id=collection_id,
                token_type="llm",
                operation="query",
                metadata={
                    "query": query,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "elapsed_time": time.time() - start_time
                }
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
                "processing_time": processing_time,
                "query": query,
                "similarity_top_k": similarity_top_k,
                "response_mode": response_mode
            }
            
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
    
    # Usar la implementación centralizada del patrón Cache-Aside
    # No necesitamos función de fetch_from_db, ya que los resultados de consulta
    # no se almacenan en Supabase
    result, metrics = await get_with_cache_aside(
        data_type="query_result",
        resource_id=resource_id,
        tenant_id=tenant_id,
        fetch_from_db_func=lambda *args: None,  # No buscar en DB para resultados de consulta
        generate_func=execute_query,
        agent_id=agent_id,
        collection_id=collection_id,
        ctx=ctx
    )
    
    # Si tenemos contexto, añadir métricas para análisis
    if ctx:
        ctx.add_metric("query_cache_metrics", metrics)
    
    return result


@with_context(tenant=True, collection=True, agent=True)
async def create_query_engine(
    tenant_info=None,
    collection_id: Optional[str] = None,
    llm_model: Optional[str] = None,
    similarity_top_k: int = 4,
    response_mode: str = "compact",
    ctx: Context = None
) -> Tuple[RetrieverQueryEngine, LlamaDebugHandler]:
    """
    Crea un motor de consulta para una colección específica.
    
    Args:
        tenant_info: Información del tenant (opcional, se puede obtener del contexto)
        collection_id: ID de la colección (opcional, se puede obtener del contexto)
        llm_model: Modelo de lenguaje a utilizar (opcional)
        similarity_top_k: Número de documentos a recuperar
        response_mode: Modo de respuesta (compact, verbose, etc.)
        ctx: Contexto de la consulta proporcionado por el decorador
        
    Returns:
        Tuple[RetrieverQueryEngine, LlamaDebugHandler]: Motor de consulta y handler de debug
        
    Raises:
        CollectionNotFoundError: Si la colección no existe
        EmbeddingGenerationError: Si hay problemas generando embeddings
        RetrievalError: Si hay problemas recuperando documentos
    """
    # Obtener tenant_id y collection_id del contexto si no se proporcionan
    tenant_id = None
    if tenant_info:
        tenant_id = tenant_info.tenant_id
    elif ctx:
        tenant_id = ctx.get_tenant_id()
    
    if not tenant_id:
        raise ValueError("Se requiere tenant_id para crear el motor de consulta")
        
    if not collection_id and ctx:
        collection_id = ctx.get_collection_id()
        
    if not collection_id:
        raise ValueError("Se requiere collection_id para crear el motor de consulta")
    
    from services.vector_store import get_vector_store_for_collection
    from services.llm import get_llm_for_tenant
    from common.llm.llamaindex import create_response_synthesizer
    
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
            
            # Crear tenant_info si no existe
            if not tenant_info:
                tenant_info = TenantInfo(tenant_id=tenant_id)
                
            llm = await get_llm_for_tenant(tenant_info, model_name, ctx)
            
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
            
        except Exception as e:
            logger.error(f"Error configurando LLM: {str(e)}")
            raise GenerationError(
                message=f"Error configurando modelo de generación: {str(e)}",
                details={"model": model_name, "error_details": str(e)}
            )
            
    except Exception as e:
        if isinstance(e, (CollectionNotFoundError, RetrievalError, GenerationError)):
            raise
            
        logger.error(f"Error creando motor de consulta: {str(e)}")
        raise ServiceError(
            message=f"Error creando motor de consulta: {str(e)}",
            error_code=ErrorCode.QUERY_ENGINE_ERROR,
            details={"collection_id": collection_id, "tenant_id": tenant_id}
        )