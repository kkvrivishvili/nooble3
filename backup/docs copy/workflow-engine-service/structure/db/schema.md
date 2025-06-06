# Estructura de Base de Datos para Workflow Engine Service

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

Este documento describe la estructura de base de datos para el Workflow Engine Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar la definición, ejecución y monitoreo de flujos de trabajo que pueden ser utilizados por los agentes.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS workflow_engine;
```

## 3. Tablas Principales

### 3.1 Tabla: `workflow_engine.definitions`

```sql
CREATE TABLE workflow_engine.definitions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    version VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'draft',
    definition JSONB NOT NULL
);
```

### 3.2 Tabla: `workflow_engine.instances`

```sql
CREATE TABLE workflow_engine.instances (
    id UUID PRIMARY KEY,
    definition_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    agent_id UUID, -- Referencia a agent_management.agents.id
    session_id UUID, -- Referencia a agent_orchestrator.sessions.id
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    context JSONB,
    result JSONB,
    FOREIGN KEY (definition_id) REFERENCES workflow_engine.definitions (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `workflow_engine.steps`

```sql
CREATE TABLE workflow_engine.steps (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    step_name VARCHAR(255) NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    inputs JSONB,
    outputs JSONB,
    error_code VARCHAR(50),
    error_message TEXT,
    FOREIGN KEY (instance_id) REFERENCES workflow_engine.instances (id) ON DELETE CASCADE
);
```

### 3.4 Tabla: `workflow_engine.transitions`

```sql
CREATE TABLE workflow_engine.transitions (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    from_step_id UUID NOT NULL,
    to_step_id UUID NOT NULL,
    transition_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    condition_result BOOLEAN,
    condition_expression TEXT,
    FOREIGN KEY (instance_id) REFERENCES workflow_engine.instances (id) ON DELETE CASCADE,
    FOREIGN KEY (from_step_id) REFERENCES workflow_engine.steps (id) ON DELETE CASCADE,
    FOREIGN KEY (to_step_id) REFERENCES workflow_engine.steps (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para definiciones de workflows
CREATE INDEX idx_definitions_tenant_id ON workflow_engine.definitions (tenant_id);
CREATE INDEX idx_definitions_name ON workflow_engine.definitions (name);
CREATE INDEX idx_definitions_version ON workflow_engine.definitions (version);
CREATE INDEX idx_definitions_status ON workflow_engine.definitions (status);
CREATE INDEX idx_definitions_created_at ON workflow_engine.definitions (created_at);

-- Índices para instancias de workflows
CREATE INDEX idx_instances_definition_id ON workflow_engine.instances (definition_id);
CREATE INDEX idx_instances_tenant_id ON workflow_engine.instances (tenant_id);
CREATE INDEX idx_instances_agent_id ON workflow_engine.instances (agent_id);
CREATE INDEX idx_instances_session_id ON workflow_engine.instances (session_id);
CREATE INDEX idx_instances_status ON workflow_engine.instances (status);
CREATE INDEX idx_instances_started_at ON workflow_engine.instances (started_at);

-- Índices para pasos de workflows
CREATE INDEX idx_steps_instance_id ON workflow_engine.steps (instance_id);
CREATE INDEX idx_steps_tenant_id ON workflow_engine.steps (tenant_id);
CREATE INDEX idx_steps_step_name ON workflow_engine.steps (step_name);
CREATE INDEX idx_steps_step_type ON workflow_engine.steps (step_type);
CREATE INDEX idx_steps_status ON workflow_engine.steps (status);

-- Índices para transiciones de workflows
CREATE INDEX idx_transitions_instance_id ON workflow_engine.transitions (instance_id);
CREATE INDEX idx_transitions_tenant_id ON workflow_engine.transitions (tenant_id);
CREATE INDEX idx_transitions_from_step_id ON workflow_engine.transitions (from_step_id);
CREATE INDEX idx_transitions_to_step_id ON workflow_engine.transitions (to_step_id);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| agent_id | agent_management.agents.id | Agente que inicia o está asociado con esta instancia de workflow |
| session_id | agent_orchestrator.sessions.id | Sesión en la que se ejecuta este workflow |
