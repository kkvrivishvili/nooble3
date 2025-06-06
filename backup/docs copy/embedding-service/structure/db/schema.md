# Estructura de Base de Datos para Embedding Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Esquema de Base de Datos](#2-esquema-de-base-de-datos)
3. [Tablas Principales](#3-tablas-principales)
4. [Índices y Relaciones](#4-índices-y-relaciones)
5. [Referencias entre Servicios](#5-referencias-entre-servicios)

## 1. Introducción

Este documento describe la estructura de base de datos para el Embedding Service dentro de la plataforma Nooble AI. Este servicio es responsable de generar, gestionar y almacenar metadatos sobre los embeddings (representaciones vectoriales) utilizados para operaciones de similitud semántica.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS embedding;
```

## 3. Tablas Principales

### 3.1 Tabla: `embedding.embedding_batches`

```sql
CREATE TABLE embedding.embedding_batches (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    batch_size INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    processing_time_ms INTEGER,
    total_tokens INTEGER,
    error_code VARCHAR(50),
    error_message TEXT,
    created_by UUID,
    updated_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB
);
```

### 3.2 Tabla: `embedding.embedding_requests`

```sql
CREATE TABLE embedding.embedding_requests (
    id UUID PRIMARY KEY,
    batch_id UUID,
    tenant_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    text TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    tokens INTEGER,
    error_code VARCHAR(50),
    error_message TEXT,
    source_type VARCHAR(50),
    source_id VARCHAR(255),
    created_by UUID,
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (batch_id) REFERENCES embedding.embedding_batches (id) ON DELETE SET NULL
);
```

### 3.3 Tabla: `embedding.model_configurations`

```sql
CREATE TABLE embedding.model_configurations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    dimensions INTEGER NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    active BOOLEAN DEFAULT TRUE,
    configuration JSONB
);
```

## 4. Índices y Relaciones

```sql
-- Índices para lotes de embeddings
CREATE INDEX idx_embedding_batches_tenant_id ON embedding.embedding_batches (tenant_id);
CREATE INDEX idx_embedding_batches_model_name ON embedding.embedding_batches (model_name);
CREATE INDEX idx_embedding_batches_status ON embedding.embedding_batches (status);
CREATE INDEX idx_embedding_batches_created_at ON embedding.embedding_batches (created_at);

-- Índices para solicitudes de embeddings
CREATE INDEX idx_embedding_requests_batch_id ON embedding.embedding_requests (batch_id);
CREATE INDEX idx_embedding_requests_tenant_id ON embedding.embedding_requests (tenant_id);
CREATE INDEX idx_embedding_requests_model_name ON embedding.embedding_requests (model_name);
CREATE INDEX idx_embedding_requests_status ON embedding.embedding_requests (status);
CREATE INDEX idx_embedding_requests_source_id ON embedding.embedding_requests (source_id);
CREATE INDEX idx_embedding_requests_source_type ON embedding.embedding_requests (source_type);

-- Índices para configuraciones de modelos
CREATE INDEX idx_model_configurations_tenant_id ON embedding.model_configurations (tenant_id);
CREATE INDEX idx_model_configurations_model_name ON embedding.model_configurations (model_name);
CREATE INDEX idx_model_configurations_is_default ON embedding.model_configurations (is_default);
CREATE INDEX idx_model_configurations_active ON embedding.model_configurations (active);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| source_id | ingestion.document_chunks.id (cuando source_type='document_chunk') | Fragmento de documento al que se asocia este embedding |
| source_id | query_service.queries.id (cuando source_type='query') | Consulta a la que se asocia este embedding |
