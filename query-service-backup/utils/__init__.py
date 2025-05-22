"""
Utilidades específicas para el servicio de consulta.

Este paquete contiene funciones de utilidad específicas para el servicio de consulta,
incluidas funciones para contar y estimar tokens que han reemplazado a las antiguas
funciones ubicadas anteriormente en common/llm.
"""

from .callbacks import TokenCountingHandler, LatencyTrackingHandler, TrackingCallbackHandler
from .llamaindex_utils import create_response_synthesizer
from .token_counters import count_tokens, count_message_tokens, estimate_model_max_tokens

__all__ = [
    'TokenCountingHandler',
    'LatencyTrackingHandler',
    'TrackingCallbackHandler',
    'create_response_synthesizer',
    'count_tokens',
    'count_message_tokens',
    'estimate_model_max_tokens',
]
