# Patrones de Caché en Ingestion Service

## Introducción

Este documento describe la implementación de patrones de caché en el servicio de ingestion, siguiendo los estándares establecidos en las memorias del sistema para garantizar consistencia entre servicios.

## Principios clave implementados

1. **Patrón Cache-Aside centralizado**: Usamos `get_with_cache_aside()` para toda la lógica de caché, simplificando el código y garantizando consistencia.
2. **Jerarquía de claves**: Siempre incluimos `tenant_id` y `collection_id` cuando corresponde para mantener el aislamiento entre tenants.
3. **TTL estándar**: Utilizamos las constantes definidas (`CacheManager.ttl_standard`, `CacheManager.ttl_extended`) en lugar de valores hardcodeados.
4. **Serialización estándar**: Aplicamos `serialize_for_cache()` cuando es necesario para mantener consistencia.
5. **Métricas**: Capturamos métricas de rendimiento de caché para análisis y monitoreo.

## Implementaciones por módulo

### services/extraction.py

En `process_file_from_storage()`:
- **Patrón**: Cache-Aside para archivos descargados de storage
- **Objetivo**: Evitar descargar el mismo archivo múltiples veces
- **TTL**: `CacheManager.ttl_extended` (24 horas)
- **Claves**: `resource_id=f"file:{file_key}"`, `tenant_id`, `collection_id`

### services/queue.py

En `get_job_status()`:
- **Patrón**: Cache-Aside para estados de trabajos
- **Objetivo**: Acelerar consultas frecuentes sobre el estado de trabajos
- **TTL**: Por defecto para tipo "job_status"
- **Claves**: `resource_id=job_id`, `tenant_id`

### services/storage.py

En `update_document_status()` y `update_processing_job()`:
- **Patrón**: Invalidación directa con `CacheManager.delete()` o `CacheManager.set()`
- **Objetivo**: Mantener consistencia al actualizar estados
- **TTL**: `CacheManager.ttl_extended` para job_status

### services/llama_extractors.py

En `process_text_with_llama_index()`:
- **Patrón**: Cache-Aside para resultados de procesamiento de texto
- **Objetivo**: Evitar reprocesamiento de textos idénticos
- **TTL**: Por defecto para tipo "processed_text"
- **Claves**: `resource_id=f"text:{text_hash}"`, `tenant_id`, `collection_id`

En `process_upload_with_llama_index()`:
- **Patrón**: Cache-Aside para resultados de procesamiento de archivos
- **Objetivo**: Evitar reprocesamiento del mismo archivo
- **TTL**: Por defecto para tipo "processed_file" 
- **Claves**: `resource_id=f"file:{file_key}"`, `tenant_id`, `collection_id`

## Métricas y monitoreo

El patrón Cache-Aside implementado registra automáticamente métricas como:
- Aciertos de caché (`cache_hit`)
- Operaciones en caché (`cache_operations`)
- Tiempos de respuesta (`latency`)

Estas métricas son accesibles a través del contexto (`ctx.add_metric()`) y se pueden utilizar para monitorear y optimizar el rendimiento.

## Referencias

- [Memoria: Uso Estandarizado del CacheManager para Servicios RAG](memory:6c9efbf8-98d9-4d1c-b073-a09823e56a5d)
- [Memoria: Implementación por Servicio del Patrón Cache-Aside](memory:1990c4da-39e0-4cdb-94e7-0dfdb25110ee)
