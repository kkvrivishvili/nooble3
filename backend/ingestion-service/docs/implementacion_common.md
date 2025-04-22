# Implementación de Módulos Common en Ingestion Service

Este documento describe la implementación de los módulos compartidos de `common` en el servicio de ingestión, detallando cómo se han aplicado los patrones estándar y los puntos específicos de integración.

## 1. Manejo de Errores

El servicio implementa el patrón unificado de manejo de errores a través del decorador `@handle_errors`:

- **Endpoints públicos**: Utilizan `@handle_errors(error_type="simple", log_traceback=False)` para errores simplificados.
- **Servicios internos**: Utilizan `@handle_errors(error_type="service", log_traceback=True)` para capturar todos los detalles.
- **Ejemplo**: 
  ```python
  @router.post("/upload")
  @with_context(tenant=True, collection=True)
  @handle_errors(error_type="simple", log_traceback=False)
  async def upload_document(...):
  ```

## 2. Contexto Multitenancy

El servicio usa el sistema unificado de contexto para validación de tenant:

- **Decorador `@with_context`**: Aplicado en todos los endpoints que requieren validación de tenant.
- **Acceso al contexto**: A través del objeto `ctx` pasado a las funciones.
- **Validación de tenant**: Implementada en todos los puntos críticos del servicio.
- **Ejemplo**:
  ```python
  @with_context(tenant=True, collection=True)
  async def queue_document_processing_job(tenant_id: str, ...):
      # El tenant_id ya ha sido validado por @with_context
  ```

## 3. Tracking de Tokens

El servicio implementa el tracking centralizado de tokens para contabilizar uso en embeddings:

- **Función unificada**: Uso de `track_token_usage` con parámetros estandarizados.
- **Tipos de operaciones**: Se registran tanto operaciones de generación como hits de caché.
- **Metadatos enriquecidos**: Se incluyen metadatos como tiempos de procesamiento y conteos.
- **Ejemplo**:
  ```python
  await track_token_usage(
      tenant_id=tenant_id,
      tokens=total_tokens,
      model=model_name,
      token_type="embedding",
      operation="generate",
      metadata={
          "texts_count": len(texts_to_process),
          "processing_time": processing_time
      }
  )
  ```

## 4. Configuración y Tiers

El servicio usa la estructura centralizada de configuraciones:

- **Configuraciones de tier**: A través de `get_tier_limits` importado directamente de `common.config.tiers`.
- **Verificación de modelos**: Se usan `get_available_embedding_models` para validar acceso a modelos.
- **Límites de procesamiento**: Validación contra límites como `max_docs` según el tier.
- **Ejemplo**:
  ```python
  tier_limits = get_tier_limits(tenant_info.tier, tenant_id=tenant_id)
  max_docs = tier_limits.get("max_docs", 999999)
  ```

## 5. Gestión de Caché

El servicio utiliza el `CacheManager` para todas las operaciones de caché:

- **Verificación de embeddings**: Se consulta la caché antes de generar nuevos embeddings.
- **Almacenamiento consistente**: Se utilizan claves estandarizadas para compatibilidad entre servicios.
- **Ejemplo**:
  ```python
  val = await CacheManager.get(
      data_type="embedding",
      resource_id=resource_id,
      tenant_id=tenant_id,
      search_hierarchy=True
  )
  ```

## 6. Rate Limiting

El servicio implementa el middleware de rate limiting aunque con características específicas:

- **Middleware estándar**: Configurado a través de `setup_rate_limiting(app)`.
- **Particularidades**: El rate limiting es menos crítico en este servicio ya que:
  - La mayoría de las operaciones son asíncronas y procesadas por workers
  - Los documentos ya pasan por validación de límites de tier
  - La validación de tier ya controla el número máximo de documentos

## 7. Consideraciones Especiales

- **Procesamiento asíncrono**: La mayor parte del trabajo se realiza en workers asíncronos.
- **Optimización de caché**: Se utiliza caché para minimizar generaciones redundantes de embeddings.
- **Trazabilidad**: Se mantiene logging detallado para auditoria y depuración.

## 8. Mejoras Futuras

- Implementar monitoreo de rendimiento para workers.
- Considerar el escalado dinámico de workers según carga.
- Consolidar los diferentes extractores para mejor mantenibilidad.
