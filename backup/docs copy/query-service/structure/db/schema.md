# Estructura de Base de Datos para Query Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Esquema de Base de Datos](#2-esquema-de-base-de-datos)
3. [Tablas Principales](#3-tablas-principales)
4. [Índices y Relaciones](#4-índices-y-relaciones)
5. [Flujo de Datos](#5-flujo-de-datos)
6. [Integración con Vector DB](#6-integración-con-vector-db)
7. [Migraciones y Versionado](#7-migraciones-y-versionado)

## 1. Introducción

Este documento describe la estructura de base de datos para el Query Service dentro de la plataforma Nooble AI. El Query Service es responsable del procesamiento RAG (Retrieval Augmented Generation) y requiere almacenamiento tanto para metadatos de consultas como para la integración con la base de datos vectorial de Supabase.

### 1.1 Propósito

El esquema de base de datos del Query Service permite:
- Almacenamiento de metadatos de consultas y resultados
- Registro de uso de tokens y métricas de calidad
- Historial de consultas por tenant
- Configuración de parámetros de RAG por tenant y colección
- Referencias a documentos y fragmentos utilizados

### 1.2 Responsabilidades

- **Responsable del esquema**: Equipo Query Service
- **Permisos requeridos**: Lectura/escritura para servicio, solo lectura para monitoreo

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

El Query Service utiliza un esquema dedicado en la base de datos PostgreSQL:

```sql
CREATE SCHEMA IF NOT EXISTS query_service;
```

### 2.2 Relaciones con Otros Esquemas

| Esquema | Relación | Propósito |
|---------|----------|-----------|
| ingestion_service | Referencial | Referencias a documentos y colecciones |
| embedding_service | Sin acceso directo | Comunicación vía API |
| agent_management | Sin acceso directo | Comunicación vía API |

## 3. Tablas Principales

### 3.1 Tabla: `query_service.queries`

Almacena metadatos de todas las consultas procesadas por el servicio.

```sql
CREATE TABLE query_service.queries (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    session_id UUID,
    user_id UUID,
    correlation_id UUID,
    query_text TEXT NOT NULL,
    collection_id UUID,
    model_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_time_ms INTEGER,
    status VARCHAR(50) NOT NULL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    source_quality VARCHAR(50),
    error_code VARCHAR(50),
    error_message TEXT
);
```

| Campo | Tipo | Descripción | Obligatorio |
|-------|------|-------------|-------------|
| id | UUID | Identificador único de la consulta | Sí |
| tenant_id | UUID | ID del tenant | Sí |
| session_id | UUID | ID de la sesión | No |
| user_id | UUID | ID del usuario final | No |
| correlation_id | UUID | ID para correlacionar solicitudes | No |
| query_text | TEXT | Texto de la consulta | Sí |
| collection_id | UUID | ID de la colección consultada | No |
| model_name | VARCHAR | Nombre del modelo LLM usado | Sí |
| created_at | TIMESTAMP | Momento de creación | Sí |
| processing_time_ms | INTEGER | Tiempo de procesamiento | No |
| status | VARCHAR | Estado (completed, failed) | Sí |
| tokens_input | INTEGER | Tokens de entrada usados | No |
| tokens_output | INTEGER | Tokens de salida generados | No |
| source_quality | VARCHAR | Calidad de fuentes (high, low, none) | No |
| error_code | VARCHAR | Código de error si falló | No |
| error_message | TEXT | Mensaje de error detallado | No |

### 3.2 Tabla: `query_service.query_sources`

Registra las fuentes (documentos) utilizadas para responder a una consulta.

```sql
CREATE TABLE query_service.query_sources (
    id UUID PRIMARY KEY,
    query_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    document_id UUID NOT NULL,
    chunk_id UUID,
    relevance_score FLOAT,
    used_in_response BOOLEAN DEFAULT FALSE,
    page_number INTEGER,
    character_range JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (query_id) REFERENCES query_service.queries (id)
);
```

| Campo | Tipo | Descripción | Obligatorio |
|-------|------|-------------|-------------|
| id | UUID | Identificador único | Sí |
| query_id | UUID | ID de la consulta relacionada | Sí |
| tenant_id | UUID | ID del tenant | Sí |
| document_id | UUID | ID del documento fuente | Sí |
| chunk_id | UUID | ID del fragmento específico | No |
| relevance_score | FLOAT | Puntuación de relevancia (0-1) | No |
| used_in_response | BOOLEAN | Indica si se usó en la respuesta | Sí |
| page_number | INTEGER | Número de página | No |
| character_range | JSONB | Rango de caracteres {"start": X, "end": Y} | No |
| created_at | TIMESTAMP | Momento de registro | Sí |

### 3.3 Tabla: `query_service.tenant_configurations`

Almacena configuraciones específicas por tenant para el proceso RAG.

```sql
CREATE TABLE query_service.tenant_configurations (
    tenant_id UUID PRIMARY KEY,
    default_model VARCHAR(100) NOT NULL,
    default_similarity_threshold FLOAT DEFAULT 0.7,
    default_num_results INTEGER DEFAULT 5,
    max_tokens_per_request INTEGER DEFAULT 8000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID
);
```

| Campo | Tipo | Descripción | Valor Predeterminado |
|-------|------|-------------|----------------------|
| tenant_id | UUID | ID del tenant | - |
| default_model | VARCHAR | Modelo LLM por defecto | - |
| default_similarity_threshold | FLOAT | Umbral de similitud | 0.7 |
| default_num_results | INTEGER | Número de resultados | 5 |
| max_tokens_per_request | INTEGER | Límite de tokens | 8000 |
| created_at | TIMESTAMP | Momento de creación | NOW() |
| updated_at | TIMESTAMP | Última actualización | NULL |
| created_by | UUID | Usuario creador | NULL |
| updated_by | UUID | Usuario que actualizó | NULL |

### 3.4 Tabla: `query_service.collection_configurations`

Configuraciones específicas por colección, con herencia de configuración del tenant.

```sql
CREATE TABLE query_service.collection_configurations (
    collection_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    model_name VARCHAR(100),
    similarity_threshold FLOAT,
    num_results INTEGER,
    system_prompt TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID
);
```

| Campo | Tipo | Descripción | Obligatorio |
|-------|------|-------------|-------------|
| collection_id | UUID | ID de la colección | Sí |
| tenant_id | UUID | ID del tenant | Sí |
| model_name | VARCHAR | Modelo LLM específico | No |
| similarity_threshold | FLOAT | Umbral de similitud | No |
| num_results | INTEGER | Número de resultados | No |
| system_prompt | TEXT | Prompt del sistema personalizado | No |
| created_at | TIMESTAMP | Momento de creación | Sí |
| updated_at | TIMESTAMP | Última actualización | No |
| created_by | UUID | Usuario creador | No |
| updated_by | UUID | Usuario que actualizó | No |

## 4. Índices y Relaciones

### 4.1 Índices Principales

```sql
-- Índices para consultas
CREATE INDEX idx_queries_tenant_id ON query_service.queries (tenant_id);
CREATE INDEX idx_queries_created_at ON query_service.queries (created_at);
CREATE INDEX idx_queries_collection_id ON query_service.queries (collection_id);
CREATE INDEX idx_queries_status ON query_service.queries (status);
CREATE INDEX idx_queries_source_quality ON query_service.queries (source_quality);
CREATE INDEX idx_queries_model_name ON query_service.queries (model_name);

-- Índices para fuentes
CREATE INDEX idx_query_sources_query_id ON query_service.query_sources (query_id);
CREATE INDEX idx_query_sources_tenant_id ON query_service.query_sources (tenant_id);
CREATE INDEX idx_query_sources_document_id ON query_service.query_sources (document_id);
CREATE INDEX idx_query_sources_relevance_score ON query_service.query_sources (relevance_score);
```

### 4.2 Restricciones de Clave Foránea

```sql
-- Relación entre fuentes y consultas
ALTER TABLE query_service.query_sources
ADD CONSTRAINT fk_query_sources_query_id
FOREIGN KEY (query_id) REFERENCES query_service.queries (id)
ON DELETE CASCADE;

-- Relación entre configuraciones y colecciones
ALTER TABLE query_service.collection_configurations
ADD CONSTRAINT fk_collection_configurations_tenant_id
FOREIGN KEY (tenant_id) REFERENCES query_service.tenant_configurations (tenant_id)
ON DELETE CASCADE;
```

## 5. Flujo de Datos

### 5.1 Operaciones Principales

| Operación | Tablas Involucradas | Descripción |
|-----------|---------------------|-------------|
| Registro de consulta | queries | Almacena metadata inicial al recibir consulta |
| Registro de fuentes | query_sources | Registra documentos recuperados y utilizados |
| Actualización de resultados | queries | Actualiza con tokens, tiempo y estado |
| Configuración de tenant | tenant_configurations | CRUD para configuraciones |
| Configuración de colección | collection_configurations | CRUD para configuraciones |

### 5.2 Diagrama de Flujo

```
┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   Recepción   │     │  Procesamiento  │     │    Resultados    │
│  de Consulta  │────▶│      RAG       │────▶│  y Actualización  │
└───────────────┘     └─────────────────┘     └──────────────────┘
        │                     │                        │
        ▼                     ▼                        ▼
┌───────────────┐     ┌─────────────────┐     ┌──────────────────┐
│queries (create)│     │query_sources    │     │queries (update)  │
└───────────────┘     │(create multiple) │     └──────────────────┘
                      └─────────────────┘
```

## 6. Integración con Vector DB

### 6.1 Estructura en Supabase

El Query Service accede a la tabla de vectores en Supabase:

```sql
-- Tabla referencial (gestionada por Ingestion Service)
CREATE TABLE public.documents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    collection_id UUID NOT NULL,
    content TEXT,
    metadata JSONB,
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índice vectorial
CREATE INDEX documents_embedding_idx ON public.documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### 6.2 Flujo de Acceso

1. Se recibe una consulta con embedding previamente calculado
2. Se realiza búsqueda vectorial en Supabase
3. Se registran documentos relevantes en `query_sources`
4. Se generan respuestas usando fuentes recuperadas

## 7. Migraciones y Versionado

### 7.1 Estrategia de Migraciones

Las migraciones del Query Service siguen esta estructura:

```
query_service/
├── migrations/
│   ├── 001_initial_schema.sql    # Esquema inicial
│   ├── 002_add_indices.sql       # Adición de índices
│   └── 003_extended_fields.sql   # Campos adicionales
```

### 7.2 Script de Aplicación

```python
async def apply_migrations():
    """Aplica las migraciones de base de datos en orden."""
    migration_dir = Path("migrations")
    
    async with db.transaction():
        # Crear tabla de versiones si no existe
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_service.schema_versions (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                script_name VARCHAR(255)
            )
        """)
        
        # Obtener última versión aplicada
        result = await db.fetch_one(
            "SELECT MAX(version) as version FROM query_service.schema_versions"
        )
        current_version = result['version'] if result['version'] else 0
        
        # Aplicar migraciones pendientes
        for migration_file in sorted(migration_dir.glob("*.sql")):
            file_version = int(migration_file.name.split("_")[0])
            
            if file_version > current_version:
                logger.info(f"Aplicando migración {migration_file.name}")
                
                # Leer y ejecutar script
                script = migration_file.read_text()
                await db.execute(script)
                
                # Registrar versión
                await db.execute(
                    """
                    INSERT INTO query_service.schema_versions (version, script_name)
                    VALUES ($1, $2)
                    """,
                    file_version, migration_file.name
                )
                
                logger.info(f"Migración {file_version} aplicada con éxito")
```
