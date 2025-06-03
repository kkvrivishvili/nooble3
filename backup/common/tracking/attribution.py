"""
Servicio de atribución de tokens para determinar quién debe pagar por los tokens.

Este módulo contiene lógica para determinar el propietario final de los tokens
en diferentes escenarios, como agentes compartidos públicamente.
"""

import logging
from typing import Optional, Dict, Any

from ..context.vars import get_current_tenant_id, get_current_agent_id
from ..cache import CacheManager
from ..db.supabase import get_supabase_client
from ..db.tables import get_table_name

logger = logging.getLogger(__name__)

class TokenAttributionService:
    """
    Servicio para determinar la atribución de tokens, especialmente en 
    escenarios donde un agente es propiedad de un tenant pero es accedido
    por otro tenant o usuario anónimo.
    """
    
    @staticmethod
    async def determine_token_owner(
        requester_tenant_id: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> str:
        """
        Determina quién debe pagar por los tokens utilizados.
        
        Args:
            requester_tenant_id: ID del tenant que realiza la solicitud
            agent_id: ID del agente con el que se interactúa
            conversation_id: ID de la conversación
            
        Returns:
            ID del tenant al que se deben atribuir los tokens
        """
        if not agent_id or not requester_tenant_id:
            return requester_tenant_id
            
        owner_detected = False
        effective_tenant_id = requester_tenant_id
        
        # 1. Intentar obtener de la caché
        if conversation_id:
            try:
                cached_conv = await CacheManager.get(
                    data_type="conversation",
                    resource_id=conversation_id,
                    tenant_id=requester_tenant_id
                )
                
                if cached_conv and "owner_tenant_id" in cached_conv:
                    if cached_conv["owner_tenant_id"] != requester_tenant_id:
                        effective_tenant_id = cached_conv["owner_tenant_id"]
                        owner_detected = True
                        logger.debug(f"Using cached owner: attributing tokens to owner {effective_tenant_id} instead of {requester_tenant_id}")
            except Exception as e:
                logger.warning(f"Error retrieving owner from cache: {str(e)}")
        
        # 2. Si no está en caché, consultar base de datos
        if not owner_detected:
            try:
                supabase = get_supabase_client()
                agent_result = await supabase.table(get_table_name("agent_configs")).select("tenant_id").eq("agent_id", agent_id).execute()
                
                if agent_result.data:
                    agent_owner_id = agent_result.data[0]["tenant_id"]
                    
                    if agent_owner_id != requester_tenant_id:
                        effective_tenant_id = agent_owner_id
                        owner_detected = True
                        logger.debug(f"Attributing tokens to agent owner {agent_owner_id} instead of {requester_tenant_id}")
                        
                        # Guardar en caché para futuras consultas
                        if conversation_id:
                            try:
                                await CacheManager.set(
                                    data_type="conversation",
                                    resource_id=conversation_id,
                                    value={"owner_tenant_id": agent_owner_id, "is_public": True},
                                    tenant_id=requester_tenant_id,
                                    ttl=CacheManager.TTL_LONG  # 24 horas
                                )
                            except Exception as cache_error:
                                logger.warning(f"Error caching conversation owner: {str(cache_error)}")
            except Exception as e:
                logger.warning(f"Error checking agent owner, using original tenant_id: {str(e)}")
        
        return effective_tenant_id
