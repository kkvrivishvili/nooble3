import logging
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings
from common.errors import setup_error_handling, handle_service_error_simple, ServiceError
from common.utils.logging import init_logging
from common.context import Context
from common.db.supabase import init_supabase
from common.swagger import configure_swagger_ui
from common.cache.redis import get_redis_client
from common.utils.rate_limiting import setup_rate_limiting

# Importar rutas
from routes.query import router as query_router
from routes.collections import router as collections_router
from routes.internal import router as internal_router
from routes.health import router as health_router

# Configuración
settings = get_settings()
logger = logging.getLogger("query_service")
init_logging(settings.log_level)

# Variable global para registrar el inicio del servicio
service_start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    try:
        logger.info(f"Inicializando servicio de {settings.service_name}")
        
        # Inicializar Supabase
        init_supabase()
        
        # Verificar conexión a Redis para caché
        redis = await get_redis_client()
        if redis:
            logger.info("Conexión a Redis establecida correctamente")
        else:
            logger.warning("No se pudo conectar a Redis - servicio funcionará sin caché")
        
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
    title="Linktree AI - Query Service",
    description="""
    Servicio de consulta RAG (Retrieval Augmented Generation) para la plataforma Linktree AI.
    
    ## Funcionalidad
    - Búsqueda semántica de documentos por similitud vectorial
    - Generación de respuestas basadas en contexto recuperado
    - Soporte para diferentes estrategias de recuperación y sintetización
    - Múltiples motores LLM (OpenAI, Ollama) con configuración por tenant
    
    ## Dependencias
    - Redis: Para caché y almacenamiento temporal
    - Supabase: Para almacenamiento de vectores y configuración
    - Embedding Service: Para generación de embeddings de consultas
    - Ingestion Service: Para ingesta y procesamiento de documentos
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
    service_name="Query Service",
    service_description="API de consulta RAG especializada para búsqueda semántica y recuperación de información",
    version=settings.service_version,
    tags=[
        {"name": "Health", "description": "Verificación de estado y salud del servicio"},
        {"name": "Collections", "description": "Gestión de colecciones de documentos"},
        {"name": "Query", "description": "Operaciones de consulta y recuperación de información"},
        {"name": "Internal", "description": "Endpoints internos para consumo por otros servicios"}
    ]
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar manejo de errores y rate limiting
setup_error_handling(app)
setup_rate_limiting(app)

# Registrar rutas
app.include_router(health_router, tags=["Health"])
app.include_router(collections_router, prefix="/collections", tags=["Collections"])
app.include_router(query_router, tags=["Query"])
app.include_router(internal_router, prefix="/internal", tags=["Internal"])

# Para desarrollo local
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)