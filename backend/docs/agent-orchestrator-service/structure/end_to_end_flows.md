# Flujos End-to-End del Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Flujos End-to-End del Agent Orchestrator Service](#flujos-end-to-end-del-agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Diagrama de Arquitectura Global](#2-diagrama-de-arquitectura-global)
  - [3. Flujo de Sesión de Chat Interactiva](#3-flujo-de-sesión-de-chat-interactiva)
  - [4. Flujo de Procesamiento por Lotes](#4-flujo-de-procesamiento-por-lotes)
  - [5. Flujo de Ejecución de Workflow](#5-flujo-de-ejecución-de-workflow)
  - [6. Flujo de Recuperación ante Fallos](#6-flujo-de-recuperación-ante-fallos)
  - [7. Ciclo de Vida de una Sesión](#7-ciclo-de-vida-de-una-sesión)

## 1. Introducción

Este documento presenta los flujos completos de comunicación end-to-end entre el Agent Orchestrator Service y otros componentes de la plataforma Nooble AI. Se detallan los intercambios de mensajes, tiempos de respuesta estimados, secuencias de operaciones y manejo de casos especiales.

## 2. Diagrama de Arquitectura Global

```
┌───────────────┐     ┌─────────────────┐      ┌──────────────────┐
│               │     │                 │      │                  │
│   Frontend    │◄────┤  API Gateway    │◄─────┤  Load Balancer   │
│               │     │                 │      │                  │
└───────┬───────┘     └────────┬────────┘      └─────────┬────────┘
        │                      │                         │
        │                      ▼                         │
        │             ┌──────────────────┐               │
        │             │                  │               │
        └──────────►  │ Agent           │ ◄─────────────┘
                      │ Orchestrator    │
                      │ Service         │
                      │ (NIVEL 1)       │
                      │                  │
                      └───┬─────┬────┬───┘
                          │     │    │
          ┌───────────────┘     │    └────────────┐
          │                     │                 │
          ▼                     ▼                 ▼
┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐
│                 │  │                  │  │                │
│ Conversation    │  │ Agent Execution  │  │ Workflow       │
│ Service         │  │ Service          │  │ Engine         │
│ (NIVEL 2)       │  │ (NIVEL 2)        │  │ (NIVEL 2)      │
│                 │  │                  │  │                │
└────────┬────────┘  └─────────┬────────┘  └───────┬────────┘
         │                     │                   │
         │                     │                   │
         ▼                     ▼                   ▼
┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐
│                 │  │                  │  │                │
│ Query Service   │  │ Embedding        │  │ Tool Registry  │
│ (NIVEL 3)       │  │ Service (NIVEL 3)│  │ (NIVEL 2)      │
│                 │  │                  │  │                │
└─────────────────┘  └──────────────────┘  └────────────────┘
```

## 3. Flujo de Sesión de Chat Interactiva

### 3.1 Secuencia de Operaciones

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator
    participant ConvSvc as Conversation Service
    participant AgentExec as Agent Execution Service
    participant ToolReg as Tool Registry

    Cliente->>Orchestrator: 1. POST /api/sessions
    Orchestrator->>ConvSvc: 2. Crear conversación
    ConvSvc-->>Orchestrator: 3. Conversación creada
    Orchestrator-->>Cliente: 4. Session ID + WebSocket URL

    Cliente->>Orchestrator: 5. CONNECT WebSocket
    Orchestrator-->>Cliente: 6. WebSocket conectado

    Cliente->>Orchestrator: 7. POST /api/sessions/{id}/messages
    Orchestrator-->>Cliente: 8. Aceptado (202) + task_id
    
    Orchestrator->>ConvSvc: 9. Registrar mensaje
    Orchestrator->>AgentExec: 10. Procesar con agente
    AgentExec->>ToolReg: 11. Ejecutar herramienta (opcional)
    ToolReg-->>AgentExec: 12. Resultado de herramienta
    AgentExec-->>Orchestrator: 13. Respuesta procesada
    
    Orchestrator->>ConvSvc: 14. Guardar respuesta
    Orchestrator-->>Cliente: 15. [WS] Streaming de respuesta
    Orchestrator-->>Cliente: 16. [WS] Mensaje completo
```

### 3.2 Detalles de Tiempos y Operaciones

| Paso | Operación | Tiempo estimado | Cola/Canal |
|------|-----------|-----------------|------------|
| 1-4 | Creación de sesión | 300-500 ms | HTTP |
| 5-6 | Conexión WebSocket | 100-200 ms | WebSocket |
| 7-8 | Envío de mensaje | 100-200 ms | HTTP |
| 9 | Registro en Conversation | 100-200 ms | `orchestrator:tasks:{tenant_id}` |
| 10-13 | Procesamiento de agente | 1000-5000 ms | `orchestrator:tasks:{tenant_id}` |
| 14 | Guardar respuesta | 100-200 ms | `orchestrator:tasks:{tenant_id}` |
| 15-16 | Envío de respuesta | 100-300 ms | WebSocket |

### 3.3 Manejo de Estado

- El estado de la sesión se mantiene en la base de datos PostgreSQL y se actualiza en cada operación
- Las actualizaciones de estado se transmiten por WebSocket al cliente
- Los timeouts para cada fase son configurables por tenant

## 4. Flujo de Procesamiento por Lotes

### 4.1 Secuencia de Operaciones

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator
    participant AgentExec as Agent Execution Service
    participant WorkflowEng as Workflow Engine
    
    Cliente->>Orchestrator: 1. POST /api/batch
    Orchestrator-->>Cliente: 2. Aceptado (202) + batch_id
    
    Orchestrator->>Orchestrator: 3. Dividir en tareas
    
    par Procesamiento Paralelo
        Orchestrator->>AgentExec: 4a. Procesar item 1
        AgentExec-->>Orchestrator: 5a. Resultado item 1
        Orchestrator->>Cliente: 6a. [Callback] Resultado item 1
    and
        Orchestrator->>AgentExec: 4b. Procesar item 2
        AgentExec-->>Orchestrator: 5b. Resultado item 2
        Orchestrator->>Cliente: 6b. [Callback] Resultado item 2
    and
        Orchestrator->>AgentExec: 4c. Procesar item N
        AgentExec-->>Orchestrator: 5c. Resultado item N
        Orchestrator->>Cliente: 6c. [Callback] Resultado item N
    end
    
    Orchestrator->>WorkflowEng: 7. Procesamiento post-batch (si config)
    WorkflowEng-->>Orchestrator: 8. Resultado agregado
    
    Orchestrator->>Cliente: 9. [Callback] Batch completo
```

### 4.2 Detalles de Cola de Procesamiento

- Cola de alta prioridad: `orchestrator:batch:priority:{tenant_id}`
- Cola estándar: `orchestrator:batch:standard:{tenant_id}`
- Cola de baja prioridad: `orchestrator:batch:low:{tenant_id}`

### 4.3 Monitoreo y Control

- Cada batch tiene un estado global y estados individuales por item
- Se pueden consultar via API los estados: `GET /api/batch/{batch_id}`
- Se puede cancelar un batch en curso: `DELETE /api/batch/{batch_id}`

## 5. Flujo de Ejecución de Workflow

### 5.1 Secuencia de Operaciones

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator
    participant WorkflowEng as Workflow Engine
    participant AgentExec as Agent Execution Service
    participant ToolReg as Tool Registry
    
    Cliente->>Orchestrator: 1. POST /api/workflows
    Orchestrator->>WorkflowEng: 2. Iniciar workflow
    WorkflowEng-->>Orchestrator: 3. Workflow iniciado + workflow_id
    Orchestrator-->>Cliente: 4. Aceptado (202) + workflow_id
    
    WorkflowEng->>Orchestrator: 5. Solicitud de tarea
    
    alt Tarea de Ejecución de Agente
        Orchestrator->>AgentExec: 6a. Ejecutar agente
        AgentExec-->>Orchestrator: 7a. Resultado de agente
    else Tarea de Herramienta
        Orchestrator->>ToolReg: 6b. Ejecutar herramienta
        ToolReg-->>Orchestrator: 7b. Resultado de herramienta
    end
    
    Orchestrator->>WorkflowEng: 8. Resultado de tarea
    
    alt Si hay más tareas
        WorkflowEng->>Orchestrator: 9. Nueva solicitud de tarea
    else Workflow completo
        WorkflowEng->>Orchestrator: 9. Workflow completo + resultados
    end
    
    Orchestrator->>Cliente: 10. [Callback/WebSocket] Resultados
```

## 6. Flujo de Recuperación ante Fallos

### 6.1 Fallo de Servicio Nivel 2

```mermaid
sequenceDiagram
    participant Orchestrator
    participant ServiceN2 as Servicio Nivel 2
    participant DLQ as Dead Letter Queue
    
    Orchestrator->>ServiceN2: 1. Envío de mensaje
    ServiceN2--xOrchestrator: 2. Fallo (timeout/error)
    
    Orchestrator->>Orchestrator: 3. Intento #1 con backoff (1s)
    Orchestrator->>ServiceN2: 4. Reintento #1
    ServiceN2--xOrchestrator: 5. Fallo persistente
    
    Orchestrator->>Orchestrator: 6. Intento #2 con backoff (2s)
    Orchestrator->>ServiceN2: 7. Reintento #2
    ServiceN2--xOrchestrator: 8. Fallo persistente
    
    Orchestrator->>Orchestrator: 9. Circuit breaker activado
    Orchestrator->>DLQ: 10. Mensaje a DLQ
    Orchestrator->>Cliente: 11. [WS] Error notificado
```

### 6.2 Reconexión de Cliente WebSocket

```mermaid
sequenceDiagram
    participant Cliente
    participant Orchestrator
    participant ConvSvc as Conversation Service
    
    Cliente->>Orchestrator: 1. CONNECT WebSocket (reconexión)
    Orchestrator->>ConvSvc: 2. Obtener historial reciente
    ConvSvc-->>Orchestrator: 3. Historial de mensajes
    
    Note over Orchestrator,Cliente: Sincronización de estado
    
    Orchestrator-->>Cliente: 4. [WS] Estado actual
    Orchestrator-->>Cliente: 5. [WS] Últimos N mensajes
    
    Note over Cliente,Orchestrator: Continuación normal
```

## 7. Ciclo de Vida de una Sesión

### 7.1 Estados de Sesión

```mermaid
stateDiagram-v2
    [*] --> Created: POST /api/sessions
    Created --> Active: Primer mensaje
    Active --> Active: Interacción normal
    Active --> Inactive: Inactividad (10 min)
    Inactive --> Active: Nuevo mensaje
    Inactive --> Closed: Inactividad (24 hrs)
    Active --> Closed: Close explícito
    Closed --> [*]
```

### 7.2 Persistencia de Datos

Para cada sesión, se almacenan los siguientes datos:

| Entidad | Tabla | Tiempo de retención | Notas |
|---------|-------|---------------------|-------|
| Metadatos de sesión | `sessions` | 90 días | Indefinido para enterprise |
| Mensajes | `session_contexts` | 30 días | Configurable por tenant |
| Estado de agentes | `session_agents` | 90 días | Para análisis |
| Tareas | `tasks` | 7 días | Solo para debugging |
| Logs de operación | `operation_logs` | 30 días | Rotación automática |

### 7.3 Limpieza y Mantenimiento

- Limpieza periódica de sesiones inactivas: Tarea programada cada hora
- Archivado de sesiones antiguas: Tarea diaria (2:00 AM UTC)
- Compactación de tablas: Tarea semanal (domingo, 3:00 AM UTC)
