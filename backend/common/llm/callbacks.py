"""
Módulo centralizado para callbacks relacionados con modelos LLM.
Proporciona implementaciones estándar de callbacks para tracking, conteo de tokens
y otras funcionalidades comunes para todos los servicios.
"""

import time
import logging
from typing import List, Dict, Any, Optional

from llama_index.core.callbacks import CallbackManager, CBEventType, EventPayload

from ..llm.token_counters import count_tokens

logger = logging.getLogger(__name__)

class TokenCountingHandler:
    """
    Callback handler para contar tokens de entrada y salida con precisión.
    Implementación centralizada para uso en todos los servicios.
    Compatible con LlamaIndex.
    """
    
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self._prompts = []
    
    def on_event_start(self, event_type, payload, **kwargs):
        """Maneja el inicio de eventos de LlamaIndex."""
        if event_type == CBEventType.LLM:
            # Extraer el prompt para contar tokens
            if payload.get(EventPayload.PROMPT):
                prompt = payload.get(EventPayload.PROMPT)
                self._prompts.append(prompt)
                self.input_tokens += count_tokens(prompt)
    
    def on_event_end(self, event_type, payload, **kwargs):
        """Maneja el fin de eventos de LlamaIndex."""
        if event_type == CBEventType.LLM:
            # Contar tokens de salida si hay una respuesta
            if payload.get(EventPayload.RESPONSE):
                response = payload.get(EventPayload.RESPONSE)
                self.output_tokens += count_tokens(response)
    
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


class TrackingCallbackHandler:
    """
    Callback handler para tracking automático de uso de LLM.
    Registra métricas clave como tokens, latencia y resultados.
    """
    
    def __init__(self, tenant_id: str, agent_id: Optional[str] = None, 
                 conversation_id: Optional[str] = None, operation: str = "llm"):
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
        
    def on_event_start(self, event_type, payload, **kwargs):
        """Registra el inicio de una generación LLM."""
        if event_type == CBEventType.LLM:
            self.start_time = time.time()
            # Estimar tokens de entrada
            if payload.get(EventPayload.PROMPT):
                prompt = payload.get(EventPayload.PROMPT)
                self.tokens["input"] += count_tokens(prompt)
    
    def on_event_end(self, event_type, payload, **kwargs):
        """Registra la finalización de una generación LLM."""
        if event_type == CBEventType.LLM:
            self.end_time = time.time()
            # Calcular latencia
            latency = (self.end_time - self.start_time) * 1000  # ms
            
            # Contar tokens de salida
            if payload.get(EventPayload.RESPONSE):
                response = payload.get(EventPayload.RESPONSE)
                self.tokens["output"] += count_tokens(response)
            
            self.tokens["total"] = self.tokens["input"] + self.tokens["output"]
            
            # Usar la función centralizada de tracking (async)
            # Este es un llamado que normalmente sería async, pero lo hacemos sin await
            # porque langchain no soporta callbacks async
            from ..tracking import track_token_usage_sync
            
            track_token_usage_sync(
                tenant_id=self.tenant_id,
                tokens=self.tokens["total"],
                model=getattr(payload, "model", "unknown"),
                token_type="llm",
                agent_id=self.agent_id,
                conversation_id=self.conversation_id,
                input_tokens=self.tokens["input"],
                output_tokens=self.tokens["output"],
                latency_ms=latency,
                service=self.operation
            )


class LatencyTrackingHandler:
    """
    Callback handler para medir latencia de LLM.
    Compatible con LlamaIndex.
    """
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.latency = None
    
    def on_event_start(self, event_type, payload, **kwargs):
        """Registra el tiempo de inicio para eventos LLM."""
        if event_type == CBEventType.LLM:
            self.start_time = time.time()
    
    def on_event_end(self, event_type, payload, **kwargs):
        """Registra el tiempo de fin y calcula la latencia."""
        if event_type == CBEventType.LLM and self.start_time is not None:
            self.end_time = time.time()
            self.latency = self.end_time - self.start_time
    
    def get_latency(self):
        """Retorna la latencia en segundos o None si no está disponible."""
        return self.latency
