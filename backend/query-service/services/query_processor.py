"""
Procesador de consultas RAG simplificado.
"""

import logging
import time
from typing import Dict, List, Any, Optional

from models.query import DocumentMatch
from provider.groq import GroqLLM
from services.vector_store import search_by_embedding
from config.settings import get_settings
from common.tracking import track_token_usage, TOKEN_TYPE_LLM, OPERATION_QUERY

logger = logging.getLogger(__name__)
settings = get_settings()

async def process_rag_query(
    query: str,
    query_embedding: List[float],
    tenant_id: str,
    collection_id: str,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    similarity_top_k: int = 4,
    llm_model: Optional[str] = None,
    include_sources: bool = True,
    agent_description: Optional[str] = None,
    fallback_behavior: str = "agent_knowledge",
    relevance_threshold: float = 0.75
) -> Dict[str, Any]:
    """
    Procesa consulta RAG con embedding pre-calculado y manejo de fallback inteligente.
    
    Args:
        query: Texto de la consulta
        query_embedding: Embedding del query (desde Embedding Service)
        tenant_id: ID del tenant
        collection_id: ID de la colección
        agent_id: ID del agente (opcional)
        conversation_id: ID de la conversación (opcional)
        similarity_top_k: Número de documentos similares
        llm_model: Modelo LLM a usar
        include_sources: Si incluir fuentes en respuesta
        agent_description: Descripción del agente para casos de fallback
        fallback_behavior: Estrategia para casos sin resultados relevantes
        relevance_threshold: Umbral para considerar documentos realmente relevantes
        
    Returns:
        Dict con respuesta y metadatos
    """
    start_time = time.time()
    
    # 1. Buscar documentos similares
    logger.info(f"Buscando documentos similares en colección {collection_id}")
    similar_docs = await search_by_embedding(
        tenant_id=tenant_id,
        collection_id=collection_id,
        query_embedding=query_embedding,
        top_k=similarity_top_k,
        threshold=settings.similarity_threshold
    )
    
    # 2. Determinar si hay documentos realmente relevantes
    has_relevant_docs = False
    source_quality = "none"
    
    if similar_docs:
        # Verificar si al menos un documento supera el umbral de relevancia estricto
        has_relevant_docs = any(doc['similarity'] > relevance_threshold for doc in similar_docs)
        
        if has_relevant_docs:
            source_quality = "high"
        else:
            source_quality = "low"
            logger.info(f"Documentos encontrados pero por debajo del umbral de relevancia ({relevance_threshold})")
    else:
        logger.warning("No se encontraron documentos similares")
    
    # 3. Preparar fuentes para incluir en respuesta si es necesario
    sources = []
    if include_sources and similar_docs:
        for i, doc in enumerate(similar_docs[:similarity_top_k]):
            sources.append({
                "content": doc['content'][:500] + "..." if len(doc['content']) > 500 else doc['content'],
                "metadata": doc['metadata'],
                "similarity": doc['similarity']
            })
    
    # 4. Determinar comportamiento según disponibilidad de información
    if not similar_docs and fallback_behavior == "reject_query":
        # Caso 1: No hay documentos y política es rechazar
        return {
            "response": "No dispongo de información para responder a esta pregunta.",
            "sources": [],
            "metadata": {
                "found_documents": 0,
                "processing_time": time.time() - start_time,
                "source_quality": source_quality
            }
        }
    
    # 5. Construir prompt y system prompt según escenario
    system_prompt = """"""
    prompt = """"""
    
    if not similar_docs:
        # Caso 2: No hay documentos pero usamos conocimiento del agente
        system_prompt = f"""Eres un asistente útil que representa a un agente. 
        {agent_description or 'Tu objetivo es proporcionar información precisa y útil.'}
        Si no puedes responder con confianza, indícalo claramente."""
        
        prompt = f"Pregunta: {query}\n\nResponde según tu conocimiento sobre el propósito y funcionalidad del agente."
        
    elif not has_relevant_docs:
        # Caso 3: Hay documentos pero no son suficientemente relevantes
        system_prompt = f"""Eres un asistente útil que representa a un agente.
        {agent_description or 'Tu objetivo es proporcionar información precisa y útil.'}
        Se te ha proporcionado algo de contexto, pero no parece directamente relevante a la pregunta.
        Responde basándote principalmente en tu conocimiento general sobre el agente.
        Si no puedes responder con confianza, indícalo claramente."""
        
        # Incluimos el contexto de todas formas, pero indicamos que podría no ser muy relevante
        context = "\n".join(f"[Documento {i+1}]:\n{doc['content']}\n" for i, doc in enumerate(similar_docs[:similarity_top_k]))
        prompt = f"""Contexto (posiblemente no directamente relevante):
{context}

Pregunta: {query}

Responde basándote principalmente en tu conocimiento del agente, usando el contexto solo si es útil:"""
        
    else:
        # Caso 4: Hay documentos relevantes (flujo normal RAG)
        system_prompt = """Eres un asistente útil que responde preguntas basándose ÚNICAMENTE en el contexto proporcionado. 
Si la información no está en el contexto, di que no tienes esa información."""
        
        # Construir contexto como lo hacemos actualmente
        context_parts = []
        for i, doc in enumerate(similar_docs[:similarity_top_k]):
            context_parts.append(f"[Documento {i+1}]:\n{doc['content']}\n")
        
        context = "\n".join(context_parts)
        prompt = f"""Contexto:
{context}

Pregunta: {query}

Responde basándote SOLO en el contexto anterior:"""
    
    # 6. Generar respuesta con Groq
    llm = GroqLLM(model=llm_model)
    response = await llm.generate(
        prompt=prompt,
        system_prompt=system_prompt
    )
    
    # 7. Registrar uso de tokens (pendiente implementación completa)
    # await track_token_usage(...)
    
    # 8. Preparar respuesta
    processing_time = time.time() - start_time
    
    return {
        "response": response,
        "sources": sources if include_sources else [],
        "metadata": {
            "model": llm.model,
            "found_documents": len(similar_docs) if similar_docs else 0,
            "used_documents": min(similarity_top_k, len(similar_docs)) if similar_docs else 0,
            "processing_time": processing_time,
            "source_quality": source_quality,
            "avg_similarity": sum(d['similarity'] for d in similar_docs) / len(similar_docs) if similar_docs else 0.0
        }
    }

async def search_documents(
    query_embedding: List[float],
    tenant_id: str,
    collection_id: str,
    limit: int = 5,
    threshold: float = 0.7
) -> List[DocumentMatch]:
    """
    Busca documentos sin generar respuesta.
    
    Args:
        query_embedding: Embedding para búsqueda
        tenant_id: ID del tenant
        collection_id: ID de la colección
        limit: Número máximo de resultados
        threshold: Umbral de similitud
        
    Returns:
        Lista de documentos encontrados
    """
    docs = await search_by_embedding(
        tenant_id=tenant_id,
        collection_id=collection_id,
        query_embedding=query_embedding,
        top_k=limit,
        threshold=threshold
    )
    
    return [
        DocumentMatch(
            id=doc['id'],
            content=doc['content'],
            metadata=doc['metadata'],
            similarity=doc['similarity']
        )
        for doc in docs
    ]
