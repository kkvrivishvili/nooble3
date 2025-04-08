import logging
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config import get_settings
from common.errors import setup_error_handling
from common.utils.logging import init_logging
from common.context import Context
from common.db.supabase import init_supabase
from common.swagger import configure_swagger_ui, add_example_to_endpoint
from common.cache.redis import get_redis_client
from common.utils.rate_limiting import setup_rate_limiting
from common.utils.http import check_service_health

from routes import register_routes

# Configuración
settings = get_settings()
logger = logging.getLogger("agent_service")
init_logging(settings.log_level)

# Cliente HTTP compartido
http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    global http_client
    
    try:
        logger.info(f"Inicializando servicio de agentes con URL Supabase: {settings.supabase_url}")
        
        # Inicializar Supabase
        init_supabase()
        
        # Verificar conexión a Redis para caché
        redis = await get_redis_client()
        if redis:
            logger.info("Conexión a Redis establecida correctamente")
        else:
            logger.warning("No se pudo conectar a Redis - servicio funcionará sin caché")
        
        # Inicializar cliente HTTP
        http_client = httpx.AsyncClient(timeout=30.0)
        
        # Verificar servicios dependientes usando la función común
        if settings.environment != "development":
            dependencies = {
                "query-service": settings.query_service_url,
                "embedding-service": settings.embedding_service_url
                # "ingestion-service": settings.ingestion_service_url # Descomentar cuando se use
            }
            for service_name, service_url in dependencies.items():
                is_healthy = await check_service_health(service_url, service_name)
                if is_healthy:
                    logger.info(f"Conexión a {service_name} establecida correctamente")
                else:
                    logger.warning(f"No se pudo conectar a {service_name} - funcionalidad podría estar limitada")
        
        logger.info("Servicio de agentes inicializado correctamente")
        yield
    except Exception as e:
        logger.error(f"Error al inicializar el servicio de agentes: {str(e)}")
        yield
    finally:
        # Cerrar cliente HTTP
        if http_client:
            await http_client.aclose()
        logger.info("Servicio de agentes detenido correctamente")

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Linktree AI - Agent Service",
    description="""
    Servicio para gestión de agentes conversacionales inteligentes.
    
    ## Funcionalidad
    - Creación y configuración de agentes con diferentes capacidades
    - Gestión de conversaciones y contexto
    - Interacción con conocimiento externo mediante RAG
    - Exposición de agentes mediante API pública
    
    ## Dependencias
    - Redis: Para caché y gestión de sesiones
    - Supabase: Para almacenamiento de configuración
    - Embedding Service: Para generación de embeddings
    - Query Service: Para consultas RAG
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
    service_name="Agent Service",
    service_description="API para gestión de agentes conversacionales inteligentes",
    version=settings.service_version,
    tags=[
        {"name": "Agents", "description": "Operaciones de gestión de agentes"},
        {"name": "Conversations", "description": "Operaciones de gestión de conversaciones"},
        {"name": "Chat", "description": "Endpoints de interacción conversacional"},
        {"name": "Admin", "description": "Operaciones administrativas"}
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

# Agregar ejemplos para Swagger
add_example_to_endpoint(
    app=app,
    path="/agents",
    method="get",
    response_example={
        "success": True,
        "message": "Agentes obtenidos exitosamente",
        "agents": [
            {
                "agent_id": "ag_123456789",
                "name": "Customer Support Agent",
                "description": "Asistente para soporte al cliente",
                "model": "gpt-3.5-turbo",
                "is_public": False,
                "created_at": "2023-06-15T10:30:45Z",
                "updated_at": "2023-06-15T10:30:45Z"
            }
        ],
        "count": 1
    }
)

add_example_to_endpoint(
    app=app,
    path="/chat",
    method="post",
    request_example={
        "message": "¿Cómo puedo restablecer mi dispositivo?",
        "agent_id": "ag_123456789",
        "conversation_id": "conv_987654321",
        "context": {"product_id": "XYZ-100"},
        "stream": False
    },
    response_example={
        "success": True,
        "message": "Consulta procesada exitosamente",
        "conversation_id": "conv_987654321",
        "message": {
            "role": "assistant",
            "content": "Para restablecer tu dispositivo XYZ-100, sigue estos pasos...",
            "metadata": {
                "processing_time": 0.853
            }
        },
        "thinking": "El usuario quiere saber cómo restablecer el dispositivo...",
        "tools_used": ["search_documentation"],
        "processing_time": 0.853,
        "sources": [
            {
                "document_id": "doc_456789",
                "document_name": "Manual_XYZ-100.pdf",
                "page": 42
            }
        ]
    }
)

# Exponer cliente HTTP para otros módulos
def get_http_client():
    return http_client

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)