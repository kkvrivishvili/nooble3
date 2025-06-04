# Estructura de Base de Datos para Agent Orchestrator Service

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

Este documento describe la estructura de base de datos para el Agent Orchestrator Service dentro de la plataforma Nooble AI. Este servicio es responsable de coordinar la ejecución de múltiples agentes y gestionar el flujo de información entre ellos.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS agent_orchestrator;
```

## 3. Tablas Principales

### 3.1 Tabla: `agent_orchestrator.sessions`

```sql
CREATE TABLE agent_orchestrator.sessions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    session_type VARCHAR(50) NOT NULL,
    metadata JSONB,
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
```

### 3.2 Tabla: `agent_orchestrator.session_agents`

```sql
CREATE TABLE agent_orchestrator.session_agents (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    agent_id UUID NOT NULL, -- Referencia a agent_management.agents.id
    agent_role VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    left_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (session_id) REFERENCES agent_orchestrator.sessions (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `agent_orchestrator.session_contexts`

```sql
CREATE TABLE agent_orchestrator.session_contexts (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    context_type VARCHAR(50) NOT NULL,
    context_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    FOREIGN KEY (session_id) REFERENCES agent_orchestrator.sessions (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para sesiones
CREATE INDEX idx_sessions_tenant_id ON agent_orchestrator.sessions (tenant_id);
CREATE INDEX idx_sessions_user_id ON agent_orchestrator.sessions (user_id);
CREATE INDEX idx_sessions_status ON agent_orchestrator.sessions (status);
CREATE INDEX idx_sessions_session_type ON agent_orchestrator.sessions (session_type);
CREATE INDEX idx_sessions_started_at ON agent_orchestrator.sessions (started_at);

-- Índices para agentes en sesiones
CREATE INDEX idx_session_agents_session_id ON agent_orchestrator.session_agents (session_id);
CREATE INDEX idx_session_agents_tenant_id ON agent_orchestrator.session_agents (tenant_id);
CREATE INDEX idx_session_agents_agent_id ON agent_orchestrator.session_agents (agent_id);
CREATE INDEX idx_session_agents_status ON agent_orchestrator.session_agents (status);

-- Índices para contextos de sesión
CREATE INDEX idx_session_contexts_session_id ON agent_orchestrator.session_contexts (session_id);
CREATE INDEX idx_session_contexts_tenant_id ON agent_orchestrator.session_contexts (tenant_id);
CREATE INDEX idx_session_contexts_context_type ON agent_orchestrator.session_contexts (context_type);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| agent_id | agent_management.agents.id | Identifica el agente que participa en la sesión |
