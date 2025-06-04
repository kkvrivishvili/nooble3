# Estructura de Base de Datos para Agent Execution Service

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

Este documento describe la estructura de base de datos para el Agent Execution Service dentro de la plataforma Nooble AI. Este servicio es responsable de registrar y gestionar todas las ejecuciones de agentes, incluyendo su historial, métricas y resultados.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS agent_execution;
```

## 3. Tablas Principales

### 3.1 Tabla: `agent_execution.executions`

```sql
CREATE TABLE agent_execution.executions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    agent_id UUID NOT NULL, -- Referencia a agent_management.agents.id
    user_id UUID,
    conversation_id UUID, -- Referencia a conversation.conversations.id
    session_id UUID NOT NULL, -- Referencia a agent_orchestrator.sessions.id
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_time_ms INTEGER,
    error_code VARCHAR(50),
    error_message TEXT,
    input_prompt TEXT,
    output_response TEXT,
    tokens_used INTEGER,
    model_name VARCHAR(100),
    created_by UUID,
    metadata JSONB
);
```

### 3.2 Tabla: `agent_execution.execution_steps`

```sql
CREATE TABLE agent_execution.execution_steps (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    step_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    input JSONB,
    output JSONB,
    error_code VARCHAR(50),
    error_message TEXT,
    step_index INTEGER NOT NULL,
    execution_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (execution_id) REFERENCES agent_execution.executions (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `agent_execution.execution_metrics`

```sql
CREATE TABLE agent_execution.execution_metrics (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB,
    FOREIGN KEY (execution_id) REFERENCES agent_execution.executions (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para ejecuciones
CREATE INDEX idx_executions_tenant_id ON agent_execution.executions (tenant_id);
CREATE INDEX idx_executions_agent_id ON agent_execution.executions (agent_id);
CREATE INDEX idx_executions_session_id ON agent_execution.executions (session_id);
CREATE INDEX idx_executions_status ON agent_execution.executions (status);
CREATE INDEX idx_executions_started_at ON agent_execution.executions (started_at);
CREATE INDEX idx_executions_conversation_id ON agent_execution.executions (conversation_id);

-- Índices para pasos de ejecución
CREATE INDEX idx_execution_steps_execution_id ON agent_execution.execution_steps (execution_id);
CREATE INDEX idx_execution_steps_tenant_id ON agent_execution.execution_steps (tenant_id);
CREATE INDEX idx_execution_steps_status ON agent_execution.execution_steps (status);
CREATE INDEX idx_execution_steps_step_type ON agent_execution.execution_steps (step_type);
CREATE INDEX idx_execution_steps_step_index ON agent_execution.execution_steps (step_index);

-- Índices para métricas de ejecución
CREATE INDEX idx_execution_metrics_execution_id ON agent_execution.execution_metrics (execution_id);
CREATE INDEX idx_execution_metrics_tenant_id ON agent_execution.execution_metrics (tenant_id);
CREATE INDEX idx_execution_metrics_metric_name ON agent_execution.execution_metrics (metric_name);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| agent_id | agent_management.agents.id | Identifica el agente que se ejecutó |
| conversation_id | conversation.conversations.id | Conversación asociada a esta ejecución |
| session_id | agent_orchestrator.sessions.id | Sesión donde se realizó la ejecución |
