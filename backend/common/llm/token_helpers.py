"""
Utilidades adicionales para trabajar con tokens.
"""

def estimate_max_tokens_for_model(model_name: str) -> int:
    """
    Estima el máximo de tokens para un modelo específico.
    """
    model_limits = {
        "gpt-3.5-turbo": 4096,
        "gpt-4": 8192,
        "gpt-4-turbo": 16384,
        "llama3": 8192,
        "claude-3-opus": 32768,
        "claude-3-sonnet": 16384
    }
    
    for key, limit in model_limits.items():
        if key in model_name.lower():
            return limit
    
    # Por defecto, un valor conservador
    return 4096