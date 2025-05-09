"""
Servicio de reconciliación para sincronizar contadores entre caché y base de datos.

Este módulo contiene funciones para asegurar la consistencia entre los contadores
en memoria/Redis y los contadores persistentes en la base de datos.
"""

import json
import time
import logging
from typing import List, Dict, Any, Optional

from ..cache import CacheManager
# La función increment_token_usage_raw ha sido eliminada y reemplazada por la implementación interna
# Ver comentario en common/db/rpc.py
from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name
from ..context.vars import get_current_tenant_id

logger = logging.getLogger(__name__)

async def reconcile_pending_tokens() -> int:
    """
    Procesa todos los registros de tokens pendientes de reconciliación.
    
    Esta función debe ejecutarse periódicamente como una tarea programada
    para asegurar que todos los tokens se registren correctamente en la
    base de datos, incluso cuando hay fallos temporales.
    
    Returns:
        int: Número de registros procesados exitosamente
    """
    try:
        # Obtener todos los registros pendientes
        pending_records = await CacheManager.get_set_members(
            set_name="pending_token_reconciliation",
            tenant_id="system"
        )
        
        if not pending_records:
            logger.debug("No hay registros pendientes de reconciliación")
            return 0
            
        logger.info(f"Reconciliando {len(pending_records)} registros de tokens pendientes")
        
        success_count = 0
        for record_json in pending_records:
            try:
                record = json.loads(record_json)
                
                # Intentar persistir directamente en la tabla
                try:
                    # Obtener cliente y tabla
                    supabase = await get_supabase_client()
                    table_name = get_table_name("token_usage")
                    
                    # Insertar directamente en la tabla token_usage
                    result = await supabase.table(table_name).insert({
                        "tenant_id": record["tenant_id"],
                        "tokens": record["tokens"],
                        "agent_id": record.get("agent_id"),
                        "conversation_id": record.get("conversation_id"),
                        "token_type": record.get("token_type", "llm"),
                        "operation": record.get("operation", "query"),
                        "model": record.get("model"),
                        "metadata": record.get("metadata", {})
                    }).execute()
                    
                    success = result.data is not None
                except Exception as e:
                    logger.error(f"Error insertando token en reconciliación: {str(e)}")
                    success = False
                
                if success:
                    # Eliminar de la lista de pendientes
                    await CacheManager.remove_from_set(
                        set_name="pending_token_reconciliation",
                        value=record_json,
                        tenant_id="system"
                    )
                    success_count += 1
                    logger.debug(f"Registro reconciliado exitosamente: tenant={record['tenant_id']}, tokens={record['tokens']}")
            except Exception as e:
                logger.error(f"Error reconciliando registro {record_json}: {str(e)}")
                
        logger.info(f"Reconciliación completa: {success_count}/{len(pending_records)} registros procesados exitosamente")
        return success_count
                
    except Exception as e:
        logger.error(f"Error en proceso de reconciliación: {str(e)}")
        return 0

async def consolidate_counters(
    pattern: str = "*:counter:token_usage:*",
    tenant_id: Optional[str] = None,
    token_type: Optional[str] = None
) -> int:
    """
    Consolida contadores de Redis en la base de datos asegurando
    que todos los datos estén correctamente persistidos.
    
    Args:
        pattern: Patrón de claves a buscar en Redis
        tenant_id: ID del tenant para filtrar (None para todos)
        token_type: Tipo de token para filtrar (None para todos)
        
    Returns:
        int: Número de contadores consolidados
    """
    # Obtener cliente Redis
    from ..cache.redis import get_redis_client
    redis_client = await get_redis_client()
    if not redis_client:
        logger.error("Redis no disponible para consolidación")
        return 0
    
    try:
        # Buscar todas las claves que coincidan con el patrón
        keys = await redis_client.keys(pattern)
        
        if not keys:
            logger.debug(f"No se encontraron contadores con el patrón: {pattern}")
            return 0
            
        logger.info(f"Consolidando {len(keys)} contadores")
        
        consolidated_count = 0
        for key in keys:
            try:
                # Si hay filtro de tenant, aplicarlo
                if tenant_id and not key.startswith(f"{tenant_id}:"):
                    continue
                    
                # Analizar la clave para extraer componentes
                parts = key.split(":")
                
                # El tenant es siempre el primer componente
                current_tenant_id = parts[0] if parts else None
                
                if not current_tenant_id:
                    logger.warning(f"No se pudo determinar tenant_id para la clave: {key}")
                    continue
                
                # Obtener tipo de token (llm o embedding)
                current_token_type = "llm"  # Valor por defecto
                for i, part in enumerate(parts):
                    if part == "type" and i+1 < len(parts):
                        current_token_type = parts[i+1]
                
                # Si hay filtro de token_type, aplicarlo
                if token_type and current_token_type != token_type:
                    continue
                
                # Obtener valor actual
                value = await redis_client.get(key)
                if not value:
                    continue
                    
                try:
                    token_count = int(value)
                except (ValueError, TypeError):
                    logger.warning(f"Valor no numérico en contador: {key}={value}")
                    continue
                
                # Registrar en la base de datos solo si hay tokens
                if token_count > 0:
                    # Extraer otros componentes de context
                    agent_id = None
                    conversation_id = None
                    
                    for i, part in enumerate(parts):
                        if part == "agent" and i+1 < len(parts):
                            agent_id = parts[i+1]
                        elif part == "conv" and i+1 < len(parts):
                            conversation_id = parts[i+1]
                    
                    # Persistir en base de datos
                    try:
                        # Obtener cliente y tabla
                        supabase = await get_supabase_client()
                        table_name = get_table_name("token_usage")
                        
                        # Insertar directamente en la tabla token_usage
                        result = await supabase.table(table_name).insert({
                            "tenant_id": current_tenant_id,
                            "tokens": token_count,
                            "token_type": current_token_type,
                            "agent_id": agent_id,
                            "conversation_id": conversation_id,
                            "operation": "consolidated",
                            "metadata": {"source": "consolidation"}
                        }).execute()
                        
                        success = result.data is not None
                    except Exception as e:
                        logger.error(f"Error insertando token consolidado: {str(e)}")
                        success = False
                    
                    if success:
                        consolidated_count += 1
                        logger.debug(f"Consolidado contador {key} con valor {value}")
                        
                        # Opcionalmente, resetear el contador en Redis
                        # await redis_client.set(key, "0")
                
            except Exception as key_err:
                logger.error(f"Error procesando clave {key}: {str(key_err)}")
                
        logger.info(f"Consolidación completada: {consolidated_count}/{len(keys)} contadores procesados")
        return consolidated_count
                
    except Exception as e:
        logger.error(f"Error en consolidación de contadores: {str(e)}")
        return 0

async def audit_token_counters(
    tenant_id: Optional[str] = None,
    days_back: int = 7
) -> Dict[str, Any]:
    """
    Realiza una auditoría de contadores de tokens para verificar
    consistencia entre Redis y la base de datos.
    
    Args:
        tenant_id: ID del tenant a auditar (None para todos)
        days_back: Días hacia atrás a considerar para la auditoría
        
    Returns:
        Dict con resultados de la auditoría
    """
    from ..db.supabase import get_supabase_client
    
    results = {
        "redis_counters": 0,
        "db_counters": 0,
        "mismatches": 0,
        "reconciled": 0,
        "details": []
    }
    
    try:
        # 1. Obtener contadores de Redis
        redis_counters = await _get_redis_token_counters(tenant_id)
        results["redis_counters"] = len(redis_counters)
        
        # 2. Obtener contadores de la base de datos
        db_counters = await _get_db_token_counters(tenant_id, days_back)
        results["db_counters"] = len(db_counters)
        
        # 3. Comparar y encontrar diferencias
        for tenant, counters in redis_counters.items():
            for token_type, count in counters.items():
                db_count = db_counters.get(tenant, {}).get(token_type, 0)
                
                # Si hay diferencia
                if count != db_count:
                    diff = count - db_count
                    results["mismatches"] += 1
                    results["details"].append({
                        "tenant_id": tenant,
                        "token_type": token_type,
                        "redis_count": count,
                        "db_count": db_count,
                        "difference": diff
                    })
                    
                    # Si hay más tokens en Redis que en BD, reconciliar
                    if diff > 0:
                        try:
                            # Obtener cliente y tabla
                            supabase = await get_supabase_client()
                            table_name = get_table_name("token_usage")
                            
                            # Insertar directamente en la tabla token_usage
                            result = await supabase.table(table_name).insert({
                                "tenant_id": tenant,
                                "tokens": diff,
                                "token_type": token_type,
                                "operation": "audit_reconciliation",
                                "metadata": {"source": "audit", "redis_count": count, "db_count": db_count}
                            }).execute()
                            
                            success = result.data is not None
                        except Exception as e:
                            logger.error(f"Error en reconciliación de auditoría: {str(e)}")
                            success = False
                        if success:
                            results["reconciled"] += 1
        
        return results
    except Exception as e:
        logger.error(f"Error en auditoría de contadores: {str(e)}")
        return {"error": str(e)}

async def _get_redis_token_counters(tenant_id: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """
    Obtiene los contadores de tokens agrupados desde Redis.
    
    Args:
        tenant_id: ID del tenant para filtrar (None para todos)
        
    Returns:
        Dict con contadores agrupados por tenant y tipo de token
    """
    from ..cache.redis import get_redis_client
    
    result = {}
    redis_client = await get_redis_client()
    if not redis_client:
        return result
    
    try:
        # Patrón para buscar todos los contadores o solo los del tenant específico
        pattern = f"{tenant_id if tenant_id else '*'}:counter:token_usage:*"
        keys = await redis_client.keys(pattern)
        
        for key in keys:
            parts = key.split(":")
            current_tenant = parts[0]
            token_type = "llm"  # Valor por defecto
            
            # Extraer tipo de token
            for i, part in enumerate(parts):
                if part == "type" and i+1 < len(parts):
                    token_type = parts[i+1]
            
            # Obtener valor
            value = await redis_client.get(key)
            if value:
                try:
                    count = int(value)
                    
                    # Acumular por tenant y tipo
                    if current_tenant not in result:
                        result[current_tenant] = {}
                    
                    if token_type not in result[current_tenant]:
                        result[current_tenant][token_type] = 0
                    
                    result[current_tenant][token_type] += count
                except (ValueError, TypeError):
                    pass
                    
        return result
    except Exception as e:
        logger.error(f"Error obteniendo contadores de Redis: {str(e)}")
        return {}

async def _get_db_token_counters(
    tenant_id: Optional[str] = None,
    days_back: int = 7
) -> Dict[str, Dict[str, int]]:
    """
    Obtiene los contadores de tokens desde la base de datos.
    
    Args:
        tenant_id: ID del tenant para filtrar (None para todos)
        days_back: Días hacia atrás a considerar
        
    Returns:
        Dict con contadores agrupados por tenant y tipo de token
    """
    from ..db.supabase import get_supabase_client
    from ..db.tables import get_table_name
    
    result = {}
    supabase = get_supabase_client()
    
    try:
        # Construir consulta
        query = supabase.table(get_table_name("token_usage")).select("tenant_id, token_type, SUM(tokens) as total")
        
        # Filtrar por tenant si se especifica
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        
        # Filtrar por fecha
        if days_back > 0:
            from datetime import datetime, timedelta
            cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
            query = query.gte("created_at", cutoff_date)
        
        # Agrupar y ejecutar
        data = await query.group_by("tenant_id, token_type").execute()
        
        if data.data:
            for row in data.data:
                tenant = row.get("tenant_id")
                token_type = row.get("token_type", "llm")
                total = row.get("total", 0)
                
                if tenant:
                    if tenant not in result:
                        result[tenant] = {}
                    
                    result[tenant][token_type] = total
                    
        return result
    except Exception as e:
        logger.error(f"Error obteniendo contadores de la base de datos: {str(e)}")
        return {}
