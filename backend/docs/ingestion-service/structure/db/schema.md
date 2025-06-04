# Estructura de Base de Datos para Ingestion Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Esquema de Base de Datos](#2-esquema-de-base-de-datos)
3. [Tablas Principales](#3-tablas-principales)
4. [Índices y Relaciones](#4-índices-y-relaciones)

## 1. Introducción

Este documento describe la estructura de base de datos para el Ingestion Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar el proceso de ingestión de documentos, su procesamiento, chunking y almacenamiento de metadatos.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS ingestion;
```

## 3. Tablas Principales

### 3.1 Tabla: `ingestion.collections`

```sql
CREATE TABLE ingestion.collections (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB
);
```

### 3.2 Tabla: `ingestion.documents`

```sql
CREATE TABLE ingestion.documents (
    id UUID PRIMARY KEY,
    collection_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    source_url TEXT,
    source_id VARCHAR(255),
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    file_size INTEGER,
    num_pages INTEGER,
    metadata JSONB,
    FOREIGN KEY (collection_id) REFERENCES ingestion.collections (id)
);
```

### 3.3 Tabla: `ingestion.document_chunks`

```sql
CREATE TABLE ingestion.document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    collection_id UUID NOT NULL,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding_id UUID,
    page_number INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB,
    FOREIGN KEY (document_id) REFERENCES ingestion.documents (id)
);
```

### 3.4 Tabla: `ingestion.ingestion_jobs`

```sql
CREATE TABLE ingestion.ingestion_jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    collection_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(50),
    error_message TEXT,
    total_documents INTEGER,
    processed_documents INTEGER DEFAULT 0,
    failed_documents INTEGER DEFAULT 0,
    metadata JSONB,
    FOREIGN KEY (collection_id) REFERENCES ingestion.collections (id)
);
```

## 4. Índices y Relaciones

```sql
-- Índices para colecciones
CREATE INDEX idx_collections_tenant_id ON ingestion.collections (tenant_id);
CREATE INDEX idx_collections_name ON ingestion.collections (name);
CREATE INDEX idx_collections_status ON ingestion.collections (status);

-- Índices para documentos
CREATE INDEX idx_documents_collection_id ON ingestion.documents (collection_id);
CREATE INDEX idx_documents_tenant_id ON ingestion.documents (tenant_id);
CREATE INDEX idx_documents_title ON ingestion.documents (title);
CREATE INDEX idx_documents_type ON ingestion.documents (type);
CREATE INDEX idx_documents_status ON ingestion.documents (status);
CREATE INDEX idx_documents_source_id ON ingestion.documents (source_id);

-- Índices para chunks de documentos
CREATE INDEX idx_document_chunks_document_id ON ingestion.document_chunks (document_id);
CREATE INDEX idx_document_chunks_tenant_id ON ingestion.document_chunks (tenant_id);
CREATE INDEX idx_document_chunks_collection_id ON ingestion.document_chunks (collection_id);
CREATE INDEX idx_document_chunks_embedding_id ON ingestion.document_chunks (embedding_id);
CREATE INDEX idx_document_chunks_chunk_index ON ingestion.document_chunks (chunk_index);

-- Índices para trabajos de ingestión
CREATE INDEX idx_ingestion_jobs_tenant_id ON ingestion.ingestion_jobs (tenant_id);
CREATE INDEX idx_ingestion_jobs_collection_id ON ingestion.ingestion_jobs (collection_id);
CREATE INDEX idx_ingestion_jobs_status ON ingestion.ingestion_jobs (status);
CREATE INDEX idx_ingestion_jobs_job_type ON ingestion.ingestion_jobs (job_type);
```
