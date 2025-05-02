"""
Constantes centralizadas para el servicio de embeddings.

Este archivo define todas las constantes y valores de configuración
que anteriormente estaban hardcodeados en diferentes partes del código.
"""

from typing import Dict, List, Any

# Dimensiones de embeddings por modelo
EMBEDDING_DIMENSIONS: Dict[str, int] = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "ada": 1024,
    "llama2": 4096,
    "mistral": 4096,
    "nomic-embed-text": 768  # Dimensión del modelo nomic-embed-text
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

# Endpoints de API de Ollama
OLLAMA_API_ENDPOINTS = {
    "embeddings": "/api/embeddings",
    "health": "/api/health",
    "models": "/api/tags",
    "model_info": "/api/show"
}

# Timeouts para diferentes operaciones
TIMEOUTS = {
    # Tiempo de espera para operaciones de generación de embeddings (segundos)
    "embedding_generation": 30.0,
    
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
