# Catálogo de Errores - Agent Management Service

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
- [Catálogo de Errores - Agent Management Service](#catálogo-de-errores---agent-management-service)
  - [Índice](#índice)
  - [1. Visión General](#1-visión-general)
  - [2. Formato Estándar de Error](#2-formato-estándar-de-error)
  - [3. Categorías de Errores](#3-categorías-de-errores)
    - [3.1 Errores de Validación (100-199)](#31-errores-de-validación-100-199)
    - [3.2 Errores de Autenticación y Autorización (200-299)](#32-errores-de-autenticación-y-autorización-200-299)
    - [3.3 Errores de Recurso (300-399)](#33-errores-de-recurso-300-399)
    - [3.4 Errores de Sistema (500-599)](#34-errores-de-sistema-500-599)
    - [3.5 Errores de Integración (600-699)](#35-errores-de-integración-600-699)
  - [4. Mapeo de Códigos HTTP](#4-mapeo-de-códigos-http)
  - [5. Estrategias de Manejo de Errores](#5-estrategias-de-manejo-de-errores)
    - [5.1 Errores Recuperables vs No Recuperables](#51-errores-recuperables-vs-no-recuperables)
    - [5.2 Políticas de Reintento](#52-políticas-de-reintento)
  - [6. Logging y Monitoreo](#6-logging-y-monitoreo)
  - [7. Registro de Cambios](#7-registro-de-cambios)

## 1. Visión General

Este documento cataloga todos los posibles errores que pueden ocurrir en el Agent Management Service, proporciona recomendaciones para su manejo y establece el formato estándar para reportarlos.

## 2. Formato Estándar de Error

Todos los errores del servicio siguen la siguiente estructura JSON:

```json
{
  "error": {
    "code": "AMS-101",
    "message": "Mensaje descriptivo del error",
    "details": {
      "field": "campo_específico",
      "reason": "razón_específica",
      "suggestion": "sugerencia_para_solucionar"
    },
    "request_id": "uuid-string",
    "timestamp": "ISO-timestamp",
    "documentation_url": "https://docs.nooble.com/errors/AMS-101"
  }
}
```

## 3. Categorías de Errores

### 3.1 Errores de Validación (100-199)

| Código | Mensaje | Descripción | HTTP Status |
|--------|---------|-------------|------------|
| AMS-101 | Invalid agent name | El nombre del agente contiene caracteres no permitidos o está vacío | 400 |
| AMS-102 | Agent name already exists | Ya existe un agente con este nombre en el tenant | 409 |
| AMS-103 | System prompt exceeds maximum length | El prompt del sistema excede el límite de caracteres | 400 |
| AMS-104 | Invalid tool configuration | Configuración de herramienta inválida o incompleta | 400 |
| AMS-105 | Too many tools assigned | El número de herramientas excede el máximo permitido | 400 |
| AMS-106 | Invalid memory configuration | Configuración de memoria inválida o incompleta | 400 |
| AMS-107 | Invalid LLM configuration | Configuración de LLM inválida o incompleta | 400 |
| AMS-108 | LLM model not available for tenant tier | El modelo LLM seleccionado no está disponible en el tier actual | 403 |

### 3.2 Errores de Autenticación y Autorización (200-299)

| Código | Mensaje | Descripción | HTTP Status |
|--------|---------|-------------|------------|
| AMS-201 | Authentication required | No se ha proporcionado token de autenticación | 401 |
| AMS-202 | Invalid authentication token | El token proporcionado no es válido | 401 |
| AMS-203 | Token expired | El token ha expirado | 401 |
| AMS-204 | Insufficient permissions | El usuario no tiene permisos para esta operación | 403 |
| AMS-205 | Tenant ID required | No se ha especificado el ID del tenant | 400 |
| AMS-206 | Invalid tenant ID | El ID del tenant no existe o no tiene acceso | 403 |
| AMS-207 | Tenant quota exceeded | El tenant ha excedido su cuota de agentes | 403 |

### 3.3 Errores de Recurso (300-399)

| Código | Mensaje | Descripción | HTTP Status |
|--------|---------|-------------|------------|
| AMS-301 | Agent not found | No se encontró el agente especificado | 404 |
| AMS-302 | Agent version not found | No se encontró la versión del agente especificada | 404 |
| AMS-303 | Agent template not found | No se encontró la plantilla de agente especificada | 404 |
| AMS-304 | Agent in use | El agente está siendo utilizado y no puede ser modificado/eliminado | 409 |
| AMS-305 | Invalid agent status transition | La transición de estado solicitada no es válida | 400 |

### 3.4 Errores de Sistema (500-599)

| Código | Mensaje | Descripción | HTTP Status |
|--------|---------|-------------|------------|
| AMS-501 | Internal server error | Error interno del servidor | 500 |
| AMS-502 | Database connection error | Error de conexión a la base de datos | 500 |
| AMS-503 | Message queue error | Error en la cola de mensajes | 500 |
| AMS-504 | Service temporarily unavailable | Servicio temporalmente no disponible | 503 |
| AMS-505 | Operation timeout | La operación ha excedido el tiempo máximo permitido | 504 |

### 3.5 Errores de Integración (600-699)

| Código | Mensaje | Descripción | HTTP Status |
|--------|---------|-------------|------------|
| AMS-601 | Tool registry service unavailable | Servicio de registro de herramientas no disponible | 503 |
| AMS-602 | Invalid tool reference | Referencia a herramienta inválida o no existente | 400 |
| AMS-603 | LLM provider error | Error en el proveedor de LLM | 502 |
| AMS-604 | Agent orchestration error | Error en la orquestación del agente | 502 |

## 4. Mapeo de Códigos HTTP

| HTTP Status | Uso común |
|-------------|-----------|
| 400 Bad Request | Validaciones fallidas, parámetros incorrectos |
| 401 Unauthorized | Problemas de autenticación |
| 403 Forbidden | Problemas de autorización, limitaciones de tier |
| 404 Not Found | Recursos no encontrados |
| 409 Conflict | Conflictos de estado o recursos |
| 500 Internal Server Error | Errores internos no especificados |
| 502 Bad Gateway | Errores en servicios externos |
| 503 Service Unavailable | Servicio temporalmente no disponible |
| 504 Gateway Timeout | Operaciones que exceden el tiempo límite |

## 5. Estrategias de Manejo de Errores

### 5.1 Errores Recuperables vs No Recuperables

**Errores Recuperables:**
- Problemas temporales de conexión (AMS-502, AMS-503)
- Timeouts ocasionales (AMS-505)
- Servicios externos temporalmente no disponibles (AMS-601, AMS-603)

**Errores No Recuperables:**
- Errores de validación (AMS-101 a AMS-108)
- Problemas de autenticación/autorización (AMS-201 a AMS-207)
- Recursos no encontrados (AMS-301 a AMS-305)

### 5.2 Políticas de Reintento

| Tipo de Error | Reintento | Estrategia |
|---------------|-----------|------------|
| Conexión a base de datos | Sí | Exponential backoff, max 3 intentos |
| Cola de mensajes | Sí | Exponential backoff, max 5 intentos |
| LLM provider | Sí | Exponential backoff, max 2 intentos |
| Tool registry | Sí | Intentos fijos cada 2 segundos, max 3 intentos |
| Validación | No | N/A |
| Autenticación | No | N/A |

## 6. Logging y Monitoreo

Todos los errores se registran con la siguiente información:

- Código de error
- Mensaje de error
- ID de solicitud
- ID de tenant
- ID de usuario (si está autenticado)
- Timestamp
- Stack trace (solo errores internos, no se expone al cliente)
- Contexto adicional (datos específicos de la operación)

Los errores críticos (series 500 y 600) generan alertas automáticas al equipo de operaciones.

## 7. Registro de Cambios

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0.0 | 2025-06-03 | Versión inicial del documento |
