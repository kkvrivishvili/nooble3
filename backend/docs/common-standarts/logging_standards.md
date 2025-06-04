# Estándares de Logs y Trazabilidad

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Estructura de Logs](#2-estructura-de-logs)
3. [Niveles de Log](#3-niveles-de-log)
4. [Categorías de Log](#4-categorías-de-log)
5. [Identificadores de Trazabilidad](#5-identificadores-de-trazabilidad)
6. [Retención de Logs](#6-retención-de-logs)
7. [Buenas Prácticas](#7-buenas-prácticas)
8. [Integración con Servicios Externos](#8-integración-con-servicios-externos)

## 1. Introducción

Este documento establece los estándares para la generación, formato y gestión de logs en todos los microservicios de la plataforma Nooble AI. El objetivo es garantizar la consistencia, facilitar la trazabilidad y simplificar el diagnóstico de problemas en un entorno distribuido.

### 1.1 Principios Generales

- **Consistencia**: Formato uniforme en todos los servicios
- **Completitud**: Información suficiente para diagnóstico sin datos sensibles
- **Trazabilidad**: Seguimiento completo de solicitudes entre servicios
- **Eficiencia**: Optimización del volumen y nivel de detalle
- **Multi-tenancy**: Separación clara por tenant para facilitar filtrado

## 2. Estructura de Logs

Todos los logs deben generarse en formato JSON estructurado con los siguientes campos obligatorios:

```json
{
  "timestamp": "2025-06-03T15:30:45.123Z",  // ISO-8601 con precisión de milisegundos
  "level": "INFO",                          // Nivel de log (ver sección 3)
  "service": "workflow-engine",             // Nombre del servicio
  "tenant_id": "tenant-123",                // Identificador del tenant
  "correlation_id": "uuid-v4",              // ID para correlacionar entre servicios
  "session_id": "session-xyz",              // ID de sesión (si aplica)
  "category": "business",                   // Categoría del log (ver sección 4)
  "message": "Workflow execution started",  // Mensaje descriptivo
  "context": {                              // Contexto adicional específico
    "workflow_id": "wf-123",
    "execution_id": "exec-456"
    // Campos adicionales específicos de cada operación
  }
}
```

### 2.1 Campos Obligatorios

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| timestamp | Momento exacto del evento en ISO-8601 | "2025-06-03T15:30:45.123Z" |
| level | Nivel de importancia del log | "INFO" |
| service | Nombre del servicio que genera el log | "workflow-engine" |
| tenant_id | Identificador del tenant | "tenant-123" |
| correlation_id | Identificador para trazabilidad | "3fa85f64-5717-4562-b3fc-2c963f66afa6" |
| message | Descripción concisa del evento | "Workflow execution started" |

### 2.2 Campos Opcionales

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| session_id | ID de sesión de usuario | "session-xyz" |
| user_id | ID del usuario final | "user-789" |
| request_id | ID de la solicitud específica | "req-567" |
| duration_ms | Duración de la operación en ms | 125 |
| resource_id | ID del recurso afectado | "agent-456" |

## 3. Niveles de Log

Los servicios deben respetar los siguientes niveles de log con sus usos específicos:

| Nivel | Propósito | Ejemplos de Uso |
|-------|-----------|-----------------|
| DEBUG | Información detallada para desarrollo | Valores intermedios, decisiones de código, pasos detallados |
| INFO | Eventos operativos normales | Inicio/fin de operaciones, solicitudes recibidas, mensajes enviados |
| WARNING | Situaciones inesperadas recuperables | Reintentos, errores transitorios, degradación de servicio |
| ERROR | Errores que afectan funcionalidad | Fallo en operaciones de negocio, errores en API externas, excepciones |
| CRITICAL | Errores críticos que requieren intervención | Fallos de infraestructura, brechas de seguridad, corrupción de datos |

> **Importante**: Los logs de nivel DEBUG no deben activarse en entornos de producción excepto para diagnósticos temporales.

## 4. Categorías de Log

Para facilitar el filtrado y análisis, cada log debe pertenecer a una de estas categorías:

| Categoría | Descripción | Ejemplo |
|-----------|-------------|---------|
| system | Eventos del sistema y ciclo de vida | Inicio/parada del servicio, conexiones a bases de datos |
| business | Eventos de lógica de negocio | Ejecución de workflow, procesamiento de agentes, RAG |
| security | Eventos relacionados con seguridad | Autenticación, autorización, validación de token |
| performance | Métricas y rendimiento | Tiempos de respuesta, uso de recursos, latencia |
| external | Integración con servicios externos | Llamadas a APIs externas, integraciones LLM |

## 5. Identificadores de Trazabilidad

La trazabilidad completa de solicitudes requiere:

### 5.1 Correlation ID

Identificador único que se propaga entre todos los servicios involucrados en una misma solicitud de usuario.

- Debe generarse en el punto de entrada (Agent Orchestrator)
- Debe transmitirse en cabeceras HTTP (`X-Correlation-ID`) y campos de mensajes
- Debe incluirse en todos los logs relacionados con la solicitud

### 5.2 Session ID

Identificador de la sesión del usuario que inicia la solicitud.

- Permite agrupar múltiples solicitudes relacionadas a una misma sesión
- Facilita el análisis de comportamiento y experiencia de usuario

## 6. Retención de Logs

Los logs deben gestionarse según estas políticas de retención:

| Nivel | Retención Estándar | Retención para Tenants Enterprise |
|-------|---------------------|-----------------------------------|
| DEBUG | 3 días | 7 días |
| INFO | 30 días | 90 días |
| WARNING | 60 días | 180 días |
| ERROR | 90 días | 365 días |
| CRITICAL | 365 días | 730 días |

## 7. Buenas Prácticas

### 7.1 Mensajes de Log

- Usar mensajes concisos pero descriptivos
- Incluir identificadores relevantes en el mensaje
- Evitar información sensible (API keys, tokens, credenciales)
- Utilizar formato consistente para estructuras recurrentes

### 7.2 Volumen de Logs

- Mantener equilibrio entre detalle y volumen
- Evitar logs repetitivos para operaciones de alto volumen
- Utilizar muestreo para operaciones frecuentes
- Agrupar logs relacionados cuando sea posible

### 7.3 Excepciones

- Log completo de stack trace solo en nivel ERROR o CRITICAL
- Capturar y registrar causa raíz de excepciones
- Incluir contexto suficiente para diagnóstico

## 8. Integración con Servicios Externos

### 8.1 Centralización de Logs

Todos los servicios deben enviar logs a un sistema centralizado (ELK Stack):

```python
# Ejemplo de configuración de logger
def setup_logger():
    """Configura el logger con formato estándar Nooble"""
    logger = logging.getLogger("nooble-service")
    handler = logging.StreamHandler()
    
    formatter = JsonLogFormatter(
        service_name=SERVICE_NAME,
        default_context={
            "environment": ENVIRONMENT,
            "version": SERVICE_VERSION
        }
    )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Configuración para envío a ELK
    elk_handler = ElkLogHandler(
        elk_url=ELK_URL,
        elk_index=f"nooble-{SERVICE_NAME}",
        elk_auth_token=ELK_AUTH_TOKEN
    )
    logger.addHandler(elk_handler)
    
    return logger
```

### 8.2 Dashboards y Alertas

- Cada servicio debe definir dashboards básicos para sus logs
- Configurar alertas automáticas para patrones de ERROR y CRITICAL
- Implementar detección de anomalías para comportamientos inusuales
