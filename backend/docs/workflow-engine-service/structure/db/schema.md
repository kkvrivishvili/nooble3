# Estructura de Base de Datos para Workflow Engine Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Esquema de Base de Datos](#2-esquema-de-base-de-datos)
3. [Tablas Principales](#3-tablas-principales)
4. [Índices y Relaciones](#4-índices-y-relaciones)

## 1. Introducción

Este documento describe la estructura de base de datos para el Workflow Engine Service dentro de la plataforma Nooble AI. Este servicio es responsable de definir, gestionar y ejecutar flujos de trabajo que coordinan las actividades de los agentes.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS workflow_engine;
```

## 3. Tablas Principales

### 3.1 Tabla: `workflow_engine.workflow_definitions`

```sql
CREATE TABLE workflow_engine.workflow_definitions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    definition JSONB NOT NULL
);
```

### 3.2 Tabla: `workflow_engine.workflow_instances`

```sql
CREATE TABLE workflow_engine.workflow_instances (
    id UUID PRIMARY KEY,
    workflow_definition_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    session_id UUID,
    correlation_id UUID,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    current_step VARCHAR(100),
    context JSONB,
    created_by UUID,
    error_code VARCHAR(50),
    error_message TEXT,
    FOREIGN KEY (workflow_definition_id) REFERENCES workflow_engine.workflow_definitions (id)
);
```

### 3.3 Tabla: `workflow_engine.workflow_steps`

```sql
CREATE TABLE workflow_engine.workflow_steps (
    id UUID PRIMARY KEY,
    workflow_instance_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    step_index INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    input JSONB,
    output JSONB,
    error_code VARCHAR(50),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    FOREIGN KEY (workflow_instance_id) REFERENCES workflow_engine.workflow_instances (id)
);
```

### 3.4 Tabla: `workflow_engine.workflow_transitions`

```sql
CREATE TABLE workflow_engine.workflow_transitions (
    id UUID PRIMARY KEY,
    workflow_instance_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    from_step VARCHAR(100) NOT NULL,
    to_step VARCHAR(100) NOT NULL,
    transition_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    condition_met VARCHAR(255),
    metadata JSONB,
    FOREIGN KEY (workflow_instance_id) REFERENCES workflow_engine.workflow_instances (id)
);
```

## 4. Índices y Relaciones

```sql
-- Índices para definiciones de flujo de trabajo
CREATE INDEX idx_workflow_definitions_tenant_id ON workflow_engine.workflow_definitions (tenant_id);
CREATE INDEX idx_workflow_definitions_name ON workflow_engine.workflow_definitions (name);
CREATE INDEX idx_workflow_definitions_status ON workflow_engine.workflow_definitions (status);
CREATE INDEX idx_workflow_definitions_version ON workflow_engine.workflow_definitions (version);

-- Índices para instancias de flujo de trabajo
CREATE INDEX idx_workflow_instances_workflow_definition_id ON workflow_engine.workflow_instances (workflow_definition_id);
CREATE INDEX idx_workflow_instances_tenant_id ON workflow_engine.workflow_instances (tenant_id);
CREATE INDEX idx_workflow_instances_session_id ON workflow_engine.workflow_instances (session_id);
CREATE INDEX idx_workflow_instances_status ON workflow_engine.workflow_instances (status);
CREATE INDEX idx_workflow_instances_current_step ON workflow_engine.workflow_instances (current_step);

-- Índices para pasos de flujo de trabajo
CREATE INDEX idx_workflow_steps_workflow_instance_id ON workflow_engine.workflow_steps (workflow_instance_id);
CREATE INDEX idx_workflow_steps_tenant_id ON workflow_engine.workflow_steps (tenant_id);
CREATE INDEX idx_workflow_steps_step_name ON workflow_engine.workflow_steps (step_name);
CREATE INDEX idx_workflow_steps_status ON workflow_engine.workflow_steps (status);
CREATE INDEX idx_workflow_steps_step_index ON workflow_engine.workflow_steps (step_index);

-- Índices para transiciones de flujo de trabajo
CREATE INDEX idx_workflow_transitions_workflow_instance_id ON workflow_engine.workflow_transitions (workflow_instance_id);
CREATE INDEX idx_workflow_transitions_tenant_id ON workflow_engine.workflow_transitions (tenant_id);
CREATE INDEX idx_workflow_transitions_from_step ON workflow_engine.workflow_transitions (from_step);
CREATE INDEX idx_workflow_transitions_to_step ON workflow_engine.workflow_transitions (to_step);
```
