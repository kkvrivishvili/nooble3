"""
Punto de entrada para el servicio de embeddings.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings, is_development_environment, should_use_mock_config
from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.context import Context
from common.db.supabase import init_supabase
from common.swagger import configure_swagger_ui
from common.cache.redis import get_redis_client
from common.utils.rate_limiting import setup_rate_limiting

from config import get_settings
from routes import register_routes

# Configuración
settings = get_settings()
logger = logging.getLogger("embedding_service")
init_logging(settings.log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    try:
        logger.info(f"Inicializando servicio de embeddings con URL Supabase: {settings.supabase_url}")
        
        # Inicializar Supabase
        init_supabase()
        
        # Verificar conexión a Redis para caché
        redis = await get_redis_client()
        if redis:
            logger.info("Conexión a Redis establecida correctamente")
        else:
            logger.warning("No se pudo conectar a Redis - servicio funcionará sin caché")
        
        # Cargar configuraciones específicas con contexto
        ctx = Context(tenant_id=settings.default_tenant_id)
        async with ctx:
            # Cargar configuraciones específicas del servicio
            try:
                if settings.load_config_from_supabase or is_development_environment():
                    from common.db.supabase import get_effective_configurations
                    
                    service_settings = await get_effective_configurations(
                        tenant_id=settings.default_tenant_id,
                        service_name="embedding",
                        environment=settings.environment
                    )
                    
                    if service_settings:
                        logger.info(f"Configuraciones cargadas para servicio de embeddings: {len(service_settings)} parámetros")
                    else:
                        logger.warning("No se encontraron configuraciones específicas para el servicio")
                        
                    # Si no hay configuraciones y está habilitado mock, usar configuraciones de desarrollo
                    if not service_settings and should_use_mock_config():
                        logger.warning("Usando configuración mock para desarrollo")
                        settings.use_mock_if_empty(service_name="embedding")
            except Exception as config_err:
                logger.error(f"Error cargando configuraciones: {config_err}")
        
        logger.info("Servicio de embeddings inicializado correctamente")
        yield
    except Exception as e:
        logger.error(f"Error al inicializar el servicio de embeddings: {str(e)}")
        yield
    finally:
        # Limpiar recursos al cerrar
        logger.info("Servicio de embeddings detenido correctamente")

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Linktree AI - Embedding Service",
    description="""
    Servicio encargado de generar embeddings vectoriales para texto.
    
    ## Funcionalidad
    - Generación de embeddings unitarios y por lotes
    - Soporte para múltiples modelos de embeddings (OpenAI, Ollama)
    - Aislamiento multi-tenant con caché por tenant
    
    ## Dependencias
    - Redis: Para caché de embeddings
    - Supabase: Para almacenamiento de configuración
    - Ollama (opcional): Para modelos locales de embeddings
    - OpenAI API (opcional): Para modelos en la nube
    """,
    version=settings.service_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configurar Swagger UI
configure_swagger_ui(
    app=app,
    service_name="Embedding Service",
    service_description="API para generación de embeddings vectoriales de alta calidad para texto",
    version=settings.service_version,
    tags=[
        {"name": "Embeddings", "description": "Operaciones de generación de embeddings"},
        {"name": "Models", "description": "Gestión de modelos de embeddings"},
        {"name": "Health", "description": "Verificación de salud del servicio"}
    ]
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar manejo de errores
setup_error_handling(app)

# Configurar rate limiting
setup_rate_limiting(app)

# Registrar rutas
register_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)