"""
Tracking unificado de tokens, queries y embeddings.
"""
import time
import uuid
import logging
import json
import hashlib
import random
import asyncio
from typing import Dict, Any, List, Optional
import re
import importlib
import logging

# Reemplazar la dependencia de common/llm con un sistema dinámico
# que detecta el contador de tokens adecuado según el servicio

# Usamos solo las importaciones necesarias sin crear ciclos
from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
# La función increment_token_usage ha sido eliminada y reemplazada por la implementación en este mismo archivo
from ..config import get_settings
from ..config.tiers import get_tier_rate_limit
from ..context.vars import get_current_tenant_id, get_current_agent_id, get_current_conversation_id

logger = logging.getLogger(__name__)

async def track_token_usage(
    tenant_id: Optional[str] = None,
    tokens: int = 0,
    model: Optional[str] = None,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    token_type: str = "llm",
    operation: str = "query",
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None
) -> bool:
    if tokens <= 0:
        return True
    # Obtener configuración con manejo de errores
    try:
        settings = get_settings()
        if not settings.enable_usage_tracking:
            logger.debug(f"Tracking deshabilitado, omitiendo {tokens} tokens")
            return True
    except Exception as config_err:
        logger.debug(f"Error obteniendo configuración, asumiendo tracking habilitado: {str(config_err)}")

    # Obtener tenant_id y otros datos de contexto con manejo de errores
    if not tenant_id:
        try:
            tenant_id = get_current_tenant_id()
        except ImportError:
            pass
        if not tenant_id or tenant_id == "default":
            logger.warning("No se pudo registrar uso de tokens: tenant_id no disponible")
            return False

    # Obtener agent_id del contexto si no se proporcionó
    if not agent_id:
        try:
            agent_id = get_current_agent_id()
        except (ImportError, Exception):
            pass
    
    # Obtener conversation_id del contexto si no se proporcionó
    if not conversation_id:
        try:
            conversation_id = get_current_conversation_id()
        except (ImportError, Exception):
            pass
    
    # Crear metadatos de la operación
    full_metadata = {
        "model": model,
        "collection_id": collection_id,
        "token_type": token_type,
        "operation": operation,
        "timestamp": int(time.time())
    }
    
    # Agregar metadatos personalizados si se proporcionaron
    if metadata:
        for key, value in metadata.items():
            if key not in full_metadata:
                full_metadata[key] = value
    
    # Intentar determinar la atribución del costo de los tokens (si aplica)
    attribution_info = None
    try:
        # Importación tardía para evitar dependencia circular
        from .attribution import TokenAttributionService
        attribution_service = TokenAttributionService()
        attribution_info = await attribution_service.determine_attribution(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type=token_type,
            operation=operation
        )
        
        if attribution_info:
            full_metadata["attribution"] = attribution_info
    except Exception as attr_err:
        logger.warning(f"Error determinando atribución de tokens: {str(attr_err)}")
    
    # Generar ID único para este registro de uso
    usage_id = str(uuid.uuid4())
    
    # Verificar límites de rate antes de continuar
    try:
        rate_limit = get_tier_rate_limit(tenant_id)
        if rate_limit:
            # Importación tardía de CacheManager para evitar ciclo
            from ..cache import CacheManager
            # Verificar contador de tokens ya consumidos
            cache_key = f"rate_limit:{tenant_id}:{token_type}:{int(time.time() / 60)}"
            cache = await CacheManager.get_instance()
            current_count = await cache.get("counter", cache_key, tenant_id) or 0
            
            # Si excede el límite, registrar y detener
            if current_count + tokens > rate_limit:
                logger.warning(f"Límite de rate excedido para tenant {tenant_id}: {current_count}/{rate_limit}")
                await cache.set("counter", cache_key, current_count + tokens, tenant_id, ttl=70)
                
                # Registrar el evento de límite excedido
                try:
                    rate_limit_table = get_table_name("rate_limit_events")
                    supabase = get_supabase_client()
                    await supabase.table(rate_limit_table).insert({
                        "tenant_id": tenant_id,
                        "token_type": token_type,
                        "tokens_requested": tokens,
                        "tokens_available": rate_limit - current_count,
                        "metadata": json.dumps(full_metadata)
                    }).execute()
                except Exception as db_err:
                    logger.error(f"Error registrando evento de límite: {str(db_err)}")
                
                return False
            
            # Actualizar contador
            await cache.set("counter", cache_key, current_count + tokens, tenant_id, ttl=70)
    except Exception as rate_err:
        logger.warning(f"Error verificando límites de rate: {str(rate_err)}")
    
    # Generar clave de idempotencia si no se proporcionó una
    if idempotency_key is None and operation and tenant_id:
        # Componentes para formar una clave única
        # Usamos datos significativos de la operación para evitar duplicaciones
        key_components = [
            str(tenant_id),
            str(tokens),
            token_type,
            str(operation or ""),
            str(model or ""),
            str(agent_id or ""),
            str(conversation_id or ""),
            str(int(time.time()))
        ]
        # Generar hash para idempotencia (MD5 es suficiente para este caso de uso)
        idempotency_key = hashlib.md5("|".join(key_components).encode()).hexdigest()
        logger.debug(f"Generada clave de idempotencia: {idempotency_key} para tenant {tenant_id}")
    
    # Registrar uso en base de datos utilizando la nueva implementación RPC
    try:
        logger.debug(f"Iniciando tracking de {tokens} tokens ({token_type}) para tenant {tenant_id}")
        
        # Usar RPC para incrementar el contador de tokens con idempotencia
        supabase = get_supabase_client()
        
        # Preparar datos para la función RPC
        rpc_data = {
            "p_tenant_id": tenant_id,
            "p_tokens": tokens,
            "p_token_type": token_type,
            "p_operation": operation,
            "p_model": model,
            "p_metadata": json.dumps(full_metadata),
            "p_agent_id": agent_id,
            "p_conversation_id": conversation_id,
            "p_idempotency_key": idempotency_key
        }
        
        logger.debug(f"Llamando a RPC track_token_usage con idempotency_key={idempotency_key}")
            
        # Llamar a la función RPC mejorada
        result = await supabase.rpc("track_token_usage", rpc_data).execute()
        
        # Verificar resultado
        if result.data is True:
            logger.debug(f"Tracking de tokens exitoso con nuevo procedimiento unificado")
            return True
        else:
            logger.warning(f"Resultado inesperado del RPC track_token_usage: {result.data}")
            # Error al usar RPC directo, intentar con operación a nivel de tabla
            # Esto es más robusto pero menos eficiente que el RPC
            logger.info(f"Utilizando tracking directo a tabla para tokens")
            
            try:
                # Insertar directamente en la tabla de token_usage
                table_name = get_table_name("token_usage")
                await supabase.table(table_name).insert({
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "conversation_id": conversation_id,
                    "collection_id": collection_id,
                    "token_type": token_type,
                    "operation": operation,
                    "tokens": tokens,
                    "model": model,
                    "metadata": full_metadata,
                    "idempotency_key": idempotency_key
                }).execute()
                return True
            except Exception as insert_err:
                logger.error(f"Error en tracking directo: {str(insert_err)}")
                return False
            
    except Exception as db_err:
        logger.error(f"Error registrando uso de tokens: {str(db_err)}", exc_info=True)
        
        # Implementar reintento con backoff exponencial simple antes de usar el fallback
        max_retries = 2
        base_delay = 0.5  # 500ms inicial
        
        for retry in range(max_retries):
            try:
                # Calcular delay con jitter para evitar tormentas de reintentos
                delay = base_delay * (2 ** retry) * (0.9 + 0.2 * random.random())
                logger.info(f"Reintentando tracking de tokens ({retry+1}/{max_retries}) en {delay:.2f}s")
                
                # Esperar antes de reintentar
                await asyncio.sleep(delay)
                
                # Reintentar la llamada RPC
                result = await supabase.rpc("track_token_usage", rpc_data).execute()
                if result.data is True:
                    logger.info(f"Reintento {retry+1} exitoso")
                    return True
            except Exception as retry_err:
                logger.warning(f"Error en reintento {retry+1}: {str(retry_err)}")
        
        # Último recurso - inserción directa a la tabla
        logger.warning(f"Usando inserción directa a tabla después de {max_retries} reintentos fallidos")
        try:
            # Insertar directamente en la tabla de token_usage
            table_name = get_table_name("token_usage")
            await supabase.table(table_name).insert({
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "conversation_id": conversation_id,
                "collection_id": collection_id,
                "token_type": token_type,
                "operation": operation,
                "tokens": tokens,
                "model": model,
                "metadata": full_metadata,
                "idempotency_key": idempotency_key
            }).execute()
            logger.info(f"Inserción directa a tabla exitosa")
            return True
        except Exception as fallback_err:
            logger.error(f"Error en fallback de tracking: {str(fallback_err)}", exc_info=True)
            return False

async def track_query(
    tenant_id: str,
    operation_type: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None
) -> bool:
    await get_tier_rate_limit(tenant_id, tier=None, service_name='query-service')
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de consultas deshabilitado para {tenant_id}")
        return True
    supabase = get_supabase_client()
    total = tokens_in + tokens_out
    await track_token_usage(
        tenant_id=tenant_id,
        tokens=total,
        model=model,
        agent_id=agent_id,
        conversation_id=conversation_id,
        token_type="llm",
        operation=operation_type,
        metadata={"tokens_in": tokens_in, "tokens_out": tokens_out, "operation_type": operation_type, "model": model}
    )
    data = {
        "tenant_id": tenant_id,
        "operation_type": operation_type,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_tokens": total,
        "timestamp": int(time.time())
    }
    if agent_id:
        data["agent_id"] = agent_id
    if conversation_id:
        data["conversation_id"] = conversation_id
    try:
        await supabase.table(get_table_name("query_logs")).insert(data).execute()
        return True
    except Exception as e:
        logger.error(f"Error track_query Supabase: {e}")
        return False

async def estimate_prompt_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Estima la cantidad de tokens en un texto usando el método más preciso disponible.
    
    Utiliza tiktoken para modelos OpenAI cuando está disponible, y para otros modelos
    usa estimaciones precisas basadas en los factores de conversión establecidos.
    
    Args:
        text: Texto a analizar
        model: Modelo a usar para la estimación (por defecto gpt-3.5-turbo)
        
    Returns:
        int: Cantidad estimada de tokens
    """
    # Obtener referencia al logger
    logger = logging.getLogger(__name__)

    # Variable global para evitar intentos repetidos de importación fallidos
    _token_counter_cache = {
        "query_service": None,
        "embedding_service": None,
        "tried_import": False
    }

    def _try_import_token_counters():
        """
        Intenta importar los contadores de tokens de los servicios específicos.
        Actualiza el caché global con las funciones importadas.
        """
        if _token_counter_cache["tried_import"]:
            return  # Ya lo intentamos antes, no repetir
        
        try:
            # Intentar importar el contador de tokens del servicio de query
            try:
                from query_service.utils.token_counters import count_tokens as query_count_tokens
                _token_counter_cache["query_service"] = query_count_tokens
                logger.debug("Contador de tokens de query-service importado correctamente")
            except ImportError:
                logger.debug("No se pudo importar el contador de tokens de query-service")
                
            # Intentar importar el contador de tokens del servicio de embeddings
            try:
                from embedding_service.utils.token_counters import count_embedding_tokens
                _token_counter_cache["embedding_service"] = count_embedding_tokens
                logger.debug("Contador de tokens de embedding-service importado correctamente")
            except ImportError:
                logger.debug("No se pudo importar el contador de tokens de embedding-service")
        except Exception as e:
            logger.warning(f"Error al importar contadores de tokens: {str(e)}")
        finally:
            _token_counter_cache["tried_import"] = True

    def estimate_tokens(text: str, model: str = None) -> int:
        """
        Estima la cantidad aproximada de tokens en un texto.
        Usa el contador de tokens más preciso disponible según el servicio.
            
        Args:
            text: Texto para estimar tokens
            model: Modelo para optimizar la estimación (opcional)
            
        Returns:
            int: Cantidad estimada de tokens
        """
        if not text:
            return 0
            
        # Intentar importar los contadores si no lo hemos hecho ya
        if not _token_counter_cache["tried_import"]:
            _try_import_token_counters()
        
        # Determinar qué tipo de modelo es (llm o embedding)
        is_embedding_model = False
        if model and any(emb in model.lower() for emb in ["text-embedding", "ada-002"]):
            is_embedding_model = True
        
        # Intentar usar el contador apropiado según el tipo de modelo
        try:
            if is_embedding_model and _token_counter_cache["embedding_service"]:
                # Usar contador de embeddings
                return _token_counter_cache["embedding_service"](text, model)
            elif not is_embedding_model and _token_counter_cache["query_service"]:
                # Usar contador de LLM
                return _token_counter_cache["query_service"](text, model)
        except Exception as e:
            logger.debug(f"Error usando contador especializado: {str(e)}")
        
        # Fallback a estimación básica
        try:
            # Algoritmo simplificado de estimación basado en palabras y caracteres
            words = len(text.split())
            chars = len(text)
            
            # Factor de ajuste basado en el tipo de modelo
            factor = 1.3  # Valor por defecto
            if model:
                model_lower = model.lower()
                if "gpt-4" in model_lower or "gpt-3.5" in model_lower:
                    factor = 1.33
                elif "llama" in model_lower:
                    factor = 1.4
            
            # Fórmula de estimación: palabras + factor * (caracteres / 4)
            estimated_tokens = int(words + factor * (chars / 4))
            return max(1, estimated_tokens)
        except Exception as e:
            # Estimación ultra simple como último recurso
            logger.warning(f"Error en estimación de tokens, usando método ultra simple: {str(e)}")
            return max(1, len(text) // 4)

    return estimate_tokens(text, model)

async def track_usage(
    tenant_id: str,
    operation: str,
    metadata: Dict[str, Any]
) -> bool:
    try:
        if operation == "query":
            return await track_query(
                tenant_id=tenant_id,
                operation_type=metadata.get("operation_type", "query"),
                model=metadata.get("model", "unknown"),
                tokens_in=metadata.get("tokens_in", 0),
                tokens_out=metadata.get("tokens_out", 0),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id")
            )
        elif operation == "embedding":
            return await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("tokens", 0),
                model=metadata.get("model"),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id"),
                collection_id=metadata.get("collection_id"),
                token_type="embedding"
            )
        elif operation == "tokens":
            return await track_token_usage(
                tenant_id=tenant_id,
                tokens=metadata.get("tokens", 0),
                model=metadata.get("model"),
                agent_id=metadata.get("agent_id"),
                conversation_id=metadata.get("conversation_id"),
                collection_id=metadata.get("collection_id"),
                token_type=metadata.get("token_type", "llm")
            )
        else:
            logger.warning(f"Tipo de operación desconocido: {operation}")
            return False
    except Exception as e:
        logger.error(f"Error track_usage: {e}", extra={"tenant_id": tenant_id})
        return False

async def track_embedding_usage(
    tenant_id: Optional[str] = None,
    text_length: int = 0,
    vector_dimensions: int = 0,
    model: Optional[str] = None,
    agent_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    document_id: Optional[str] = None,
    operation: str = "embedding",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Registra el uso de embeddings para un tenant específico.
    
    Args:
        tenant_id: ID del tenant (si None, se obtiene del contexto)
        text_length: Longitud del texto procesado
        vector_dimensions: Dimensiones del vector generado
        model: Modelo de embedding utilizado
        agent_id: ID del agente relacionado (opcional)
        collection_id: ID de la colección de documentos (opcional)
        document_id: ID del documento relacionado (opcional)
        operation: Tipo de operación ('embedding', 'retrieval', etc.)
        metadata: Datos adicionales sobre la operación
        
    Returns:
        bool: True si el registro fue exitoso
    """
    if text_length <= 0:
        return True
        
    # Obtener configuración con manejo de errores
    try:
        settings = get_settings()
        if not settings.enable_usage_tracking:
            logger.debug(f"Tracking deshabilitado, omitiendo embedding de {text_length} caracteres")
            return True
    except Exception as config_err:
        logger.debug(f"Error obteniendo configuración, asumiendo tracking habilitado: {str(config_err)}")

    # Obtener tenant_id del contexto si no se proporciona
    if not tenant_id:
        try:
            tenant_id = get_current_tenant_id()
        except ImportError:
            pass
        if not tenant_id or tenant_id == "default":
            logger.warning("No se pudo registrar uso de embeddings: tenant_id no disponible")
            return False
    
    # Obtener agent_id del contexto si no se proporciona
    if not agent_id:
        try:
            agent_id = get_current_agent_id()
        except ImportError:
            pass
    
    # Preparar datos para registro
    usage_data = {
        "tenant_id": tenant_id,
        "model": model or "default",
        "text_length": text_length,
        "vector_dimensions": vector_dimensions,
        "operation": operation,
        "timestamp": time.time(),
        "usage_id": str(uuid.uuid4())
    }
    
    # Añadir datos opcionales si están disponibles
    if agent_id:
        usage_data["agent_id"] = agent_id
    if collection_id:
        usage_data["collection_id"] = collection_id
    if document_id:
        usage_data["document_id"] = document_id
    if metadata:
        usage_data["metadata"] = json.dumps(metadata)
    
    # Registrar en base de datos
    try:
        supabase = get_supabase_client()
        table_name = get_table_name("embedding_usage")
        
        # Insertar registro de uso
        response = await supabase.table(table_name).insert(usage_data).execute()
        
        if response.data:
            logger.debug(f"Uso de embedding registrado: {text_length} caracteres, modelo {model}")
            return True
        else:
            logger.warning(f"Error al registrar uso de embedding: {response.error}")
            return False
    except Exception as e:
        logger.error(f"Excepción al registrar uso de embedding: {str(e)}")
        return False

# El decorador track_operation ha sido eliminado según el plan de refactorización.
# En su lugar, utilizar las funciones de tracking directas:
#
# - Para tracking de operaciones generales: track_usage()
# - Para tracking de tokens LLM: track_token_usage()
# - Para tracking de embeddings: track_embedding_usage()
#
# NOTA: Si necesitas la funcionalidad de este decorador, puedes implementarlo como:
#
# ```python
# @handle_errors(error_type="service")
# async def tu_funcion(tenant_id, ...):
#     start_time = time.time()
#     # Ejecutar lógica principal
#     result = await proceso_principal()
#     # Registrar métricas al finalizar
#     await track_usage(tenant_id, operation="nombre.operacion", metadata={...})
#     return result
# ```
