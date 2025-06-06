# Comunicación Interna - Agent Execution Service

Esta documentación se basa en el [template estándar de comunicación interna](../../../common/templates/internal_communication_template.md).

## Datos Específicos del Servicio

### Información General

- **SERVICE_NAME**: Agent Execution Service
- **VERSION**: 1.0.0
- **DATE**: 2025-06-03
- **IMPORTANT_NOTE**: El Agent Execution Service es responsable de la ejecución directa de los agentes, interactuando con LLMs y herramientas. Cualquier modificación en sus protocolos de comunicación debe ser coordinada con el Agent Orchestrator Service.
- **SERVICE_DIAGRAM**: execution_service_communication.png

### Visión General

**VISION_GENERAL_DESCRIPTION**: Este documento detalla los mecanismos de comunicación interna utilizados por el Agent Execution Service para procesar la lógica de los agentes, interactuar con LLMs, y coordinar el uso de herramientas. Como componente central de ejecución, este servicio implementa patrones de procesamiento de mensajes y streaming de respuestas en tiempo real.

**PRINCIPLES_LIST**:
- **Ejecución Optimizada**: Diseñado para minimizar latencia en la ejecución de agentes
- **Aislamiento Contextual**: Cada ejecución mantiene su propio contexto aislado
- **Streaming Nativo**: Soporte integrado para procesamiento y transmisión de tokens incrementales
- **Integración con Herramientas**: Sistema flexible para conectar con herramientas externas e internas
- **Razonamiento Trazable**: Registro completo del proceso de razonamiento de los agentes

**RESPONSIBILITIES_LIST**:
1. **Ejecución de Agentes**: Procesamiento de la lógica central de los agentes
2. **Llamadas a LLM**: Gestión optimizada de solicitudes a modelos de lenguaje
3. **Coordinación de Herramientas**: Detección y delegación de llamadas a herramientas
4. **Streaming de Respuestas**: Transmisión de tokens incrementales en tiempo real
5. **Registro de Razonamiento**: Captura del proceso de razonamiento de los agentes

### Estructura de Colas

**QUEUE_HIERARCHY**: 
```
                  +-----------------------------------+
                  |        COLAS DE EJECUCIÓN         |
                  +-----------------------------------+
                                 |
      +---------------------+--------------------+-------------------+
      |                     |                    |                   |
+----------------+  +------------------+  +---------------+  +------------------+
| Ejecuciones    |  | Streaming       |  | Herramientas  |  | Administración   |
+----------------+  +------------------+  +---------------+  +------------------+
|                |  |                  |  |               |  |                  |
| agent.         |  | agent.           |  | agent.        |  | agent.           |
| execution.     |  | streaming.       |  | tool.         |  | admin.           |
| {tenant_id}    |  | {tenant_id}.     |  | requests.     |  | {tenant_id}      |
|                |  | {execution_id}   |  | {tenant_id}   |  |                  |
+----------------+  +------------------+  +---------------+  +------------------+
```

**QUEUES_TABLE**:
```
| `agent.execution.{tenant_id}` | Cola principal para tareas de ejecución | 30 minutos | Alta |
| `agent.execution.priority.{tenant_id}` | Cola para ejecuciones prioritarias | 15 minutos | Crítica |
| `agent.streaming.{tenant_id}.{execution_id}` | Streaming de tokens incrementales | 5 minutos | Alta |
| `agent.responses.{tenant_id}.{execution_id}` | Respuestas finales de ejecuciones | 30 minutos | Media |
| `agent.tool.requests.{tenant_id}` | Solicitudes de llamadas a herramientas | 15 minutos | Alta |
| `agent.execution.status.{tenant_id}` | Actualizaciones de estado de ejecución | 10 minutos | Media |
| `agent.execution.cancellation.{tenant_id}` | Cancelaciones de ejecución | 5 minutos | Crítica |
```

**COMMUNICATION_TOPOLOGY_DESCRIPTION**: La estructura de comunicación del Agent Execution Service sigue un modelo de procesamiento distribuido, donde:

- **Punto de Entrada**: Recibe tareas del Orchestrator Service
- **Punto de Salida**: Envía resultados y actualizaciones al Orchestrator
- **Conexiones Laterales**: Interactúa con Query Service (LLM) y Tool Registry

**COMMUNICATION_TOPOLOGY_DIAGRAM**:
```
graph TB
    AO[Agent Orchestrator] --> AES[Agent Execution Service]
    AES --> AO
    AES --> QS[Query Service]
    AES --> TR[Tool Registry]
    QS --> AES
    TR --> AES
    
    classDef execution fill:#f96,stroke:#333,stroke-width:4px;
    classDef services fill:#c9e,stroke:#333,stroke-width:2px;
    
    class AES execution;
    class AO,QS,TR services;
```

### Mensajes y Comunicación

**DOMAIN_VALUES**: "agent|tool|llm|status"
**ACTION_VALUES**: "execute|response|tool_request|tool_response|streaming|cancel|error"

**MESSAGE_TYPES_TABLE**:
```
| `agent` | `execute` | Petición de ejecución de agente | 2 |
| `agent` | `response` | Respuesta final de agente | 2 |
| `agent` | `streaming` | Token incremental de respuesta | 1 |
| `tool` | `request` | Solicitud de ejecución de herramienta | 3 |
| `tool` | `response` | Respuesta de una herramienta | 3 |
| `llm` | `request` | Solicitud a modelo de lenguaje | 2 |
| `llm` | `response` | Respuesta de modelo de lenguaje | 2 |
| `status` | `update` | Actualización de estado de ejecución | 4 |
| `agent` | `cancel` | Cancelación de ejecución en curso | 0 |
| `agent` | `error` | Notificación de error | 1 |
```

**MULTISERVICE_CONSISTENCY**: Para garantizar la coherencia entre servicios, el Agent Execution Service implementa:

1. **Contexto Compartido**: Cada ejecución mantiene un identificador de correlación consistente
2. **Estado Distribuido**: Los estados de ejecución se persisten en Redis con TTL adecuados
3. **Transacciones Multi-etapa**: Las operaciones complejas se dividen en etapas verificables
4. **Idempotencia**: Todas las operaciones críticas son idempotentes para permitir reintentos seguros

### Flujos

**BASIC_ASYNC_FLOW**:
```
participant O as Orchestrator
participant AE as Agent Execution
participant Q as Query Service

O->>AE: Ejecutar agente
AE->>Q: Consulta LLM
Q->>AE: Respuesta
AE->>O: Resultado final
```

**COORDINATION_FLOW**:
```
participant O as Orchestrator
participant AE as Agent Execution
participant Q as Query Service
participant TR as Tool Registry

O->>AE: Consulta con potencial uso de herramientas
AE->>Q: Primer paso LLM
Q->>AE: Identificación de herramienta necesaria
AE->>O: Solicitud de ejecución de herramienta
O->>TR: Ejecutar herramienta
TR->>O: Resultado de herramienta
O->>AE: Continuar con resultado de herramienta
AE->>Q: Segunda consulta LLM
Q->>AE: Respuesta final
AE->>O: Resultado completo
```

**HIGH_AVAILABILITY_FLOWS**: El Agent Execution Service implementa los siguientes patrones de disponibilidad:

1. **Procesamiento Paralelo**: Múltiples instancias pueden procesar diferentes ejecuciones simultáneamente
2. **Recuperación de Sesión**: Capacidad de reanudar ejecuciones parciales en caso de fallos
3. **Estado Inmutable**: Cada paso de ejecución se registra como estado inmutable 
4. **Balanceo de Carga**: Distribución automática de carga entre instancias disponibles
5. **Degradación Controlada**: Reducción de complejidad en situaciones de alta carga

### Configuraciones

**TIMEOUT_CONFIG**:
```
| Ejecución completa de agente | 45000ms | 120000ms | Respuesta parcial |
| Llamada individual a LLM | 15000ms | 30000ms | Reintento con modelo más pequeño |
| Procesamiento de herramienta | 10000ms | 20000ms | Skip con notificación |
| Generación de token (streaming) | 1000ms | 5000ms | Continuar sin ese token |
```

**RETRY_POLICY**: Las políticas de reintento para el Agent Execution Service son:

1. **Reintentos LLM**: 3 reintentos con backoff exponencial (base: 200ms)
2. **Cambio de modelo**: Después de 2 fallos, intento con modelo alternativo
3. **Fragmentación**: División de prompts muy largos en caso de timeouts
4. **Reintentos selectivos**: Solo se reintenta en errores transitorios (429, 503, etc.)
5. **Preservación de contexto**: Todos los reintentos mantienen el contexto original completo

**CIRCUIT_BREAKER**: 
- **Umbral de apertura**: 3 fallos consecutivos en un servicio específico
- **Duración de estado abierto**: 10 segundos
- **Prueba en semi-abierto**: 1 solicitud de prueba
- **Monitoreo diferenciado**: Circuitos independientes para cada tipo de operación (LLM, herramientas)

**RECOVERY_STRATEGIES**:
1. **Checkpoints de ejecución**: Guardado de estados intermedios para recuperación
2. **Registro detallado**: Captura completa de entradas/salidas para diagnóstico
3. **Reejecution parcial**: Capacidad de reanudar desde último punto de éxito
4. **Simplificación adaptativa**: Reducción automática de complejidad en reintentos
5. **Notificación de degradación**: Alertas claras cuando se activan modos degradados

### Comunicación con Otros Servicios

**SERVICE_SPECIFIC_COMMUNICATION**: 

#### Communicación con Agent Orchestrator
- **Entrada**: Recibe solicitudes de ejecución, configuraciones y contextos
- **Salida**: Envía resultados finales, tokens incrementales y actualizaciones de estado
- **Control**: Recibe señales de cancelación y gestión de prioridad

#### Comunicación con Query Service
- **Envío**: Prompts estructurados con parámetros de configuración
- **Recepción**: Respuestas completas o streaming de tokens
- **Control de congestión**: Limitación automática de rate según capacidad

#### Comunicación con Tool Registry
- **Indirecta**: La comunicación con herramientas se realiza a través del Orchestrator
- **Directa (modo avanzado)**: En configuraciones específicas, puede comunicarse directamente

### Métricas

**METRICS_TABLE**:
```
| **Rendimiento** | `execution.duration` | Tiempo total de ejecución por tipo de agente | Sí (>10s) |
| **Rendimiento** | `llm.response_time` | Tiempo de respuesta de modelos de lenguaje | Sí (>5s) |
| **Tokens** | `llm.token_count` | Número de tokens por solicitud/respuesta | No |
| **Calidad** | `agent.success_rate` | Tasa de ejecuciones exitosas | Sí (<95%) |
| **Recursos** | `memory.usage` | Uso de memoria por ejecución | Sí (>500MB) |
| **Latencia** | `streaming.first_token_time` | Tiempo hasta primer token | Sí (>2s) |
| **Errores** | `execution.error_rate` | Tasa de errores por tipo | Sí (>3%) |
| **Volumen** | `execution.request_rate` | Solicitudes por minuto | No |
```

### Registro de Cambios

**INITIAL_DATE**: 2025-05-10
**INITIAL_VERSION**: 0.9.0
**INITIAL_AUTHOR**: Equipo Nooble Backend
