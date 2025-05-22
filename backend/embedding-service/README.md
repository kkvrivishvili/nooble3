# Embedding Service

## Descripción

Embedding Service es un microservicio optimizado que proporciona capacidades de generación de embeddings vectoriales para el sistema RAG (Retrieval Augmented Generation). El servicio está diseñado siguiendo principios de simplicidad y eficiencia, exponiendo una API interna para uso exclusivo de otros servicios del sistema.

## Características

- Generación de embeddings de alta calidad utilizando modelos de OpenAI
- Único endpoint optimizado para facilitar la integración
- Soporte para tracking centralizado de tokens
- Validaciones de seguridad y límites de uso
- Manejo de errores estandarizado

## Arquitectura

El servicio sigue una arquitectura simplificada:

```
Agent Service
    ↓
EnhancedEmbeddingRequest
    ↓
Embedding Service (validate)
    ↓
OpenAI Provider (generate)
    ↓
EnhancedEmbeddingResponse
    ↓
Agent Service → Query Service
```

### Componentes Principales

- **models/embeddings.py**: Definición de modelos de request/response
- **provider/openai.py**: Implementación del proveedor de OpenAI
- **routes/embeddings.py**: Endpoint único de API
- **config/settings.py**: Configuraciones centralizadas
- **main.py**: Punto de entrada de la aplicación FastAPI

## Instalación

```bash
# Clonar el repositorio
git clone <repositorio>

# Instalar dependencias
cd embedding-service
pip install -r requirements.txt

# Ejecutar el servicio
uvicorn main:app --host 0.0.0.0 --port 8001
```

## Configuración

El servicio utiliza variables de entorno para la configuración:

- `OPENAI_API_KEY`: Clave de API para OpenAI (requerida)
- `DEFAULT_EMBEDDING_MODEL`: Modelo predeterminado (default: "text-embedding-3-small")
- `MAX_BATCH_SIZE`: Tamaño máximo de lote (default: 100)
- `MAX_TEXT_LENGTH`: Longitud máxima de texto (default: 8000)
- `OPENAI_TIMEOUT_SECONDS`: Timeout para llamadas a OpenAI (default: 30)

## API

### Endpoint: `/api/v1/internal/enhanced_embed`

**Método**: POST

**Descripción**: Genera embeddings para los textos proporcionados.

**Request Body**:

```json
{
  "texts": ["Texto para generar embedding"],
  "model": "text-embedding-3-large",  // Opcional
  "tenant_id": "tenant123",
  "collection_id": "collection456",  // Opcional, para tracking
  "chunk_ids": ["chunk1", "chunk2"],  // Opcional, para tracking
  "metadata": {                       // Opcional
    "source": "agent_service",
    "purpose": "query"
  }
}
```

**Response**:

```json
{
  "success": true,
  "message": "Embeddings generados correctamente",
  "embeddings": [[0.1, 0.2, ...]],
  "model": "text-embedding-3-large",
  "dimensions": 3072,
  "processing_time": 0.156,
  "total_tokens": 10
}
```

## Integración con Agent Service

El Agent Service utiliza este servicio como herramienta para generar embeddings de consultas y respuestas en el flujo RAG. La integración típica es:

### Ejemplo de Código de Integración:

```python
import httpx
from models import EnhancedEmbeddingRequest

async def get_embeddings_for_query(query_text, tenant_id, collection_id=None):
    """Obtiene embeddings para una consulta de usuario."""
    
    request = EnhancedEmbeddingRequest(
        texts=[query_text],
        tenant_id=tenant_id,
        collection_id=collection_id,
        metadata={"source": "agent_service", "purpose": "query"}
    )
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://embedding-service:8001/api/v1/internal/enhanced_embed",
            json=request.dict(exclude_none=True)
        )
        
    if response.status_code == 200:
        result = response.json()
        return result["embeddings"][0]  # Primer embedding
    else:
        raise ValueError(f"Error en embedding service: {response.text}")
```

## Flujo de Trabajo en el Sistema RAG

1. **Agent Service** recibe consulta del usuario
2. **Agent Service** solicita embeddings al **Embedding Service**
3. **Embedding Service** genera vectores utilizando OpenAI
4. **Agent Service** utiliza embeddings para buscar en el **Query Service**
5. **Query Service** encuentra documentos relevantes
6. **Agent Service** genera respuesta con contexto enriquecido

## Monitoreo y Métricas

El servicio registra automáticamente:
- Uso de tokens por tenant y modelo
- Tiempos de respuesta
- Errores y excepciones

## Soporte de Modelos

El servicio soporta los siguientes modelos de OpenAI:

| Modelo | Dimensiones | Recomendado para |
|--------|------------|------------------|
| text-embedding-3-small | 1536 | Uso general, mejor balance costo/rendimiento |
| text-embedding-3-large | 3072 | Alta precisión, tareas complejas |
| text-embedding-ada-002 | 1536 | Compatibilidad con sistemas legacy |

## Buenas Prácticas

1. **Batch de solicitudes**: Cuando sea posible, enviar múltiples textos en una sola solicitud.
2. **Tamaño de texto**: Mantener textos dentro de límites razonables (<8000 caracteres).
3. **Tenant ID**: Siempre especificar un tenant_id válido para tracking correcto.
4. **Manejo de errores**: Implementar reintentos con backoff exponencial para errores transitorios.
