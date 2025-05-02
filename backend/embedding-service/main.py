"""
Punto de entrada para el servicio de embeddings.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Utilidades comunes para todos los servicios
from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.context import Context
from common.db.supabase import init_supabase
from common.swagger import configure_swagger_ui
from common.cache.manager import CacheManager
from common.utils.rate_limiting import setup_rate_limiting
from common.config.tiers import is_development_environment, should_use_mock_config

# Configuración centralizada
from config.settings import get_settings
from config.constants import TIMEOUTS
from routes import register_routes

# Configuración
settings = get_settings()
logger = logging.getLogger("embedding_service")
init_logging(settings.log_level, service_name="embedding-service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    try:
        logger.info(f"Inicializando servicio de {settings.service_name}")
        
        # Inicializar Supabase
        await init_supabase()
        
        # Verificar conexión al sistema de caché unificado
        try:
            await CacheManager.get(data_type="system", resource_id="health_check")
            logger.info("Conexión a Cache establecida correctamente")
        except Exception as e:
            logger.warning(f"Cache no disponible: {e}")
            logger.warning("Servicio funcionará sin caché")
        
        # Establecer contexto de servicio estándar
        async with Context(tenant_id=settings.default_tenant_id):
            # Cargar configuraciones específicas del servicio
            try:
                if settings.load_config_from_supabase:
                    # Cargar configuraciones...
                    logger.info(f"Configuraciones cargadas para {settings.service_name}")
            except Exception as config_err:
                logger.error(f"Error cargando configuraciones: {config_err}")
        
        logger.info(f"Servicio {settings.service_name} inicializado correctamente")
        yield
    except Exception as e:
        logger.error(f"Error al inicializar el servicio: {str(e)}")
        yield
    finally:
        # Limpieza de recursos
        logger.info(f"Servicio {settings.service_name} detenido correctamente")

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