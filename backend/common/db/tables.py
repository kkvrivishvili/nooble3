"""
Funciones para acceso a tablas y estructuras de datos en Supabase.
"""

import logging
from typing import Dict, Any, List, Optional, Set, Union

from .supabase import get_supabase_client
from ..config.settings import get_settings
from ..context.vars import get_current_tenant_id, validate_tenant_context
from ..errors.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Definición de esquemas y tablas con sus descripciones
TABLE_SCHEMA_MAP = {
    # Schema: public - Tablas de autenticación y gestión de usuarios
    "public": {
        "tenants": "Información de tenants y su estado",
        "users": "Usuarios del sistema",
        "auth": "Información de autenticación",
        "public_sessions": "Sesiones públicas no autenticadas"
    },
    
    # Schema: ai - Tablas específicas de la plataforma AI
    "ai": {
        "tenant_configurations": "Configuraciones específicas por tenant",
        "tenant_subscriptions": "Suscripciones y planes de tenants",
        "tenant_stats": "Estadísticas de uso de tenants",
        "agent_configs": "Configuraciones de agentes",
        "conversations": "Conversaciones con agentes",
        "chat_history": "Historial de mensajes de chat",
        "chat_feedback": "Feedback sobre respuestas de chat",
        "collections": "Colecciones de documentos",
        "document_chunks": "Fragmentos de documentos con embeddings",
        "agent_collections": "Relación entre agentes y colecciones",
        "embedding_metrics": "Métricas de uso de embeddings",
        "query_logs": "Logs de consultas realizadas",
        "user_preferences": "Preferencias de usuario"
    }
}

# Crear conjunto de tablas por esquema para búsquedas rápidas
PUBLIC_TABLES: Set[str] = set(TABLE_SCHEMA_MAP["public"].keys())
AI_TABLES: Set[str] = set(TABLE_SCHEMA_MAP["ai"].keys())

def get_table_name(table_base_name: str) -> str:
    """
    Retorna el nombre completo de la tabla con el prefijo de esquema correcto.
    
    Esta función centraliza la obtención de nombres de tablas para 
    mantener consistencia en todas las referencias a la base de datos.
    
    Args:
        table_base_name: Nombre base de la tabla sin prefijo
        
    Returns:
        str: Nombre completo de la tabla con prefijo adecuado
    """
    # Si ya tiene prefijo, devolverlo tal cual
    if "." in table_base_name:
        return table_base_name
    
    # Determinar esquema adecuado
    if table_base_name in PUBLIC_TABLES:
        return f"public.{table_base_name}"
    
    if table_base_name in AI_TABLES:
        return f"ai.{table_base_name}"
    
    # Por defecto, asumir esquema ai para evitar errores
    logger.warning(f"Tabla '{table_base_name}' no está en lista conocida. Usando esquema 'ai' por defecto.")
    return f"ai.{table_base_name}"

def get_table_description(table_base_name: str) -> str:
    """
    Obtiene la descripción de una tabla para documentación.
    
    Args:
        table_base_name: Nombre base de la tabla sin prefijo
        
    Returns:
        str: Descripción de la tabla o cadena vacía si no se encuentra
    """
    # Determinar esquema y buscar descripción
    if table_base_name in PUBLIC_TABLES:
        return TABLE_SCHEMA_MAP["public"].get(table_base_name, "")
    
    if table_base_name in AI_TABLES:
        return TABLE_SCHEMA_MAP["ai"].get(table_base_name, "")
    
    return ""

def get_tenant_vector_store(tenant_id: Optional[str] = None, collection_id: Optional[str] = None) -> Any:
    """
    Obtiene un vector store para un tenant específico.
    
    Requiere importación de LlamaIndex para el tipo SupabaseVectorStore,
    pero como esa dependencia no es requerida por el módulo común,
    usamos Any como tipo de retorno.
    
    Args:
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        collection_id: ID único de la colección (UUID)
        
    Returns:
        Any: Vector store para el tenant especificado
        
    Raises:
        ServiceError: Si no hay un tenant válido en el contexto cuando se omite tenant_id
    """
    # Si no se proporciona tenant_id, obtener del contexto y validar
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
        tenant_id = validate_tenant_context(tenant_id)
        
    try:
        from llama_index.vector_stores.supabase import SupabaseVectorStore
    except ImportError:
        logger.error("No se pudo importar SupabaseVectorStore desde llama_index.vector_stores.supabase. "
                      "Asegúrate de tener llama_index instalado.")
        raise ImportError("Dependencia requerida 'llama_index' no está instalada.")
    
    supabase = get_supabase_client()
    
    # Configurar filtros de metadatos
    metadata_filters = {"tenant_id": tenant_id}
    
    # Filtrar por collection_id si se proporciona
    if collection_id:
        metadata_filters["collection_id"] = str(collection_id)
    
    # Crear vector store
    vector_store = SupabaseVectorStore(
        client=supabase,
        table_name=get_table_name("document_chunks"),
        content_field="content",
        embedding_field="embedding",
        metadata_field="metadata",
        metadata_filters=metadata_filters
    )
    
    return vector_store

def get_tenant_documents(
    tenant_id: Optional[str] = None, 
    collection_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Obtiene los documentos para un tenant específico.
    
    Args:
        tenant_id: ID del tenant (opcional, usa el contexto actual si no se especifica)
        collection_id: Filtrar por ID único de colección (UUID)
        limit: Límite de resultados
        offset: Desplazamiento para paginación
        
    Returns:
        Dict[str, Any]: Documentos y metadatos de paginación
        
    Raises:
        ServiceError: Si no hay un tenant válido en el contexto cuando se omite tenant_id
    """
    # Si no se proporciona tenant_id, obtener del contexto y validar
    if tenant_id is None:
        tenant_id = get_current_tenant_id()
        tenant_id = validate_tenant_context(tenant_id)
    
    supabase = get_supabase_client()
    
    # Query base
    query = supabase.table(get_table_name("document_chunks")).select("metadata")
    
    # Añadir filtros
    query = query.eq("tenant_id", tenant_id)
    
    # Filtrar por collection_id si se proporciona
    if collection_id:
        query = query.filter("metadata->collection_id", "eq", str(collection_id))
    
    # Ejecutar query
    result = query.execute()
    
    if not result.data:
        return {
            "documents": [],
            "total": 0,
            "limit": limit,
            "offset": offset
        }
    
    # Extraer IDs de documento únicos
    document_map = {}
    for chunk in result.data:
        metadata = chunk["metadata"]
        if "document_id" in metadata:
            doc_id = metadata["document_id"]
            if doc_id not in document_map:
                # Extraer metadatos del documento
                doc_info = {
                    "document_id": doc_id,
                    "source": metadata.get("source", "Unknown"),
                    "author": metadata.get("author"),
                    "document_type": metadata.get("document_type"),
                    "collection": metadata.get("collection", "default"),
                    "created_at": metadata.get("created_at")
                }
                document_map[doc_id] = doc_info
    
    # Convertir a lista y aplicar paginación
    documents = list(document_map.values())
    total = len(documents)
    paginated_documents = documents[offset:offset+limit]
    
    return {
        "documents": paginated_documents,
        "total": total,
        "limit": limit,
        "offset": offset
    }

def get_tenant_collections(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene las colecciones para un tenant específico con recuento de documentos.
    
    Utiliza la función RPC get_collection_document_counts para obtener el recuento
    de documentos de forma eficiente, siguiendo el estándar de acceso a datos.
    
    Args:
        tenant_id: ID del tenant
        
    Returns:
        List[Dict[str, Any]]: Lista de colecciones con estadísticas
    """
    supabase = get_supabase_client()
    
    # Query para obtener colecciones desde la tabla collections
    collections_query = supabase.table(get_table_name("collections")).select("collection_id", "name", "description", "created_at", "updated_at")
    collections_query = collections_query.eq("tenant_id", tenant_id)
    collections_result = collections_query.execute()
    
    if not collections_result.data:
        return []
    
    # Extraer IDs de colecciones para uso en mapeo
    collection_ids = [collection.get("collection_id") for collection in collections_result.data]
    collection_map = {collection.get("collection_id"): collection for collection in collections_result.data}
    
    # Obtener recuentos de documentos usando la función RPC centralizada
    document_counts_result = supabase.rpc(
        "get_collection_document_counts",
        {
            "p_tenant_id": tenant_id,
            "p_collection_ids": collection_ids
        }
    ).execute()
    
    # Mapear recuentos de documentos por collection_id
    document_counts = {}
    if document_counts_result.data:
        for count_record in document_counts_result.data:
            collection_id = count_record.get("collection_id")
            count = count_record.get("document_count")
            document_counts[collection_id] = count or 0
    
    # Preparar estadísticas para cada colección
    collection_stats = []
    for collection_id in collection_ids:
        collection = collection_map.get(collection_id)
        collection_stats.append({
            "collection_id": collection_id,
            "name": collection.get("name"),
            "description": collection.get("description"),
            "document_count": document_counts.get(collection_id, 0),
            "created_at": collection.get("created_at"),
            "updated_at": collection.get("updated_at")
        })
    
    return collection_stats