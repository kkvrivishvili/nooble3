# Configuración Centralizada del Servicio de Embeddings

Este directorio contiene la configuración centralizada específica para el servicio de embeddings, siguiendo el principio de que cada servicio debe manejar su propia configuración especializada.

## Estructura

- `__init__.py`: Expone todas las constantes y configuraciones para uso en el servicio
- `constants.py`: Define valores constantes como dimensiones, umbrales, endpoints y timeouts
- `settings.py`: Implementa la clase `EmbeddingServiceSettings` que extiende la configuración base

## Configuraciones Específicas del Servicio

Las siguientes configuraciones han sido **movidas de la configuración global** a este servicio:

| Configuración | Descripción | Valor Predeterminado |
|---------------|-------------|----------------------|
| `embedding_dimensions` | Dimensiones por modelo | Mapa detallado por modelo |
| `default_embedding_dimension` | Dimensión predeterminada | 1536 |
| `default_embedding_model` | Modelo predeterminado OpenAI | "text-embedding-3-small" |
| `default_ollama_embedding_model` | Modelo predeterminado Ollama | "nomic-embed-text" |
| `embedding_cache_ttl` | TTL para caché | 604800 (7 días) |
| `embedding_cache_enabled` | Habilita/deshabilita caché | True |
| `embedding_batch_size` | Tamaño de lote predeterminado | 128 |
| `max_batch_size` | Tamaño máximo de lote | 10 |
| `max_tokens_per_batch` | Tokens máximos por lote | 50000 |
| `max_token_length_per_text` | Longitud máxima por texto | 8000 |
| `max_input_length` | Longitud máxima de entrada | 32000 |
| `allow_batch_processing` | Permite procesamiento por lotes | True |

## Constantes Importantes

El archivo `constants.py` define varias constantes cruciales:

1. **EMBEDDING_DIMENSIONS**: Dimensiones de vectores por modelo
2. **QUALITY_THRESHOLDS**: Umbrales para validación de calidad
3. **CACHE_EFFICIENCY_THRESHOLDS**: Parámetros para medir eficiencia de caché
4. **OLLAMA_API_ENDPOINTS**: Rutas de API de Ollama
5. **TIMEOUTS**: Tiempos de espera para operaciones
6. **METRICS_CONFIG**: Configuración para métricas y monitoreo

## Variables de Entorno

El servicio usa las siguientes variables de entorno:

- `USE_OLLAMA`: Define si se usa Ollama (compartida con otros servicios)
- `DEFAULT_OLLAMA_EMBEDDING_MODEL`: Modelo de embedding predeterminado para Ollama
- `OLLAMA_API_URL`: URL de la API de Ollama (compartida)

## Principio de Diseño

Esta configuración específica del servicio sigue el principio de que cada servicio debe manejar su propia configuración especializada para:

1. Reducir acoplamiento entre servicios
2. Facilitar la evolución independiente de cada servicio
3. Eliminar código muerto o configuraciones innecesarias
4. Mejorar claridad y mantenimiento del código

La configuración global en `common/config/settings.py` ahora solo debe contener configuraciones verdaderamente compartidas entre servicios.
