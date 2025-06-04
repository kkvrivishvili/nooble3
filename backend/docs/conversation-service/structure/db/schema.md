# Estructura de Base de Datos para Conversation Service

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

Este documento describe la estructura de base de datos para el Conversation Service dentro de la plataforma Nooble AI. Este servicio es responsable de gestionar las conversaciones entre usuarios y agentes, almacenando los mensajes y su contexto.

## 2. Esquema de Base de Datos

### 2.1 Identificación del Esquema

```sql
CREATE SCHEMA IF NOT EXISTS conversation;
```

## 3. Tablas Principales

### 3.1 Tabla: `conversation.conversations`

```sql
CREATE TABLE conversation.conversations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL, -- Referencia a agent_orchestrator.sessions.id
    title VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by UUID,
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB
);
```

### 3.2 Tabla: `conversation.messages`

```sql
CREATE TABLE conversation.messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    sender_type VARCHAR(50) NOT NULL, -- 'user', 'agent', 'system'
    sender_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'text',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    parent_message_id UUID,
    role VARCHAR(50) DEFAULT 'user',
    metadata JSONB,
    FOREIGN KEY (conversation_id) REFERENCES conversation.conversations (id) ON DELETE CASCADE
);
```

### 3.3 Tabla: `conversation.message_reactions`

```sql
CREATE TABLE conversation.message_reactions (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    reaction_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (message_id) REFERENCES conversation.messages (id) ON DELETE CASCADE
);
```

### 3.4 Tabla: `conversation.conversation_participants`

```sql
CREATE TABLE conversation.conversation_participants (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    participant_type VARCHAR(50) NOT NULL, -- 'user', 'agent'
    participant_id VARCHAR(255) NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    left_at TIMESTAMP WITH TIME ZONE,
    role VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (conversation_id) REFERENCES conversation.conversations (id) ON DELETE CASCADE
);
```

## 4. Índices y Relaciones

```sql
-- Índices para conversaciones
CREATE INDEX idx_conversations_tenant_id ON conversation.conversations (tenant_id);
CREATE INDEX idx_conversations_session_id ON conversation.conversations (session_id);
CREATE INDEX idx_conversations_status ON conversation.conversations (status);
CREATE INDEX idx_conversations_created_at ON conversation.conversations (created_at);

-- Índices para mensajes
CREATE INDEX idx_messages_conversation_id ON conversation.messages (conversation_id);
CREATE INDEX idx_messages_tenant_id ON conversation.messages (tenant_id);
CREATE INDEX idx_messages_sender_id ON conversation.messages (sender_id);
CREATE INDEX idx_messages_created_at ON conversation.messages (created_at);
CREATE INDEX idx_messages_parent_message_id ON conversation.messages (parent_message_id);

-- Índices para reacciones
CREATE INDEX idx_message_reactions_message_id ON conversation.message_reactions (message_id);
CREATE INDEX idx_message_reactions_tenant_id ON conversation.message_reactions (tenant_id);
CREATE INDEX idx_message_reactions_user_id ON conversation.message_reactions (user_id);

-- Índices para participantes
CREATE INDEX idx_conversation_participants_conversation_id ON conversation.conversation_participants (conversation_id);
CREATE INDEX idx_conversation_participants_tenant_id ON conversation.conversation_participants (tenant_id);
CREATE INDEX idx_conversation_participants_participant_id ON conversation.conversation_participants (participant_id);
```

## 5. Referencias entre Servicios

| Campo | Referencia a | Descripción |
|-------|-------------|-------------|
| session_id | agent_orchestrator.sessions.id | Sesión a la que pertenece esta conversación |
| participant_id | agent_management.agents.id (cuando participant_type='agent') | Agente que participa en la conversación |
