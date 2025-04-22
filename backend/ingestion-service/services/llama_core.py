"""
Módulo central de LlamaIndex para ingesta y embeddings.

Este módulo centraliza todas las operaciones relacionadas con LlamaIndex,
siguiendo los patrones establecidos en las memorias del sistema para
garantizar consistencia y trazabilidad.
"""

import logging
import os
from typing import List, Dict, Any, Optional, Tuple, Union
import json
import mimetypes
import traceback

from fastapi import UploadFile

from common.errors import handle_errors, ServiceError, ErrorCode, ValidationError
from common.context import with_context, Context
from common.config import get_settings, get_tier_limits
from common.tracking import track_token_usage
from common.cache.manager import CacheManager

# Importaciones de LlamaIndex
from llama_index.core import (
    Settings, VectorStoreIndex, SimpleDirectoryReader, 
    ServiceContext, StorageContext, Document
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.supabase import SupabaseVectorStore
from llama_index.llms.openai import OpenAI

logger = logging.getLogger(__name__)
settings = get_settings()

# Configuración global de LlamaIndex
def configure_llama_index():
    """Configura LlamaIndex con los parámetros globales."""
    # Configuración de la API de OpenAI
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    
    # Configuración del embed model por defecto
    embed_model = OpenAIEmbedding(
        model=settings.default_embedding_model,
        embed_batch_size=100,  # Tamaño de batch óptimo
        dimensions=None  # Usar dimensión por defecto del modelo
    )
    
    # Configuración global de LlamaIndex
    Settings.embed_model = embed_model
    Settings.chunk_size = settings.chunk_size
    Settings.chunk_overlap = settings.chunk_overlap
    
    logger.info(f"LlamaIndex configurado con modelo de embedding: {settings.default_embedding_model}")

# Inicialización
configure_llama_index()

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def validate_file_with_llama_index(
    file: UploadFile,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Valida un archivo subido utilizando LlamaIndex para determinar si puede ser procesado.
    
    Args:
        file: Archivo subido mediante FastAPI
        ctx: Contexto de la operación
        
    Returns:
        Dict[str, Any]: Información del archivo validado incluyendo mimetype, tamaño, etc.
        
    Raises:
        ValidationError: Si el archivo no es válido por alguna razón
    """
    # Obtener contexto para errores
    error_context = {
        "service": "ingestion",
        "operation": "validate_file_llama_index",
        "file_name": file.filename
    }
    
    # Añadir información de contexto si está disponible
    if ctx:
        if ctx.has_tenant_id():
            error_context["tenant_id"] = ctx.get_tenant_id()
        if ctx.has_collection_id():
            error_context["collection_id"] = ctx.get_collection_id()
    
    # Verificar que se proporcionó un archivo
    if not file:
        raise ValidationError(
            message="No file provided",
            details={"error_code": ErrorCode.MISSING_FILE},
            context=error_context
        )
    
    # Verificar que el archivo tiene un nombre
    if not file.filename:
        raise ValidationError(
            message="File has no name",
            details={"error_code": ErrorCode.INVALID_FILENAME},
            context=error_context
        )
    
    # Detectar el tipo MIME
    mimetype = file.content_type
    
    # Lista de tipos MIME soportados por LlamaIndex
    supported_mimetypes = {
        "application/pdf": "PDFReader",
        "text/plain": "TextReader",
        "text/markdown": "MarkdownReader",
        "text/html": "HtmlReader",
        "application/json": "JSONReader",
        "text/csv": "CSVReader",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DocxReader",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PptxReader",
        "application/vnd.ms-excel": "ExcelReader",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "ExcelReader",
    }
    
    # Verificar que el mimetype es soportado
    if mimetype not in supported_mimetypes:
        raise ValidationError(
            message=f"Unsupported file type: {mimetype}",
            details={"mimetype": mimetype, "error_code": ErrorCode.UNSUPPORTED_FILE_TYPE},
            context=error_context
        )
    
    # Verificar el tamaño del archivo (límite configurable)
    max_file_size = settings.max_file_size_mb * 1024 * 1024  # Convertir MB a bytes
    
    # Intentar obtener el tamaño del archivo
    file_size = 0
    try:
        # Guardar la posición actual
        current_position = await file.tell()
        # Ir al final del archivo
        await file.seek(0, 2)  # 2 = SEEK_END
        # Obtener la posición final (tamaño)
        file_size = await file.tell()
        # Volver a la posición original
        await file.seek(current_position)
    except Exception as e:
        logger.warning(f"No se pudo determinar el tamaño del archivo: {str(e)}", 
                     extra=error_context)
    
    # Verificar si excede el tamaño máximo
    if file_size > max_file_size:
        max_size_mb = max_file_size / (1024 * 1024)
        actual_size_mb = file_size / (1024 * 1024)
        raise ValidationError(
            message=f"File too large. Maximum size is {max_size_mb:.1f} MB, but got {actual_size_mb:.1f} MB",
            details={
                "max_size_mb": max_size_mb,
                "file_size_mb": actual_size_mb,
                "error_code": ErrorCode.FILE_TOO_LARGE
            },
            context=error_context
        )
    
    # Registrar información de validación
    logger.info(f"Archivo validado con LlamaIndex: {file.filename} ({mimetype}, {file_size} bytes)", 
               extra=error_context)
    
    # Devolver información del archivo
    return {
        "filename": file.filename,
        "mimetype": mimetype,
        "file_size": file_size,
        "llama_reader": supported_mimetypes[mimetype],
        "is_valid": True
    }

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def load_and_process_file_with_llama_index(
    file_path: str,
    mimetype: str,
    metadata: Dict[str, Any],
    ctx: Context = None
) -> str:
    """
    Carga y procesa un archivo utilizando los lectores de LlamaIndex para extraer su contenido.
    
    Args:
        file_path: Ruta al archivo en el sistema de archivos
        mimetype: Tipo MIME del archivo
        metadata: Metadatos a incluir en el procesamiento
        ctx: Contexto de la operación
        
    Returns:
        str: Texto extraído del archivo
        
    Raises:
        ServiceError: Si hay un error en el procesamiento del archivo
    """
    # Información de contexto para logging y errores
    tenant_id = metadata.get("tenant_id")
    document_id = metadata.get("document_id", "unknown")
    error_context = {
        "service": "ingestion",
        "operation": "load_and_process_file_llama_index",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "mimetype": mimetype
    }
    
    try:
        logger.info(f"Procesando archivo con LlamaIndex: {file_path}", extra=error_context)
        
        # Verificar tier para funcionalidades avanzadas
        tier = "free"  # Valor por defecto
        if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
            tier = ctx.tenant_info.tier
        
        # Obtener límites del tier siguiendo el patrón de la memoria fbcc4004
        tier_limits = get_tier_limits(tier, tenant_id=tenant_id)
        has_advanced_rag = tier_limits.get("has_advanced_rag", False)
        
        # Crear un lector de SimpleDirectoryReader optimizado según el tier
        extra_info = {}
        
        # Mapeo de tipos MIME a opciones específicas de LlamaIndex
        reader_options = {}
        
        # Configuraciones específicas según tipo de archivo
        if mimetype == "application/pdf":
            # Para PDFs, usar opciones avanzadas si el tier lo permite
            if has_advanced_rag:
                reader_options = {
                    "filename_as_id": True,
                    "recursive": False,
                    "required_exts": [".pdf"],
                    "pdf_parser": "pdfminer" if has_advanced_rag else "pypdf"
                }
                extra_info["pdf_parser"] = "pdfminer"
            else:
                reader_options = {
                    "filename_as_id": True,
                    "recursive": False,
                    "required_exts": [".pdf"]
                }
        elif mimetype in ["text/csv", "application/json"]:
            # Para datos estructurados
            reader_options = {
                "filename_as_id": True,
                "recursive": False,
                "required_exts": [".csv", ".json"]
            }
        else:
            # Configuración base para otros tipos
            reader_options = {
                "filename_as_id": True,
                "recursive": False
            }
        
        # Directorio que contiene el archivo
        # Nota: SimpleDirectoryReader necesita un directorio, no un archivo individual
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        
        # Cargar el documento con LlamaIndex
        reader = SimpleDirectoryReader(
            input_dir=file_dir,
            input_files=[file_name],
            **reader_options
        )
        
        # Extraer documentos
        start_time = __import__('time').time()
        documents = reader.load_data()
        processing_time = __import__('time').time() - start_time
        
        if not documents:
            raise ServiceError(
                message="No se pudo extraer contenido del archivo",
                error_code=ErrorCode.EXTRACTION_ERROR,
                status_code=500
            )
        
        # Combinar el texto de todos los documentos
        all_text = " ".join(doc.text for doc in documents)
        
        # Registrar tokens procesados siguiendo el patrón de la memoria 05f79c43
        if tenant_id:
            # Estimar tokens procesados (aproximación)
            token_count = len(all_text.split()) * 1.3  # Aproximación de tokens
            
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=int(token_count),
                token_type="processing",
                operation="extraction",
                metadata={
                    "document_id": document_id,
                    "mimetype": mimetype,
                    "processing_time": processing_time,
                    **extra_info
                }
            )
            
        logger.info(
            f"Texto extraído con LlamaIndex: {len(all_text)} caracteres, {len(all_text.split())} palabras", 
            extra=error_context
        )
        
        return all_text
        
    except Exception as e:
        logger.error(
            f"Error procesando archivo con LlamaIndex: {str(e)}", 
            extra={**error_context, "traceback": traceback.format_exc()}
        )
        
        # Siguiendo el patrón de la memoria 5cce8e0b para manejo de errores
        if isinstance(e, ServiceError):
            raise
            
        raise ServiceError(
            message=f"Error en extracción de texto: {str(e)}",
            error_code=ErrorCode.EXTRACTION_ERROR,
            status_code=500
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def split_text_with_llama_index(
    text: str,
    document_id: str,
    metadata: Dict[str, Any],
    chunk_size: int = None,
    chunk_overlap: int = None,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Divide un texto en chunks utilizando LlamaIndex para un chunking inteligente.
    
    Args:
        text: Texto a dividir
        document_id: ID del documento
        metadata: Metadatos a incluir en cada chunk
        chunk_size: Tamaño de cada chunk
        chunk_overlap: Solapamiento entre chunks
        ctx: Contexto de la operación
        
    Returns:
        List[Dict[str, Any]]: Lista de chunks con texto y metadata
    """
    # Usar configuración proporcionada o la del sistema
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap
    
    # Verificar tier para funcionalidades avanzadas de RAG según memoria fbcc4004
    tier = "free"  # Valor por defecto
    tenant_id = metadata.get("tenant_id")
    if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
        tier = ctx.tenant_info.tier
    
    # Obtener límites del tier
    tier_limits = get_tier_limits(tier, tenant_id=tenant_id)
    has_advanced_rag = tier_limits.get("has_advanced_rag", False)
    
    # Configurar opciones avanzadas según el tier
    use_advanced_splitting = has_advanced_rag
    
    logger.info(f"Dividiendo texto para tier {tier} (RAG avanzado: {has_advanced_rag})")
    
    try:
        # Crear documento para procesamiento
        doc = Document(text=text, id_=document_id, metadata=metadata)
        
        # Configurar el sentence splitter con los parámetros especificados
        if use_advanced_splitting:
            # Usar divisor de oraciones más avanzado para tiers con RAG avanzado
            splitter = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                paragraph_separator="\n\n",
                secondary_chunking_regex=r"[^.!?]+[.!?]",
                chunk_by_paragraph_segments=True
            )
            logger.info(f"Usando chunking avanzado para documento {document_id}")
        else:
            # Usar divisor simple para tiers básicos
            splitter = SentenceSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            logger.info(f"Usando chunking básico para documento {document_id}")
        
        # Dividir el documento en nodos
        nodes = splitter.get_nodes_from_documents([doc])
        
        # Convertir nodos a formato estándar para el servicio
        chunks = []
        for i, node in enumerate(nodes):
            # Extraer texto y metadatos
            node_text = node.text
            node_metadata = {
                **metadata,
                "chunk_id": f"{document_id}_{i+1}",
                "chunk_index": i,
                "chunking_method": "llama_index_advanced" if use_advanced_splitting else "llama_index_basic"
            }
            
            chunks.append({
                "text": node_text,
                "metadata": node_metadata
            })
        
        logger.info(f"Texto dividido en {len(chunks)} fragmentos usando LlamaIndex")
        
        # Registrar procesamiento para tracking
        tenant_id = metadata.get("tenant_id") or (ctx.tenant_info.id if ctx and hasattr(ctx, 'tenant_info') else None)
        if tenant_id:
            # Estimar tokens procesados (aproximación)
            token_count = len(text.split()) * 1.3  # Aproximación de tokens
            
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=int(token_count),
                token_type="processing",
                operation="chunking",
                metadata={
                    "document_id": document_id,
                    "chunks_count": len(chunks),
                    "advanced_rag": use_advanced_splitting
                }
            )
            
        return chunks
        
    except Exception as e:
        logger.error(f"Error dividiendo texto con LlamaIndex: {str(e)}")
        raise ServiceError(
            message=f"Error en chunking con LlamaIndex: {str(e)}",
            error_code=ErrorCode.PROCESSING_ERROR,
            status_code=500
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def generate_embeddings_with_llama_index(
    texts: List[str],
    tenant_id: str,
    model_name: str = None,
    ctx: Context = None
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Genera embeddings para textos usando LlamaIndex.
    
    Args:
        texts: Lista de textos para generar embeddings
        tenant_id: ID del tenant
        model_name: Nombre del modelo de embedding
        ctx: Contexto de la operación
        
    Returns:
        Tuple[List[List[float]], Dict[str, Any]]: 
            - Lista de embeddings generados
            - Diccionario con metadatos del proceso
    """
    try:
        # Verificar tier para uso del modelo
        tier = "free"  # Valor por defecto
        if ctx and hasattr(ctx, 'tenant_info') and ctx.tenant_info:
            tier = ctx.tenant_info.tier
        
        # Usar modelo solicitado o modelo por defecto
        model_name = model_name or settings.default_embedding_model
        
        # Validar acceso al modelo según el tier siguiendo el patrón de la memoria fbcc4004
        available_models = get_available_embedding_models(tier, tenant_id)
        
        # Usar la función validate_model_access como se recomienda en la memoria fbcc4004
        from common.auth.models import validate_model_access
        if not validate_model_access(model_name, available_models):
            allowed_models = ", ".join(available_models)
            raise ServiceError(
                message=f"El modelo '{model_name}' no está disponible para el tier {tier}.",
                error_code=ErrorCode.PERMISSION_DENIED,
                details={
                    "requested_model": model_name,
                    "available_models": available_models,
                    "tier": tier
                }
            )
        
        # Crear hashes para los textos - usando método consistent con embedding-service
        import hashlib
        text_hashes = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
        
        # Generar claves de caché compatibles con embedding-service
        cache_keys = []
        embeddings_from_cache = {}
        
        # Verificar caché para cada texto individualmente
        for i, text in enumerate(texts):
            # Crear clave de caché usando el mismo formato que embedding-service
            resource_id = f"{model_name}:{text_hashes[i]}"
            
            cache_keys.append(resource_id)
            
            # Intentar obtener embedding de caché
            try:
                val = await CacheManager.get(
                    data_type="embedding",
                    resource_id=resource_id,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    search_hierarchy=True,
                    use_memory=True
                )
                if val:
                    embeddings_from_cache[i] = val
            except Exception as cache_err:
                # Solo log en debug para errores de caché
                logger.debug(f"Error al obtener embedding de caché: {str(cache_err)}")
                
        # Si todos los embeddings están en caché, devolverlos directamente
        if len(embeddings_from_cache) == len(texts):
            logger.info(f"Embeddings obtenidos de caché para {len(texts)} textos")
            embeddings = [embeddings_from_cache[i] for i in range(len(texts))]
            
            # Registrar uso desde caché (menor costo) según patrón de memoria 05f79c43
            await track_token_usage(
                tenant_id=tenant_id,
                tokens=0,  # Sin costo adicional por usar caché
                model=model_name,
                token_type="embedding",
                operation="cache_hit",
                metadata={"texts_count": len(texts)}
            )
            
            return embeddings, {"model": model_name, "cached": True}
            
        # Identificar textos que necesitan procesamiento
        texts_to_process = []
        indices_to_process = []
        
        for i, text in enumerate(texts):
            if i not in embeddings_from_cache:
                texts_to_process.append(text)
                indices_to_process.append(i)
        
        # Configurar modelo de embeddings
        embed_model = OpenAIEmbedding(
            model=model_name,
            embed_batch_size=min(len(texts_to_process), 100),  # Tamaño de batch óptimo
            api_key=settings.openai_api_key
        )
        
        # Estimar tokens para la operación
        import tiktoken
        encoder = tiktoken.encoding_for_model(model_name)
        total_tokens = sum(len(encoder.encode(text)) for text in texts_to_process)
        
        # Generar los embeddings solo para textos no cacheados
        start_time = __import__('time').time()
        
        # Método por lotes
        new_embeddings = embed_model.get_text_embedding_batch(texts_to_process)
        
        processing_time = __import__('time').time() - start_time
        
        # Registrar uso de tokens siguiendo el patrón de la memoria 05f79c43
        await track_token_usage(
            tenant_id=tenant_id,
            tokens=total_tokens,
            model=model_name,
            token_type="embedding",
            operation="generate",
            metadata={
                "texts_count": len(texts_to_process),
                "processing_time": processing_time
            }
        )
        
        # Almacenar nuevos embeddings en caché
        for idx, (i, embedding) in enumerate(zip(indices_to_process, new_embeddings)):
            resource_id = cache_keys[i]
            
            try:
                await CacheManager.set(
                    data_type="embedding",
                    resource_id=resource_id,
                    value=embedding,
                    tenant_id=tenant_id,
                    agent_id=ctx.get_agent_id() if ctx else None,
                    ttl=86400  # 24 horas
                )
            except Exception as cache_set_err:
                # Solo log en debug para errores de caché
                logger.debug(f"Error al guardar embedding en caché: {str(cache_set_err)}")
        
        # Combinar embeddings de caché y nuevos
        final_embeddings = [None] * len(texts)
        
        # Primero colocar los de caché
        for i, emb in embeddings_from_cache.items():
            final_embeddings[i] = emb
            
        # Luego colocar los nuevos
        for idx, i in enumerate(indices_to_process):
            final_embeddings[i] = new_embeddings[idx]
        
        # Metadatos del proceso
        metadata = {
            "model": model_name,
            "token_count": total_tokens,
            "texts_count": len(texts),
            "cached_count": len(embeddings_from_cache),
            "processing_time": processing_time,
            "cached": False
        }
        
        logger.info(f"Embeddings generados con LlamaIndex: {len(texts)} textos ({len(embeddings_from_cache)} de caché)")
        return final_embeddings, metadata
        
    except Exception as e:
        logger.error(f"Error generando embeddings con LlamaIndex: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        
        # Usar el decorador handle_errors que convertirá automáticamente esto
        # siguiendo el patrón de la memoria 5cce8e0b
        raise ServiceError(
            message=f"Error generando embeddings: {str(e)}",
            error_code=ErrorCode.EMBEDDING_ERROR,
            details={"model": model_name, "texts_count": len(texts)}
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def create_supabase_vector_store(
    tenant_id: str,
    collection_id: str,
    embedding_dimension: int = 1536,
    ctx: Context = None
) -> SupabaseVectorStore:
    """
    Crea o verifica un vector store en Supabase usando LlamaIndex.
    
    Args:
        tenant_id: ID del tenant
        collection_id: ID de la colección
        embedding_dimension: Dimensión de los embeddings
        ctx: Contexto de la operación
        
    Returns:
        SupabaseVectorStore: Instancia del vector store
    """
    try:
        # Obtener cliente de Supabase
        from common.db.supabase import get_supabase_client
        supabase = get_supabase_client()
        
        # Crear vector store
        table_name = "document_embeddings"
        
        vector_store = SupabaseVectorStore(
            client=supabase,
            table_name=table_name,
            tenant_column="tenant_id",
            tenant_id=tenant_id,
            collection_id=collection_id,
            dimensions=embedding_dimension
        )
        
        logger.info(f"Vector store creado/verificado para tenant={tenant_id}, collection={collection_id}")
        return vector_store
        
    except Exception as e:
        logger.error(f"Error creando vector store: {str(e)}")
        raise ServiceError(
            message=f"Error al crear/verificar vector store: {str(e)}",
            error_code=ErrorCode.STORAGE_ERROR,
            status_code=500
        )

@with_context(tenant=True)
@handle_errors(error_type="service", log_traceback=True)
async def store_chunks_in_vector_store(
    chunks: List[Dict[str, Any]],
    tenant_id: str,
    collection_id: str,
    document_id: str,
    embedding_model: str = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Almacena chunks con sus embeddings en el vector store de Supabase.
    
    Args:
        chunks: Lista de chunks con texto y metadatos
        tenant_id: ID del tenant
        collection_id: ID de la colección
        document_id: ID del documento
        embedding_model: Modelo de embeddings a utilizar
        ctx: Contexto de la operación
        
    Returns:
        Dict[str, Any]: Estadísticas del procesamiento
    """
    if not chunks:
        return {"chunks_processed": 0, "chunks_stored": 0}
    
    start_time = __import__('time').time()
    
    try:
        # 1. Generar embeddings para los chunks
        texts = [chunk["text"] for chunk in chunks]
        embeddings, metadata = await generate_embeddings_with_llama_index(
            texts=texts,
            tenant_id=tenant_id,
            model_name=embedding_model,
            ctx=ctx
        )
        
        # 2. Crear el vector store
        vector_store = await create_supabase_vector_store(
            tenant_id=tenant_id,
            collection_id=collection_id,
            ctx=ctx
        )
        
        # 3. Preparar los documentos para almacenamiento
        documents = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Asegurar que metadatos tengan los campos necesarios
            metadata = chunk["metadata"].copy()
            if "document_id" not in metadata:
                metadata["document_id"] = document_id
            if "collection_id" not in metadata:
                metadata["collection_id"] = collection_id
            if "chunk_id" not in metadata:
                metadata["chunk_id"] = f"{document_id}_{i+1}"
            if "chunk_index" not in metadata:
                metadata["chunk_index"] = i
                
            # Crear documento
            doc = Document(
                text=chunk["text"],
                id_=metadata["chunk_id"],
                metadata=metadata,
                embedding=embedding
            )
            documents.append(doc)
        
        # 4. Almacenar documentos en el vector store
        vector_store.add_documents(documents)
        
        # 5. Calcular estadísticas
        processing_time = __import__('time').time() - start_time
        stored_count = len(documents)
        
        # 6. Invalidar caché para esta colección
        cache_manager = CacheManager()
        cache_key = f"vectorstore:{tenant_id}:{collection_id}"
        await cache_manager.delete(cache_key)
        
        stats = {
            "chunks_processed": len(chunks),
            "chunks_stored": stored_count,
            "embedding_model": metadata.get("model"),
            "processing_time": processing_time,
            "average_chunk_length": sum(len(c["text"]) for c in chunks) / len(chunks)
        }
        
        logger.info(f"Procesados {stored_count} fragmentos en {processing_time:.2f}s con LlamaIndex")
        return stats
        
    except Exception as e:
        logger.error(f"Error procesando y almacenando fragmentos con LlamaIndex: {str(e)}")
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(
            message=f"Error procesando y almacenando fragmentos: {str(e)}",
            error_code=ErrorCode.EMBEDDING_STORAGE_ERROR,
            details={
                "document_id": document_id,
                "collection_id": collection_id,
                "chunks_count": len(chunks) if chunks else 0
            }
        )

# Importar funciones de obtención de modelos según tier
from common.config.tiers import get_available_embedding_models
