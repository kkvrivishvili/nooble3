# Funciones "muertas" (no utilizadas) en common

Este documento lista las funciones, clases o utilidades públicas definidas en el módulo `common` que no son utilizadas por ninguno de los servicios principales (`agent-service`, `embedding-service`, `ingestion-service`, `query-service`).

> **Nota:** Esta lista es útil para identificar posibles candidatos a refactorización, eliminación o documentación adicional.

| Módulo                | Nombre                        | Tipo      | Descripción breve                                     |
|-----------------------|-------------------------------|-----------|-------------------------------------------------------|
| common.llm.base       | BaseEmbeddingModel            | Clase     | Interfaz abstracta para modelos de embedding          |
| common.llm.ollama     | OllamaEmbeddings              | Clase     | Cliente de embeddings Ollama, compatible con LangChain |

**Notas:**
- `BaseEmbeddingModel` y `OllamaEmbeddings` están definidos y exportados, pero no son usados directamente por los servicios actuales.
- Se recomienda revisar antes de eliminar, ya que podrían ser usados en futuras integraciones o por código experimental/test.
- Si algún servicio comienza a utilizar estas clases, actualizar este archivo para mantenerlo sincronizado.
