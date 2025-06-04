# Estructura de Base de Datos para Tool Registry Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Esquema de Base de Datos](#2-esquema-de-base-de-datos)
3. [Tablas Principales](#3-tablas-principales)
4. [Índices y Relaciones](#4-índices-y-relaciones)

## 1. Introducción

Este documento describe la estructura de base de datos para el Tool Registry Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar el registro, catalogación y ejecución de herramientas que pueden ser utilizadas por los agentes.

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
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    visibility VARCHAR(50) DEFAULT 'public',
    version VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    schema JSONB NOT NULL
);
```

### 3.2 Tabla: `tool_registry.tool_implementations`

```sql
CREATE TABLE tool_registry.tool_implementations (
    id UUID PRIMARY KEY,
    tool_id UUID NOT NULL,
    implementation_type VARCHAR(50) NOT NULL,
    endpoint_url TEXT,
    function_name VARCHAR(255),
    runtime_environment VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    configuration JSONB,
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id)
);
```

### 3.3 Tabla: `tool_registry.tenant_tool_permissions`

```sql
CREATE TABLE tool_registry.tenant_tool_permissions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    tool_id UUID NOT NULL,
    permission_level VARCHAR(50) DEFAULT 'read',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id)
);
```

### 3.4 Tabla: `tool_registry.tool_executions`

```sql
CREATE TABLE tool_registry.tool_executions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    tool_id UUID NOT NULL,
    implementation_id UUID NOT NULL,
    agent_id UUID,
    session_id UUID,
    correlation_id UUID,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_time_ms INTEGER,
    input_parameters JSONB,
    output_result JSONB,
    error_code VARCHAR(50),
    error_message TEXT,
    FOREIGN KEY (tool_id) REFERENCES tool_registry.tools (id),
    FOREIGN KEY (implementation_id) REFERENCES tool_registry.tool_implementations (id)
);
```

## 4. Índices y Relaciones

```sql
-- Índices para herramientas
CREATE INDEX idx_tools_name ON tool_registry.tools (name);
CREATE INDEX idx_tools_category ON tool_registry.tools (category);
CREATE INDEX idx_tools_visibility ON tool_registry.tools (visibility);
CREATE INDEX idx_tools_status ON tool_registry.tools (status);
CREATE INDEX idx_tools_version ON tool_registry.tools (version);

-- Índices para implementaciones
CREATE INDEX idx_tool_implementations_tool_id ON tool_registry.tool_implementations (tool_id);
CREATE INDEX idx_tool_implementations_implementation_type ON tool_registry.tool_implementations (implementation_type);
CREATE INDEX idx_tool_implementations_status ON tool_registry.tool_implementations (status);

-- Índices para permisos de tenant
CREATE INDEX idx_tenant_tool_permissions_tenant_id ON tool_registry.tenant_tool_permissions (tenant_id);
CREATE INDEX idx_tenant_tool_permissions_tool_id ON tool_registry.tenant_tool_permissions (tool_id);

-- Índices para ejecuciones
CREATE INDEX idx_tool_executions_tenant_id ON tool_registry.tool_executions (tenant_id);
CREATE INDEX idx_tool_executions_tool_id ON tool_registry.tool_executions (tool_id);
CREATE INDEX idx_tool_executions_implementation_id ON tool_registry.tool_executions (implementation_id);
CREATE INDEX idx_tool_executions_agent_id ON tool_registry.tool_executions (agent_id);
CREATE INDEX idx_tool_executions_session_id ON tool_registry.tool_executions (session_id);
CREATE INDEX idx_tool_executions_status ON tool_registry.tool_executions (status);
```
