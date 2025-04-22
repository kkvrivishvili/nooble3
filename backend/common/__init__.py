"""
Biblioteca común para los servicios de LlamaIndex en la plataforma Linktree AI.
Proporciona funciones compartidas para autenticación, caché, rate limiting y más.
"""

# Importaciones principales para compatibilidad con código existente
from .auth import verify_tenant
from .cache import get_redis_client
from .config import get_settings
from .models import TenantInfo, HealthResponse
from .utils import rate_limiting
from .db import get_supabase_client
from .tracking import track_token_usage, track_embedding_usage
from .errors import setup_error_handling, handle_errors

# Aliases para mantener compatibilidad hacia atrás
from .auth import verify_tenant as verify_tenant
from .db import get_supabase_client as get_supabase_client
from .cache import get_redis_client as get_redis_client
from .config import get_settings as get_settings
from .models import TenantInfo as TenantInfo
from .models import HealthResponse as HealthResponse
from .utils.rate_limiting import apply_rate_limit as apply_rate_limit
from .tracking import track_token_usage as track_token_usage
from .tracking import track_embedding_usage as track_embedding_usage
from .errors import setup_error_handling as setup_error_handling
from .errors import handle_errors as handle_errors

# Exportar todos los símbolos importantes para mantener compatibilidad
__all__ = [
    'verify_tenant',
    'get_redis_client',
    'get_settings',
    'TenantInfo',
    'HealthResponse',
    'apply_rate_limit',
    'get_supabase_client',
    'track_token_usage',
    'track_embedding_usage',
    'setup_error_handling',
    'handle_errors',
]