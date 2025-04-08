# Actualización de query-service/services/query_engine.py para usar QueryResultCache

# En la función process_query_with_sources, añadir caché de resultados:

from common.cache.specialized import QueryResultCache

@with_context(tenant=True, collection=True)
async def process_query_with_sources(
    query_engine: RetrieverQueryEngine,
    debug_handler: LlamaDebugHandler,
    query: str,
    filters: Optional[Dict[str, Any]] = None
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
        agent_id=agent_id
    )
    
    if cached_result:
        logger.info(f"Resultado de consulta obtenido de caché para '{query[:30]}...'")
        return cached_result
    
    try:
        # Ejecutar consulta
        query_result = await query_engine.aquery(query)
        
                # Extraer respuesta
        response = query_result.response
        
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
                    )
                )
        except Exception as e:
            logger.warning(f"Error extrayendo fuentes: {str(e)}")
        
        # Obtener modelo usado
        model_used = getattr(query_result, "model", "unknown")
        if not model_used or model_used == "unknown":
            # Intentar extraer del LLM
            try:
                model_used = query_engine.response_synthesizer.llm.model_name
            except:
                # Usar el modelo por defecto si no podemos extraerlo
                model_used = get_settings().default_llm_model
        
        # Construir resultado final
        result = {
            "response": response,
            "sources": sources,
            "model": model_used,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_total": tokens_total
        }
        
        # Guardar en caché (1 hora)
        await QueryResultCache.set(
            query=query,
            result=result,
            collection_id=collection_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            ttl=3600
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Error procesando consulta: {str(e)}")
        raise ServiceError(
            message=f"Error procesando consulta: {str(e)}",
            error_code="QUERY_PROCESSING_ERROR"
        )