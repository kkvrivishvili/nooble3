# Modelos de Datos - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Modelos de Datos - Agent Management Service](#modelos-de-datos---agent-management-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Entidades Principales](#2-entidades-principales)
    - [2.1 Agent](#21-agent)
    - [2.2 AgentVersion](#22-agentversion)
    - [2.3 AgentTemplate](#23-agenttemplate)
    - [2.4 AgentStatus](#24-agentstatus)
  - [3. Esquemas JSON](#3-esquemas-json)
    - [3.1 Agent](#31-agent)
    - [3.2 LLMConfig](#32-llmconfig)
    - [3.3 MemoryConfig](#33-memoryconfig)
    - [3.4 AgentTool](#34-agenttool)
  - [4. Relaciones entre Modelos](#4-relaciones-entre-modelos)
  - [5. Validaciones y Reglas de Negocio](#5-validaciones-y-reglas-de-negocio)
  - [6. Versionado de Modelos](#6-versionado-de-modelos)
  - [7. Registro de Cambios](#7-registro-de-cambios)

## 1. Visión General

Este documento detalla los modelos de datos utilizados en el Agent Management Service. Los modelos principales son Agent (agente), AgentVersion (versión del agente), AgentTemplate (plantilla de agente) y AgentStatus (estado del agente).

![Diagrama Entidad-Relación](./diagrams/agent_models_erd.png)

## 2. Entidades Principales

### 2.1 Agent

Representa un agente en el sistema. Un agente puede tener múltiples versiones y está asociado a un tenant específico.

**Atributos clave:**
- `id`: Identificador único del agente
- `name`: Nombre descriptivo del agente
- `description`: Descripción detallada del agente
- `tenant_id`: Identificador del tenant al que pertenece
- `current_version_id`: Referencia a la versión actual del agente
- `status`: Estado actual del agente (ACTIVE, INACTIVE, DRAFT)
- `created_at`: Timestamp de creación
- `updated_at`: Timestamp de última actualización
- `created_by`: Usuario que creó el agente
- `is_template`: Indica si es una plantilla de agente

### 2.2 AgentVersion

Almacena una versión específica de configuración de un agente, permitiendo el versionado y la capacidad de revertir a versiones anteriores.

**Atributos clave:**
- `id`: Identificador único de la versión
- `agent_id`: Referencia al agente al que pertenece
- `version_number`: Número secuencial de versión
- `system_prompt`: Instrucciones base para el agente
- `tools`: Lista de herramientas disponibles para el agente
- `llm_config`: Configuración del modelo de lenguaje
- `memory_config`: Configuración de la memoria del agente
- `created_at`: Timestamp de creación
- `created_by`: Usuario que creó esta versión

### 2.3 AgentTemplate

Plantillas predefinidas para crear agentes con configuraciones comunes.

**Atributos clave:**
- `id`: Identificador único de la plantilla
- `name`: Nombre de la plantilla
- `description`: Descripción detallada
- `category`: Categoría (CUSTOMER_SUPPORT, MARKETING, SALES, etc.)
- `system_prompt`: Instrucciones base recomendadas
- `tools`: Herramientas recomendadas
- `llm_config`: Configuración recomendada de LLM
- `memory_config`: Configuración recomendada de memoria
- `popularity`: Indicador de popularidad/uso

### 2.4 AgentStatus

Historial de cambios de estado de un agente.

**Atributos clave:**
- `id`: Identificador único del registro de estado
- `agent_id`: Referencia al agente
- `previous_status`: Estado anterior
- `new_status`: Nuevo estado
- `changed_at`: Timestamp del cambio
- `changed_by`: Usuario que realizó el cambio
- `reason`: Razón del cambio de estado

## 3. Esquemas JSON

### 3.1 Agent

```json
{
  "id": "uuid-string",
  "name": "Customer Support Agent",
  "description": "Agente especializado en soporte técnico",
  "status": "active",
  "created_at": "2025-05-15T10:30:00Z",
  "updated_at": "2025-06-02T14:25:30Z",
  "version": 3,
  "system_prompt": "Eres un agente de soporte técnico especializado...",
  "tools": [
    {
      "id": "knowledge-base",
      "config": {
        "kb_id": "support-docs"
      }
    },
    {
      "id": "ticket-system",
      "config": {
        "priority_access": true
      }
    }
  ],
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.3,
    "max_tokens": 2000,
    "top_p": 0.95
  },
  "memory_config": {
    "memory_type": "conversation",
    "window_size": 15,
    "include_knowledge_context": true
  },
  "metadata": {
    "created_by": "user-123",
    "department": "support",
    "tags": ["technical", "premium-support", "product-specialist"],
    "training_complete": true
  }
}
```

### 3.2 LLMConfig

```json
{
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 1000,
  "top_p": 1.0,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "stop_sequences": ["User:", "Agent:"],
  "custom_parameters": {
    "streaming": true
  }
}
```

### 3.3 MemoryConfig

```json
{
  "memory_type": "conversation",
  "window_size": 10,
  "include_knowledge_context": false,
  "summarize_threshold": 20,
  "vector_store_config": {
    "enabled": true,
    "model": "text-embedding-ada-002",
    "similarity_threshold": 0.85
  }
}
```

### 3.4 AgentTool

```json
{
  "id": "knowledge-base",
  "config": {
    "kb_id": "support-docs",
    "search_type": "semantic",
    "max_results": 5
  },
  "permissions": ["read"],
  "required": true
}
```

## 4. Relaciones entre Modelos

- Un **Agent** tiene muchas **AgentVersion**
- Un **Agent** tiene muchos registros de **AgentStatus**
- Un **Agent** puede derivar de un **AgentTemplate**
- Un **AgentTemplate** puede ser creado a partir de un **Agent** existente

## 5. Validaciones y Reglas de Negocio

- Nombres de agentes deben ser únicos dentro del mismo tenant
- El campo `system_prompt` tiene un límite de 8,000 caracteres
- Un agente puede tener como máximo 15 herramientas asignadas (según tier)
- La configuración de LLM debe ser compatible con el tier del tenant
- Solo usuarios con rol "admin" pueden cambiar un agente a estado "ACTIVE"

## 6. Versionado de Modelos

El sistema utiliza versionado semántico para los modelos:

- Cambios mayores (breaking changes): incremento en el primer número
- Adiciones de campos opcionales: incremento en el segundo número
- Correcciones menores: incremento en el tercer número

Ejemplo: v1.2.3

## 7. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
