"""
Módulo centralizado para callbacks relacionados con modelos LLM.
Proporciona implementaciones estándar de callbacks para tracking, conteo de tokens
y otras funcionalidades comunes para todos los servicios.
"""

import time
import logging
from typing import List, Dict, Any, Optional

from langchain_core.callbacks import BaseCallbackHandler

from ..llm.utils import count_tokens

logger = logging.getLogger(__name__)

class TokenCountingHandler(BaseCallbackHandler):
    """
    Callback handler para contar tokens de entrada y salida con precisión.
    Implementación centralizada para uso en todos los servicios.
    """
    
    def __init__(self):
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self._prompts = []
    
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Cuenta tokens de entrada al iniciar el LLM."""
        self._prompts = prompts
        # Contar tokens de entrada usando la función centralizada
        self.input_tokens = sum(count_tokens(p) for p in prompts)
    
    def on_llm_new_token(self, token: str, **kwargs):
        """Cuenta cada token de salida."""
        # Incrementa contador por cada token generado
        self.output_tokens += 1
    
    def get_total_tokens(self):
        """Retorna el total de tokens utilizados."""
        return self.input_tokens + self.output_tokens
    
    def get_counts(self):
        """Retorna un diccionario con el conteo de tokens."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens
        }


class TrackingCallbackHandler(BaseCallbackHandler):
    """
    Callback handler para tracking automático de uso de LLM.
    Registra métricas clave como tokens, latencia y resultados.
    """
    
    def __init__(self, tenant_id: str, agent_id: Optional[str] = None, 
                 conversation_id: Optional[str] = None, operation: str = "llm"):
        super().__init__()
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.operation = operation
        self.start_time = None
        self.end_time = None
        self.tokens = {
            "input": 0,
            "output": 0,
            "total": 0
        }
        
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Registra el inicio de una generación LLM."""
        self.start_time = time.time()
        # Estimar tokens de entrada
        for prompt in prompts:
            self.tokens["input"] += count_tokens(prompt)
    
    def on_llm_end(self, response, **kwargs):
        """Registra la finalización de una generación LLM."""
        self.end_time = time.time()
        # Calcular latencia
        latency = (self.end_time - self.start_time) * 1000  # ms
        
        # Contar tokens de salida
        if hasattr(response, "generations") and response.generations:
            for gen in response.generations:
                for g in gen:
                    self.tokens["output"] += count_tokens(g.text)
        
        self.tokens["total"] = self.tokens["input"] + self.tokens["output"]
        
        # Usar la función centralizada de tracking (async)
        # Este es un llamado que normalmente sería async, pero lo hacemos sin await
        # porque langchain no soporta callbacks async
        from ..tracking import track_token_usage_sync
        
        track_token_usage_sync(
            tenant_id=self.tenant_id,
            tokens=self.tokens["total"],
            model=getattr(response, "model", "unknown"),
            token_type="llm",
            agent_id=self.agent_id,
            conversation_id=self.conversation_id,
            input_tokens=self.tokens["input"],
            output_tokens=self.tokens["output"],
            latency_ms=latency,
            service=self.operation
        )
