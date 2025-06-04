# Matriz de Errores del Agent Orchestrator Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-04*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Matriz de Errores del Agent Orchestrator Service](#matriz-de-errores-del-agent-orchestrator-service)
  - [Índice](#índice)
  - [1. Introducción](#1-introducción)
  - [2. Estructura de Códigos de Error](#2-estructura-de-códigos-de-error)
  - [3. Matriz de Errores Comunes](#3-matriz-de-errores-comunes)
    - [4xx - Errores del Cliente](#4xx---errores-del-cliente)
    - [5xx - Errores del Servidor](#5xx---errores-del-servidor)
  - [4. Errores Específicos por Servicio](#4-errores-específicos-por-servicio)
    - [Agent Orchestrator Service (ORCH)](#agent-orchestrator-service-orch)
    - [Agent Execution Service (AGEX)](#agent-execution-service-agex)
    - [Conversation Service (CONV)](#conversation-service-conv)
    - [Workflow Engine Service (WFLOW)](#workflow-engine-service-wflow)
    - [Tool Registry Service (TOOL)](#tool-registry-service-tool)
  - [5. Estrategia de Reintentos](#5-estrategia-de-reintentos)
    - [Categorías de Reintentos](#categorías-de-reintentos)
    - [Algoritmo de Backoff](#algoritmo-de-backoff)
  - [6. Logging y Telemetría de Errores](#6-logging-y-telemetría-de-errores)

## 1. Introducción

Este documento define la matriz de errores estándar para todo el Agent Orchestrator Service y sus servicios relacionados. Establece una correlación clara entre códigos HTTP, códigos de error internos, y recomendaciones de manejo para cada tipo de error.

## 2. Estructura de Códigos de Error

Todos los códigos de error específicos siguen el formato:

```
{SERVICIO}_{CATEGORÍA}_{NÚMERO}
```

Donde:
- **SERVICIO**: Código de 4 letras que identifica el servicio (ej. ORCH, AGEX)
- **CATEGORÍA**: Código de 3 letras que identifica el tipo de error (ej. VAL, AUTH)
- **NÚMERO**: Secuencial numérico de 3 dígitos

**Servicios**:
- ORCH: Agent Orchestrator Service
- AGEX: Agent Execution Service
- CONV: Conversation Service
- WFLOW: Workflow Engine
- TOOL: Tool Registry

**Categorías**:
- AUTH: Autenticación/Autorización
- VAL: Validación
- EXEC: Ejecución
- CFG: Configuración
- CONN: Conexión/Networking
- RATE: Rate limiting
- SYS: Sistema interno
- DB: Base de datos

## 3. Matriz de Errores Comunes

### 4xx - Errores del Cliente

| HTTP Status | Código Interno     | Descripción                            | Reintentable | Acción Recomendada                                |
|------------|--------------------|-----------------------------------------|--------------|--------------------------------------------------|
| 400        | `validation_error` | Datos de solicitud incorrectos          | No           | Corregir formato de solicitud                    |
| 400        | `invalid_session`  | Sesión inválida o expirada              | No           | Iniciar nueva sesión                             |
| 401        | `unauthorized`     | Credenciales inválidas o expiradas      | No           | Renovar token de autenticación                   |
| 403        | `forbidden`        | Sin permisos para el recurso solicitado | No           | Solicitar acceso o elevar privilegios            |
| 404        | `resource_not_found` | Recurso no encontrado                 | No           | Verificar identificadores y paths                |
| 409        | `conflict`         | Conflicto de estado o recurso           | No           | Resolver el conflicto y reintentar              |
| 413        | `payload_too_large` | Carga útil demasiado grande            | No           | Reducir tamaño de la solicitud                  |
| 422        | `unprocessable_content` | Formato correcto pero contenido inválido | No      | Verificar reglas de negocio                     |
| 429        | `rate_limited`     | Se excedió el límite de tasa            | Sí           | Esperar según header Retry-After                |

### 5xx - Errores del Servidor

| HTTP Status | Código Interno          | Descripción                          | Reintentable | Acción Recomendada                               |
|------------|-----------------------|-------------------------------------|-------------|--------------------------------------------------|
| 500        | `service_error`       | Error interno del servicio           | Sí          | Reintento con backoff exponencial                |
| 501        | `not_implemented`     | Funcionalidad no implementada        | No          | Reportar como bug o solicitar feature            |
| 502        | `bad_gateway`         | Error en servicio dependiente        | Sí          | Reintento con backoff exponencial                |
| 503        | `service_unavailable` | Servicio temporalmente no disponible | Sí          | Reintento con backoff exponencial                |
| 503        | `circuit_open`        | Circuit breaker abierto              | Sí          | Esperar a que el circuit breaker se cierre       |
| 504        | `timeout`             | Timeout en la operación              | Sí          | Reintento con backoff exponencial                |

## 4. Errores Específicos por Servicio

### Agent Orchestrator Service (ORCH)

| Código           | HTTP Status | Descripción                             | Reintentable |
|--------------------|------------|----------------------------------------|--------------|
| `ORCH_AUTH_001`    | 401        | Token JWT inválido                     | No           |
| `ORCH_AUTH_002`    | 403        | Tenant no autorizado                   | No           |
| `ORCH_VAL_001`     | 400        | Formato de mensaje inválido            | No           |
| `ORCH_CONN_001`    | 503        | Error de conexión a servicio interno   | Sí           |
| `ORCH_RATE_001`    | 429        | Límite de sesiones excedido            | Sí           |
| `ORCH_SYS_001`     | 500        | Error interno de orquestación          | Sí           |

### Agent Execution Service (AGEX)

| Código           | HTTP Status | Descripción                             | Reintentable |
|--------------------|------------|----------------------------------------|--------------|
| `AGEX_VAL_001`     | 400        | Configuración de agente inválida       | No           |
| `AGEX_EXEC_001`    | 500        | Error de ejecución del agente          | Sí           |
| `AGEX_EXEC_002`    | 504        | Timeout en respuesta del modelo        | Sí           |
| `AGEX_CONN_001`    | 502        | Error de conexión al proveedor LLM     | Sí           |
| `AGEX_RATE_001`    | 429        | Límite de tokens excedido              | Sí           |

### Conversation Service (CONV)

| Código           | HTTP Status | Descripción                             | Reintentable |
|--------------------|------------|----------------------------------------|--------------|
| `CONV_VAL_001`     | 400        | Formato de mensaje inválido            | No           |
| `CONV_DB_001`      | 500        | Error de persistencia de mensajes      | Sí           |
| `CONV_DB_002`      | 404        | Conversación no encontrada             | No           |
| `CONV_SYS_001`     | 500        | Error en procesamiento de mensajes     | Sí           |

### Workflow Engine Service (WFLOW)

| Código           | HTTP Status | Descripción                             | Reintentable |
|--------------------|------------|----------------------------------------|--------------|
| `WFLOW_VAL_001`    | 400        | Definición de workflow inválida        | No           |
| `WFLOW_EXEC_001`   | 500        | Error en ejecución de workflow         | Sí           |
| `WFLOW_EXEC_002`   | 504        | Timeout en paso de workflow            | Sí           |
| `WFLOW_DB_001`     | 404        | Workflow template no encontrado        | No           |

### Tool Registry Service (TOOL)

| Código           | HTTP Status | Descripción                             | Reintentable |
|--------------------|------------|----------------------------------------|--------------|
| `TOOL_VAL_001`     | 400        | Parámetros de herramienta inválidos    | No           |
| `TOOL_EXEC_001`    | 500        | Error en ejecución de herramienta      | Sí           |
| `TOOL_EXEC_002`    | 504        | Timeout en ejecución de herramienta    | Sí           |
| `TOOL_DB_001`      | 404        | Herramienta no encontrada              | No           |
| `TOOL_CONN_001`    | 502        | Error de conexión a API externa        | Sí           |

## 5. Estrategia de Reintentos

### Categorías de Reintentos

Los errores se clasifican en tres categorías de reintentos:

1. **No Reintentable**: Errores que no deben reintentarse (400, 401, 403, 404)
2. **Reintentable con Espera Específica**: Errores con instrucciones específicas (429)
3. **Reintentable con Backoff**: Errores transitorios que deben reintentarse (500, 502, 503, 504)

### Algoritmo de Backoff

Para errores reintentables, se recomienda:

```javascript
// Parámetros recomendados
const maxRetries = 5;
const baseDelay = 1000; // 1 segundo
const maxDelay = 30000; // 30 segundos
const jitterFactor = 0.2; // ±20% 

// Algoritmo
const calculateBackoff = (attempt) => {
  // Exponential backoff: baseDelay * 2^attempt
  const exponentialDelay = Math.min(
    baseDelay * Math.pow(2, attempt),
    maxDelay
  );
  
  // Add jitter: random value between ±jitterFactor of delay
  const jitterRange = exponentialDelay * jitterFactor;
  const jitter = jitterRange * (Math.random() * 2 - 1);
  
  return exponentialDelay + jitter;
};
```

## 6. Logging y Telemetría de Errores

Todos los errores deben registrarse con el siguiente formato:

```json
{
  "timestamp": "ISO-8601",
  "level": "ERROR",
  "error_code": "ORCH_AUTH_001",
  "http_status": 401,
  "service": "agent_orchestrator",
  "message": "Descripción legible",
  "tenant_id": "tenant-id",
  "correlation_id": "uuid-v4",
  "request_id": "uuid-v4",
  "stack_trace": "...",
  "metadata": {
    "request_path": "/api/sessions",
    "method": "POST"
  }
}
```

Los errores críticos (500, 502, 503, 504) deben generar alertas automáticas cuando:
1. Ocurren más de 10 veces en un minuto
2. Afectan a más del 5% de las solicitudes totales
3. Persisten por más de 2 minutos

Métricas clave a monitorear:
- Tasa de error por endpoint
- Tasa de error por tipo de error
- Tasa de error por tenant
- Distribución de latencia por endpoint
