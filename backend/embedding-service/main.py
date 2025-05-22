"""
Punto de entrada del servicio de embeddings.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.db.supabase import init_supabase
from config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    logger.info(f"Iniciando {settings.service_name}")
    
    # Inicializar Supabase (para tracking)
    await init_supabase()
    
    yield
    
    logger.info(f"{settings.service_name} detenido")

# Crear aplicación
app = FastAPI(
    title="Embedding Service",
    description="Servicio para generación de embeddings con OpenAI",
    version=settings.service_version,
    lifespan=lifespan
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

# Registrar rutas
from routes.embeddings import router as embeddings_router
app.include_router(embeddings_router, prefix="/api/v1", tags=["Embeddings"])

# Registrar health checks estándar
from common.helpers.health import register_health_routes
register_health_routes(app)

# Configurar logging
init_logging(settings.log_level, service_name="embedding-service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
