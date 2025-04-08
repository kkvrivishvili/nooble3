import logging
import time
from typing import Dict, List, Any, Optional, Union

from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManager
from langchain_core.output_parsers import StrOutputParser
from langchain.chains.query_constructor.base import QueryConstructorChain
from langchain.schema import Document
from langchain.retrievers import RetrieverQueryEngine
from llamaindex.callbacks import LlamaDebugHandler

from common.config import get_settings
from common.context import with_context, get_current_tenant_id, get_current_collection_id, get_current_agent_id
from common.errors import ServiceError
from common.tracking import track_token_usage
from common.llm.token_counters import count_tokens
from common.cache.specialized import QueryResultCache

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


@with_context(tenant=True, collection=True)
async def process_query_with_sources(
    query_engine: RetrieverQueryEngine,
    debug_handler: LlamaDebugHandler,
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    similarity_top_k: int = 4,
    response_mode: str = "compact"
) -> Dict[str, Any]:
    """Procesa una consulta y devuelve la respuesta con fuentes."""
    
    tenant_id = get_current_tenant_id()
    collection_id = get_current_collection_id()
    agent_id = get_current_agent_id()
    
    # Verificar caché primero
    cached_result = await QueryResultCache.get(
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
        
        # Guardar en caché (1 hora)
        await QueryResultCache.set(
            query=query,
            result=result,
            collection_id=collection_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            similarity_top_k=similarity_top_k,
            response_mode=response_mode,
            ttl=3600
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}")
        raise ServiceError(
            message=f"Error procesando consulta: {str(e)}",
            error_code="QUERY_PROCESSING_ERROR",
            status_code=500
        )