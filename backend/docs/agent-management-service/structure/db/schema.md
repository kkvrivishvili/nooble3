# Estructura de Base de Datos para Agent Management Service

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

Este documento describe la estructura de base de datos para el Agent Management Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar las definiciones de agentes, sus configuraciones y capacidades.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS agent_management;
```

## 3. Tablas Principales

### 3.1 Tabla: `agent_management.agents`

```sql
CREATE TABLE agent_management.agents (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    system_prompt TEXT,
    default_workflow_id UUID, -- Referencia a workflow_engine.workflow_definitions.id
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    updated_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    version INTEGER DEFAULT 1,
    metadata JSONB
);
```

### 3.2 Tabla: `agent_management.agent_tools`

```sql
CREATE TABLE agent_management.agent_tools (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    tool_id UUID NOT NULL, -- Referencia a tool_registry.tools.id
    parameters JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    FOREIGN KEY (agent_id) REFERENCES agent_management.agents (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `agent_management.agent_versions`

```sql
CREATE TABLE agent_management.agent_versions (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    version INTEGER NOT NULL,
    system_prompt TEXT,
    configuration JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    FOREIGN KEY (agent_id) REFERENCES agent_management.agents (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para agentes
CREATE INDEX idx_agents_tenant_id ON agent_management.agents (tenant_id);
CREATE INDEX idx_agents_status ON agent_management.agents (status);
CREATE INDEX idx_agents_name ON agent_management.agents (name);

-- Índices para herramientas de agentes
CREATE INDEX idx_agent_tools_agent_id ON agent_management.agent_tools (agent_id);
CREATE INDEX idx_agent_tools_tenant_id ON agent_management.agent_tools (tenant_id);
CREATE INDEX idx_agent_tools_tool_id ON agent_management.agent_tools (tool_id);

-- Índices para versiones de agentes
CREATE INDEX idx_agent_versions_agent_id ON agent_management.agent_versions (agent_id);
CREATE INDEX idx_agent_versions_tenant_id ON agent_management.agent_versions (tenant_id);
CREATE INDEX idx_agent_versions_version ON agent_management.agent_versions (version);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| default_workflow_id | workflow_engine.workflow_definitions.id | Flujo de trabajo predeterminado para este agente |
| tool_id | tool_registry.tools.id | Herramienta que puede utilizar el agente |
