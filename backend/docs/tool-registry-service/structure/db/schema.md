# Estructura de Base de Datos para Tool Registry Service

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

Este documento describe la estructura de base de datos para el Tool Registry Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar las herramientas disponibles para los agentes, sus parámetros, versiones y metadatos.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS tool_registry;
```

## 3. Tablas Principales

### 3.1 Tabla: `tool_registry.tools`

```sql
CREATE TABLE tool_registry.tools (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tool_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB
);
```

### 3.2 Tabla: `tool_registry.tool_versions`

```sql
CREATE TABLE tool_registry.tool_versions (
    id UUID PRIMARY KEY,
    tool_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    version VARCHAR(50) NOT NULL,
    config JSONB NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `tool_registry.tool_parameters`

```sql
CREATE TABLE tool_registry.tool_parameters (
    id UUID PRIMARY KEY,
    tool_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parameter_type VARCHAR(50) NOT NULL,
    required BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    schema JSONB,
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id) ON DELETE CASCADE
);
```

### 3.4 Tabla: `tool_registry.tool_executions`

```sql
CREATE TABLE tool_registry.tool_executions (
    id UUID PRIMARY KEY,
    tool_id UUID NOT NULL,
    tool_version_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    agent_id UUID, -- Referencia a agent_management.agents.id
    execution_id UUID, -- Referencia a agent_execution.executions.id
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    parameters JSONB,
    result JSONB,
    error_code VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id) ON DELETE CASCADE,
    FOREIGN KEY (tool_version_id) REFERENCES tool_registry.tool_versions (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para herramientas
CREATE INDEX idx_tools_tenant_id ON tool_registry.tools (tenant_id);
CREATE INDEX idx_tools_name ON tool_registry.tools (name);
CREATE INDEX idx_tools_tool_type ON tool_registry.tools (tool_type);
CREATE INDEX idx_tools_status ON tool_registry.tools (status);
CREATE INDEX idx_tools_created_at ON tool_registry.tools (created_at);

-- Índices para versiones de herramientas
CREATE INDEX idx_tool_versions_tool_id ON tool_registry.tool_versions (tool_id);
CREATE INDEX idx_tool_versions_tenant_id ON tool_registry.tool_versions (tenant_id);
CREATE INDEX idx_tool_versions_version ON tool_registry.tool_versions (version);
CREATE INDEX idx_tool_versions_is_default ON tool_registry.tool_versions (is_default);
CREATE INDEX idx_tool_versions_status ON tool_registry.tool_versions (status);

-- Índices para parámetros de herramientas
CREATE INDEX idx_tool_parameters_tool_id ON tool_registry.tool_parameters (tool_id);
CREATE INDEX idx_tool_parameters_tenant_id ON tool_registry.tool_parameters (tenant_id);
CREATE INDEX idx_tool_parameters_name ON tool_registry.tool_parameters (name);
CREATE INDEX idx_tool_parameters_parameter_type ON tool_registry.tool_parameters (parameter_type);

-- Índices para ejecuciones de herramientas
CREATE INDEX idx_tool_executions_tool_id ON tool_registry.tool_executions (tool_id);
CREATE INDEX idx_tool_executions_tool_version_id ON tool_registry.tool_executions (tool_version_id);
CREATE INDEX idx_tool_executions_tenant_id ON tool_registry.tool_executions (tenant_id);
CREATE INDEX idx_tool_executions_agent_id ON tool_registry.tool_executions (agent_id);
CREATE INDEX idx_tool_executions_execution_id ON tool_registry.tool_executions (execution_id);
CREATE INDEX idx_tool_executions_status ON tool_registry.tool_executions (status);
CREATE INDEX idx_tool_executions_started_at ON tool_registry.tool_executions (started_at);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| agent_id | agent_management.agents.id | Agente que ejecuta la herramienta |
| execution_id | agent_execution.executions.id | Ejecución asociada con esta invocación de herramienta |
