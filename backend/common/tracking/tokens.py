"""
Seguimiento de uso de tokens para facturación y cuotas.
"""

import logging
import time
import asyncio
import json
from typing import Dict, Any, Optional, List, Union

from ..db.supabase import get_supabase_client, get_table_name
from ..db.rpc import increment_token_usage as rpc_increment_token_usage
from ..cache.manager import CacheManager
from ..cache.counters import increment_token_counter
from ..config.settings import get_settings
from ..context.vars import get_current_tenant_id

# Eliminamos la importación circular y reemplazamos con la implementación unificada
# from ..auth.quotas import track_token_usage as quotas_track_token_usage

logger = logging.getLogger(__name__)

async def _internal_track_token_usage(
    tenant_id: str,
    model: str = "default",
    tokens: int = 0,
    operation: str = "query",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Implementación interna para registrar el uso de tokens para un tenant.
    Esta función es utilizada tanto por auth.quotas como por tracking.tokens
    para evitar duplicación de código.
    
    Args:
        tenant_id: ID del tenant
        model: Nombre del modelo utilizado
        tokens: Número de tokens consumidos
        operation: Tipo de operación (query, embed, chat, etc)
        metadata: Metadatos adicionales de la operación
        
    Returns:
        bool: True si se registró correctamente
    """
    if tokens <= 0:
        return True  # Nada que registrar
        
    # Preparar datos para registro
    usage_data = {
        "tenant_id": tenant_id,
        "model": model,
        "tokens": tokens,
        "operation": operation,
        "timestamp": time.time()
    }
    
    if metadata:
        usage_data["metadata"] = metadata
    
    try:
        # 1. Actualizar contador en Redis para operaciones de alta frecuencia
        await CacheManager.increment(
            tenant_id=tenant_id,
            data_type="token_usage",
            resource_id=f"{model}:{operation}",
            amount=tokens
        )
        
        # 2. Añadir a la cola de persistencia para almacenar en Supabase
        await CacheManager.rpush(
            queue_name="token_usage_queue",
            data=usage_data
        )
        
        return True
    except Exception as e:
        logger.error(f"Error registrando uso de tokens: {str(e)}")
        return False

async def track_token_usage(
    tenant_id: str, 
    tokens: int, 
    model: str = None, 
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    token_type: str = "llm",
    operation: str = "query"
) -> bool:
    """
    Registra el uso de tokens para un tenant.
    
    En caso de conversaciones públicas con agentes, detecta automáticamente si los tokens
    deben contabilizarse al propietario del agente en lugar del usuario que interactúa.
    
    Args:
        tenant_id: ID del tenant que realiza la solicitud (obtenido del JWT)
        tokens: Número estimado de tokens
        model: Modelo usado (para ajustar el factor de costo)
        agent_id: ID del agente con el que se interactúa (opcional)
                  Si se proporciona, se verifica si los tokens deben contabilizarse al propietario.
        conversation_id: ID de la conversación (opcional, para tracking)
        token_type: Tipo de tokens ('llm' o 'embedding')
        operation: Tipo de operación (query, embed, chat, etc)
        
    Returns:
        bool: True si se registró correctamente
    """
    # Verificar si el tracking está habilitado
    settings = get_settings()
    if not settings.enable_usage_tracking:
        logger.debug(f"Tracking de uso deshabilitado, omitiendo registro de {tokens} tokens para {tenant_id}")
        return True
    
    try:
        # Usar el factor de costo del modelo o 1.0 por defecto
        cost_factor = settings.model_cost_factors.get(model, 1.0) if model else 1.0
        adjusted_tokens = int(tokens * cost_factor)
        
        # Preparar metadatos
        metadata = {
            "token_type": token_type,
            "cost_factor": cost_factor
        }
        
        if agent_id:
            metadata["agent_id"] = agent_id
        
        if conversation_id:
            metadata["conversation_id"] = conversation_id
        
        # Usar implementación interna unificada
        await _internal_track_token_usage(
            tenant_id=tenant_id,
            model=model or "default",
            tokens=adjusted_tokens,
            operation=operation,
            metadata=metadata
        )
        
        # También registrar en Supabase a través de RPC para compatibilidad
        # con el sistema anterior (eventualmente este se puede deprecar)
        await rpc_increment_token_usage(
            tenant_id=tenant_id,
            tokens=adjusted_tokens,
            agent_id=agent_id,
            conversation_id=conversation_id,
            token_type=token_type
        )
        
        return True
    except Exception as e:
        logger.error(f"Error tracking {token_type} token usage: {str(e)}")
        return False

async def estimate_prompt_tokens(text: str) -> int:
    """
    Estima la cantidad de tokens en un texto.
    Utiliza una aproximación simple basada en palabras.
    
    Args:
        text: Texto a estimar
        
    Returns:
        int: Estimación de tokens
    """
    if not text:
        return 0
    
    # Aproximación simple: 4 caracteres ≈ 1 token
    # Esta es una estimación muy básica, pero es rápida
    return max(1, len(text) // 4)


async def process_token_usage_queue_worker():
    """
    Worker para procesar la cola de registro de uso de tokens.
    
    Extrae elementos de la cola de tokens y los guarda en Supabase.
    Se debe ejecutar como un servicio independiente o un worker.
    """
    logger.info("Iniciando worker de procesamiento de cola de tokens")
    
    supabase = get_supabase_client()
    batch_size = 50  # Procesar en lotes para mayor eficiencia
    retry_delay = 5  # Segundos entre reintentos en caso de error
    
    while True:
        try:
            # Extraer batch_size elementos de la cola
            batch = []
            for _ in range(batch_size):
                # Intentar obtener un elemento de la cola
                item = await CacheManager.lpop("token_usage_queue")
                if not item:
                    break
                
                try:
                    # Convertir de JSON a dict si es necesario
                    if isinstance(item, str):
                        item = json.loads(item)
                    batch.append(item)
                except (json.JSONDecodeError, TypeError):
                    logger.error(f"Error decodificando elemento de la cola: {item}")
                    continue
            
            # Si no hay elementos, esperar antes de volver a intentar
            if not batch:
                await asyncio.sleep(retry_delay)
                continue
            
            # Registrar lote en Supabase
            if batch:
                logger.debug(f"Procesando lote de {len(batch)} registros de uso de tokens")
                
                # Preparar datos para inserción en Supabase
                records = []
                for usage in batch:
                    tenant_id = usage.get("tenant_id")
                    tokens = usage.get("tokens", 0)
                    model = usage.get("model", "default")
                    operation = usage.get("operation", "query")
                    timestamp = usage.get("timestamp", time.time())
                    metadata = usage.get("metadata", {})
                    
                    if not tenant_id or tokens <= 0:
                        continue
                    
                    record = {
                        "tenant_id": tenant_id,
                        "tokens": tokens,
                        "model": model,
                        "operation": operation,
                        "created_at": timestamp,
                        "metadata": metadata
                    }
                    records.append(record)
                
                if records:
                    # Insertar registros en Supabase
                    try:
                        result = await supabase.table(get_table_name("token_usage")).insert(records).execute()
                        if hasattr(result, "error") and result.error:
                            logger.error(f"Error insertando registros en Supabase: {result.error}")
                        else:
                            logger.debug(f"Registrados {len(records)} usos de tokens en Supabase")
                    except Exception as e:
                        logger.error(f"Error al insertar lote en Supabase: {str(e)}")
                        
                        # En caso de error, intentar insertar uno por uno para no perder datos
                        for record in records:
                            try:
                                await supabase.table(get_table_name("token_usage")).insert(record).execute()
                            except Exception as inner_e:
                                logger.error(f"Error al insertar registro individual: {str(inner_e)}")
        
        except Exception as e:
            logger.exception(f"Error procesando cola de tokens: {str(e)}")
            await asyncio.sleep(retry_delay)


def start_token_usage_worker():
    """
    Inicia el worker de procesamiento de tokens como una tarea en segundo plano.
    """
    loop = asyncio.get_event_loop()
    worker_task = loop.create_task(process_token_usage_queue_worker())
    return worker_task