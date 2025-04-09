"""
Punto de entrada principal para el servicio de ingesta (ingestion-service).

Este servicio se encarga de:
1. Recibir documentos
2. Procesar y extraer texto
3. Dividir en chunks
4. Generar embeddings (a través del embedding-service)
5. Almacenar los embeddings en la base de datos
"""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config.settings import get_settings
from common.errors import setup_error_handling, DatabaseError, ServiceError
from common.errors.exceptions import HTTPServiceError
from common.utils.logging import init_logging
from common.context import Context
from common.context.vars import get_current_tenant_id
from common.db.supabase import init_supabase
from common.cache.manager import CacheManager
from common.swagger import configure_swagger_ui
from common.cache.redis import get_redis_client
from common.utils.rate_limiting import setup_rate_limiting

# Evitar importación duplicada
from routes import register_routes
from services.queue import initialize_queue, shutdown_queue
from services.worker import start_worker_pool, stop_worker_pool

# Configuración
settings = get_settings()
logger = logging.getLogger("ingestion_service")
init_logging(settings.log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    try:
        logger.info(f"Inicializando servicio de {settings.service_name}")
        
        # Inicializar Supabase
        await init_supabase()
        
        # Verificar conexión a Redis para caché y colas mediante CacheManager
        cache_available = True
        try:
            # Intentar operación simple para verificar disponibilidad del cache
            await CacheManager.get(
                data_type="system",
                resource_id="health_check"
            )
            logger.info("Conexión a Cache establecida correctamente")
        except Exception as e:
            logger.warning(f"No se pudo conectar al sistema de caché: {str(e)}")
            cache_available = False
            logger.warning("El servicio funcionará sin caché y sin colas")
        
        # Inicializar sistema de colas
        await initialize_queue()
        
        # Establecer contexto de servicio estándar
        async with Context(tenant_id=settings.default_tenant_id):
            # Cargar configuraciones específicas del servicio
            try:
                if settings.load_config_from_supabase:
                    # Cargar configuraciones...
                    logger.info(f"Configuraciones cargadas para {settings.service_name}")
            except Exception as config_err:
                error_context = {"service": settings.service_name}
                logger.error(f"Error cargando configuraciones: {config_err}", extra=error_context)
        
        # Iniciar workers para procesamiento en segundo plano
        await start_worker_pool(settings.max_workers)
        
        logger.info(f"Servicio {settings.service_name} inicializado correctamente")
        yield
    except Exception as e:
        error_context = {"service": settings.service_name}
        logger.error(f"Error al inicializar el servicio: {str(e)}", exc_info=True, extra=error_context)
        yield
    finally:
        # Detener workers
        await stop_worker_pool()
        
        # Limpieza de recursos
        await shutdown_queue()
        logger.info(f"Servicio {settings.service_name} detenido correctamente")

async def process_batch(batch: list):
    """
    Procesa un lote de elementos.
    
    Args:
        batch: Lista de elementos a procesar
        
    Returns:
        dict: Resultado del procesamiento
        
    Raises:
        ServiceError: Si hay un error durante el procesamiento
        DatabaseError: Si hay un error de base de datos
    """
    if not batch:
        # Validación de entrada
        raise ServiceError(
            message="Batch vacío",
            error_code="EMPTY_BATCH",
            status_code=400,
            context={"batch_size": 0}
        )
    
    try:
        tenant_id = get_current_tenant_id()
        if not tenant_id or tenant_id == "default":
            raise ServiceError(
                message="Se requiere un tenant válido",
                error_code="TENANT_REQUIRED", 
                status_code=400,
                context={"tenant_id": tenant_id}
            )
            
        from common.auth.tenant import is_tenant_active
        if not await is_tenant_active(tenant_id):
            raise ServiceError(
                message="Tenant no activo",
                error_code="TENANT_INACTIVE",
                status_code=403,
                context={"tenant_id": tenant_id}
            )
            
        # Procesamiento del batch
        try:
            processed = await _process_items(batch)
            return processed
        except HTTPServiceError as http_err:
            # Capturar errores de llamadas a otros servicios
            logger.error(f"Error en servicio externo: {http_err.message}", extra=http_err.context)
            raise ServiceError(
                message=f"Error en servicio externo: {http_err.message}",
                error_code=http_err.error_code,
                status_code=http_err.status_code,
                context={**http_err.context, "batch_size": len(batch)}
            )
            
    except DatabaseError as db_err:
        # Los errores de DB ya tienen formato correcto, propagarlos directamente
        logger.error(f"Error de base de datos: {db_err.message}", extra=db_err.context)
        raise
    except ServiceError as svc_err:
        # Los errores de servicio ya tienen formato correcto, propagarlos directamente
        logger.error(f"Error de servicio: {svc_err.message}", extra=svc_err.context)
        raise
    except Exception as e:
        # Capturar errores inesperados y convertirlos al formato estándar
        error_context = {
            "batch_size": len(batch),
            "tenant_id": get_current_tenant_id(),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        logger.error(f"Error inesperado procesando lote: {str(e)}", extra=error_context, exc_info=True)
        raise ServiceError(
            message="Error procesando lote",
            error_code="INGESTION_ERROR",
            status_code=500,
            context=error_context
        )

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Linktree AI - Ingestion Service",
    description="""
    Servicio encargado de la ingesta y procesamiento de documentos para la plataforma Linktree AI.
    
    ## Funcionalidad
    - Carga y procesamiento de documentos (PDF, Word, Excel, texto, etc.)
    - División de documentos en fragmentos optimizados para RAG
    - Generación de embeddings a través del servicio de embeddings
    - Almacenamiento en base de datos vectorial
    - Procesamiento asíncrono en segundo plano
    
    ## Dependencias
    - Redis: Para caché y gestión de colas de procesamiento
    - Supabase: Para almacenamiento de metadatos y vectores
    - Embedding Service: Para generación de embeddings
    - Múltiples bibliotecas de procesamiento de documentos
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
    service_name="Ingestion Service",
    service_description="API para ingesta y procesamiento de documentos para RAG",
    version=settings.service_version,
    tags=[
        {"name": "Ingestion", "description": "Endpoints para carga y procesamiento de documentos"},
        {"name": "Documents", "description": "Gestión de documentos existentes"},
        {"name": "Jobs", "description": "Gestión de trabajos de procesamiento en segundo plano"},
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)