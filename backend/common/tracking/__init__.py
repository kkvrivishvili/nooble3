"""
Módulo unificado para tracking y monitoreo de uso de recursos.

Este módulo expone funciones estandarizadas para el tracking de tokens,
queries y embeddings, con soporte para idempotencia y tipos ENUM estandarizados.
"""

from ._base import (
    track_token_usage,
    track_query,
    track_usage,
    estimate_prompt_tokens,
    track_embedding_usage,
    track_operation
)
from .attribution import TokenAttributionService
from .reconciliation import (
    reconcile_pending_tokens,
    consolidate_counters,
    audit_token_counters
)
from .alerts import register_alert, AlertLevel
from .scheduled_tasks import (
    run_daily_reconciliation,
    run_weekly_consolidation,
    run_monthly_audit,
    register_reconciliation_tasks
)

# Constantes para tipos de tokens (coinciden con los ENUM de base de datos)
TOKEN_TYPE_LLM = "llm"
TOKEN_TYPE_EMBEDDING = "embedding"
TOKEN_TYPE_FINE_TUNING = "fine_tuning"

# Constantes para tipos de operación (coinciden con los ENUM de base de datos)
OPERATION_QUERY = "query"
OPERATION_CHAT = "chat"
OPERATION_SUMMARIZE = "summarize"
OPERATION_VECTOR_SEARCH = "vector_search"
OPERATION_GENERATION = "generation"
OPERATION_CLASSIFICATION = "classification"
OPERATION_EXTRACTION = "extraction"
OPERATION_BATCH = "batch"      # Procesamiento por lotes (batch)
OPERATION_INTERNAL = "internal"  # Operaciones internas entre servicios

__all__ = [
    # Funciones principales de tracking
    'track_token_usage',
    'track_query',
    'track_usage',
    'track_operation',
    'estimate_prompt_tokens',
    'track_embedding_usage',
    
    # Constantes de tipos de tokens
    'TOKEN_TYPE_LLM',
    'TOKEN_TYPE_EMBEDDING',
    'TOKEN_TYPE_FINE_TUNING',
    
    # Constantes de tipos de operación
    'OPERATION_QUERY',
    'OPERATION_CHAT',
    'OPERATION_SUMMARIZE',
    'OPERATION_VECTOR_SEARCH',
    'OPERATION_GENERATION',
    'OPERATION_CLASSIFICATION',
    'OPERATION_EXTRACTION',
    
    # Servicios de atribución
    'TokenAttributionService',
    
    # Reconciliación y consolidación
    'reconcile_pending_tokens',
    'consolidate_counters',
    'audit_token_counters',
    
    # Alertas
    'register_alert',
    'AlertLevel',
    
    # Tareas programadas
    'run_daily_reconciliation',
    'run_weekly_consolidation',
    'run_monthly_audit',
    'register_reconciliation_tasks'
]
