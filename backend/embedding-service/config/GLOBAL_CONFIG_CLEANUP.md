# Propuesta de Limpieza de Configuración Global

Este documento detalla las configuraciones que deberían eliminarse de `common/config/settings.py` una vez que todos los servicios hayan migrado a su configuración específica.

## Configuraciones a Eliminar Relacionadas con Embeddings

Una vez que el servicio de embeddings esté completamente migrado a su propia configuración, las siguientes configuraciones pueden considerarse *código muerto* en `common/config/settings.py`:

```python
# =========== Embeddings ===========
embedding_batch_size: int = Field(128, description="Tamaño de lote para embeddings")
embedding_dimensions: int = Field(1536, description="Dimensiones de embeddings")
embedding_cache_ttl: int = Field(604800, description="TTL para caché de embeddings (7 días)")
max_embedding_batch_size: int = Field(10, description="Máximo tamaño de lote para API de embeddings")
embedding_cache_enabled: bool = Field(True, description="Habilitar caché para embeddings")
```

## Consideraciones sobre Modelos de Embedding

La configuración global actualmente define los modelos predeterminados para embeddings:

```python
default_embedding_model: str = Field("text-embedding-3-small", env="DEFAULT_OPENAI_EMBEDDING_MODEL")
default_ollama_embedding_model: str = Field("nomic-embed-text", env="DEFAULT_OLLAMA_EMBEDDING_MODEL")
```

Estas configuraciones se mantienen por ahora porque:

1. Son utilizadas por otros servicios para referenciar modelos
2. Están vinculadas a variables de entorno compartidas
3. Proporcionan valores predeterminados para toda la aplicación

**Recomendación**: Mantener estas configuraciones en el archivo global, pero eventualmente los otros servicios deberían obtener estos valores a través de API desde el servicio de embeddings, no directamente de la configuración.

## Variables de Entorno a Considerar

El archivo `docker-compose.yml` sigue definiendo variables relacionadas con embeddings para todos los servicios:

```yaml
- DEFAULT_OLLAMA_EMBEDDING_MODEL=${DEFAULT_OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}
```

**Recomendación**: A largo plazo, establecer variables de entorno específicas por servicio. Por ejemplo:

```yaml
# Para embedding-service
- EMBEDDING_DEFAULT_MODEL=${DEFAULT_OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}

# Para query-service 
- QUERY_DEFAULT_MODEL=${DEFAULT_OLLAMA_LLM_MODEL:-qwen3:1.7b}
```

## Plan de Migración Completo

1. Migrar cada servicio a su propia configuración específica
2. Actualizar referencias a la configuración global en el código
3. Crear un periodo de transición donde ambas configuraciones coexistan
4. Eliminar las configuraciones específicas de la configuración global
5. Actualizar las variables de entorno para que sean específicas por servicio

## Hoja de Ruta para Refactorización

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Migrar configuración específica de embeddings | Completado |
| 2 | Migrar configuración específica de query | Pendiente |
| 3 | Migrar configuración específica de agent | Pendiente |
| 4 | Migrar configuración específica de ingestion | Pendiente |
| 5 | Periodo de transición y pruebas | Pendiente |
| 6 | Limpieza de código muerto en configuración global | Pendiente |

## Beneficios de Esta Aproximación

1. **Responsabilidad única**: Cada servicio gestiona su propia configuración
2. **Mantenibilidad mejorada**: Los cambios en un servicio no afectan a otros
3. **Claridad de código**: Se elimina el código muerto y las redundancias
4. **Menor acoplamiento**: Los servicios dependen menos unos de otros
5. **Escalabilidad**: Facilita añadir nuevos servicios o modificar los existentes
