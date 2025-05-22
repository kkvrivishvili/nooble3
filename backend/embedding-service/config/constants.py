"""
Constantes centralizadas para el servicio de embeddings.

Este archivo define todas las constantes y valores de configuración
que anteriormente estaban hardcodeados en diferentes partes del código.
"""

from typing import Dict, List, Any

# Información completa sobre modelos de embeddings
# Referencia: https://platform.openai.com/docs/guides/embeddings
OPENAI_EMBEDDING_MODELS = {
    "text-embedding-3-small": {
        "dimensions": 1536,
        "max_tokens": 8191,        # Límite de tokens por solicitud
        "max_batch_size": 2048,     # Máximo número de textos por lote
        "input_cost": 0.00002,      # Costo por 1K tokens de entrada ($0.00002/1K tokens)
        "tiers": ["free", "standard", "pro", "business", "enterprise"],
        "description": "Modelo de embeddings para uso general con excelente balance rendimiento/costo"
    },
    "text-embedding-3-large": {
        "dimensions": 3072,
        "max_tokens": 8191,        # Límite de tokens por solicitud
        "max_batch_size": 2048,     # Máximo número de textos por lote
        "input_cost": 0.00013,      # Costo por 1K tokens de entrada ($0.00013/1K tokens)
        "tiers": ["pro", "business", "enterprise"],
        "description": "Modelo de alta precisión para tareas complejas que requieren máxima fidelidad"
    },
    # Modelos legacy (mantenidos para compatibilidad)
    "text-embedding-ada-002": {
        "dimensions": 1536,
        "max_tokens": 8191,
        "max_batch_size": 2048,
        "input_cost": 0.0001,
        "tiers": ["free", "standard", "pro", "business", "enterprise"],
        "description": "Obsoleto, reemplazado por text-embedding-3-small"
    }
}

# Helper para acceder fácilmente a las dimensiones de los modelos
EMBEDDING_DIMENSIONS: Dict[str, int] = {
    model: info["dimensions"] for model, info in OPENAI_EMBEDDING_MODELS.items()
}

# Valor predeterminado para dimensiones de embeddings no conocidas
DEFAULT_EMBEDDING_DIMENSION: int = 1536

# Umbrales para verificación de calidad de embeddings
QUALITY_THRESHOLDS = {
    # Número mínimo de valores distintos en los primeros N elementos
    "min_distinct_values": 3,
    "distinct_values_sample_size": 10,
    
    # Valor absoluto máximo permitido en embeddings normalizados
    "max_absolute_value": 100.0,
    
    # Tolerancia para norma del vector (debe estar cerca de 1.0)
    "norm_tolerance": 0.2
}

# Umbrales para eficiencia de caché
CACHE_EFFICIENCY_THRESHOLDS = {
    # Mínimo número de requests para considerar métricas válidas
    "min_requests": 10,
    
    # Hit ratio para considerar el servicio en diferentes estados
    "good_hit_ratio": 0.5,  # >= 50% es "available"
    "degraded_hit_ratio": 0.2  # >= 20% es "degraded", < 20% también "degraded"
}

# Nota: Ollama ha sido eliminado como proveedor soportado.
# Actualmente solo se usa OpenAI como proveedor de embeddings.

# Timeouts para diferentes operaciones
TIMEOUTS = {
    # Tiempo de espera para operaciones de generación de embeddings (segundos)
    "embedding_generation": 30.0,
    
    # Tiempo de espera para llamadas a la API de embedding (segundos)
    "embedding_api": 45.0,
    
    # Tiempo de espera para health checks (segundos)
    "health_check": 5.0,
    
    # Tiempo de espera para verificación de modelos (segundos)
    "model_check": 5.0
}

# Valores simulados para métricas cuando no hay datos reales
MOCK_METRICS = {
    # Tokens promedio por solicitud para estadísticas simuladas
    "avg_tokens_per_request": 500
}

# Definición de tipos de tareas de embedding
# Cada tipo tiene configuración específica y modelo recomendado
EMBEDDING_TASK_TYPES = {
    "rag_query": {
        "description": "Consulta para RAG (Retrieval Augmented Generation)",
        "default_model": "text-embedding-3-small",
        "preferred_model": "text-embedding-3-large",
        "normalize": True,
        "truncate_strategy": "end",
        "similarity_threshold": 0.7
    },
    "semantic_search": {
        "description": "Búsqueda semántica general",
        "default_model": "text-embedding-3-small", 
        "preferred_model": "text-embedding-3-small",
        "normalize": True,
        "truncate_strategy": "end",
        "similarity_threshold": 0.65
    },
    "classification": {
        "description": "Clasificación de textos",
        "default_model": "text-embedding-3-small",
        "preferred_model": "text-embedding-3-large",
        "normalize": True,
        "truncate_strategy": "end",
        "similarity_threshold": 0.75
    },
    "clustering": {
        "description": "Agrupación de textos similares",
        "default_model": "text-embedding-3-small",
        "preferred_model": "text-embedding-3-large",
        "normalize": True,
        "truncate_strategy": "end",
        "similarity_threshold": 0.6
    },
    "reranking": {
        "description": "Reordenamiento de resultados para mayor precisión",
        "default_model": "text-embedding-3-large",
        "preferred_model": "text-embedding-3-large",
        "normalize": True,
        "truncate_strategy": "end",
        "similarity_threshold": 0.8
    }
}

# Estrategias de truncado
TRUNCATION_STRATEGIES = ["start", "end", "middle"]

# Valores por defecto para parámetros de embedding
DEFAULT_EMBEDDING_PARAMS = {
    "normalize": True,
    "truncate_strategy": "end",
    "truncate_to_n_tokens": None,
    "similarity_threshold": 0.7
}

# Intervalos de tiempo para rate limiting y verificaciones
TIME_INTERVALS = {
    # Tiempo hasta considerar que el rate limit ha expirado (segundos)
    "rate_limit_expiry": 300  # 5 minutos
}

# Configuración para métricas y muestreo
METRICS_CONFIG = {
    # Número máximo de muestras de latencia a almacenar
    "max_latency_samples": 1000,
    # Número mínimo de muestras para cálculo de percentiles
    "min_samples_for_percentiles": 5
}
