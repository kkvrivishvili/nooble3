# Integración del Frontend con Workflow Engine Service - Parte 3

## Conexión WebSocket para Actualizaciones en Tiempo Real

El Workflow Engine Service proporciona una interfaz WebSocket para recibir actualizaciones en tiempo real sobre el estado de ejecuciones de workflows, cambios en workflows y notificaciones del sistema.

```
WebSocket URL: wss://api.domain.com/api/workflows/ws
```

**Headers requeridos para la conexión:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`

### Autenticación del WebSocket

Una vez establecida la conexión WebSocket, el cliente debe enviar un mensaje de autenticación:

```json
{
  "action": "authenticate",
  "token": "jwt-token",
  "tenant_id": "tenant-id"
}
```

### Suscripción a Eventos

Para recibir actualizaciones sobre workflows o ejecuciones específicas:

```json
{
  "action": "subscribe",
  "topics": [
    "workflow:uuid-workflow-1",
    "workflow:uuid-workflow-2",
    "execution:uuid-execution-1"
  ]
}
```

Para suscribirse a todas las actualizaciones (solo administradores):

```json
{
  "action": "subscribe",
  "topics": ["all_workflows", "all_executions"]
}
```

### Eventos del WebSocket

#### Actualización de estado de workflow

```json
{
  "event": "workflow_updated",
  "workflow_id": "uuid-string",
  "name": "Data Enrichment Workflow",
  "version": "1.1.0",
  "previous_status": "draft",
  "status": "active",
  "updated_at": "ISO-timestamp",
  "updated_by": "user-id"
}
```

#### Actualización de ejecución de workflow

```json
{
  "event": "workflow_execution_update",
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "status": "running|completed|failed|cancelled",
  "current_step": "enrich_data",
  "progress": 0.6,
  "timestamp": "ISO-timestamp",
  "details": {
    "step_name": "Data Enrichment",
    "started_at": "ISO-timestamp",
    "message": "Procesando datos..."
  }
}
```

#### Paso de workflow completado

```json
{
  "event": "workflow_step_completed",
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "step_id": "enrich_data",
  "step_name": "Data Enrichment",
  "output": {
    "data": {
      "company_size": "101-250",
      "industry": "Technology",
      "founded_year": 2010
    },
    "success": true
  },
  "duration_ms": 1250,
  "next_step": "decision",
  "timestamp": "ISO-timestamp"
}
```

#### Error en ejecución de workflow

```json
{
  "event": "workflow_execution_error",
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "error": {
    "step_id": "lookup",
    "step_name": "Customer Lookup",
    "message": "Error al conectar con el servicio de CRM",
    "code": "external_service_error",
    "details": "Timeout después de 5000ms"
  },
  "timestamp": "ISO-timestamp"
}
```

#### Terminación de workflow

```json
{
  "event": "workflow_execution_completed",
  "execution_id": "uuid-string",
  "workflow_id": "uuid-string",
  "status": "completed|failed|cancelled",
  "started_at": "ISO-timestamp",
  "completed_at": "ISO-timestamp",
  "duration_ms": 3500,
  "output": {
    "customer": {
      "name": "Test Company",
      "company_domain": "example.com"
    },
    "enriched_data": {
      "company_size": "101-250",
      "industry": "Technology",
      "founded_year": 2010
    },
    "success": true
  },
  "timestamp": "ISO-timestamp"
}
```

## Manejo de Errores

### Formato de Error Estándar

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {},
    "request_id": "uuid-string"
  }
}
```

### Códigos de Error Específicos

- `workflow_not_found`: Workflow no existe
- `execution_not_found`: Ejecución no existe
- `invalid_workflow_definition`: Definición de workflow inválida
- `workflow_execution_error`: Error durante la ejecución
- `step_configuration_error`: Configuración de paso inválida
- `invalid_input`: Datos de entrada inválidos
- `timeout`: Ejecución excedió el tiempo máximo
- `permission_denied`: Sin permisos para esta operación
- `tier_restriction`: Función no disponible en este tier

## Ejemplos de Código

### Crear un Workflow (JavaScript)

```javascript
const createWorkflow = async (workflowData, authToken, tenantId) => {
  try {
    const response = await fetch('https://api.domain.com/api/workflows', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(workflowData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error creating workflow:', error);
    throw error;
  }
};
```

### Ejecutar un Workflow para Pruebas (JavaScript)

```javascript
const testExecuteWorkflow = async (workflowId, inputData, authToken, tenantId) => {
  try {
    const response = await fetch(`https://api.domain.com/api/workflows/${workflowId}/test-execute`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        input: inputData,
        debug_mode: true
      })
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error executing workflow:', error);
    throw error;
  }
};
```

### Monitorear Ejecución de Workflow con WebSocket (JavaScript)

```javascript
const monitorWorkflowExecution = (executionId, workflowId, authToken, tenantId, callbacks) => {
  const ws = new WebSocket(`wss://api.domain.com/api/workflows/ws`);
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  
  ws.onopen = () => {
    reconnectAttempts = 0;
    
    // Autenticar
    ws.send(JSON.stringify({
      action: "authenticate",
      token: authToken,
      tenant_id: tenantId
    }));
    
    // Suscribirse a actualizaciones específicas
    ws.send(JSON.stringify({
      action: "subscribe",
      topics: [`execution:${executionId}`, `workflow:${workflowId}`]
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
      case "workflow_execution_update":
        if (callbacks.onUpdate) {
          callbacks.onUpdate(data);
        }
        break;
        
      case "workflow_step_completed":
        if (callbacks.onStepCompleted) {
          callbacks.onStepCompleted(data);
        }
        break;
        
      case "workflow_execution_error":
        if (callbacks.onError) {
          callbacks.onError(data);
        }
        break;
        
      case "workflow_execution_completed":
        if (callbacks.onCompleted) {
          callbacks.onCompleted(data);
        }
        break;
    }
  };
  
  // Manejo de reconexión con backoff exponencial
  ws.onclose = (event) => {
    if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
      reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      
      console.log(`Intentando reconectar en ${delay/1000} segundos...`);
      setTimeout(() => {
        monitorWorkflowExecution(executionId, workflowId, authToken, tenantId, callbacks);
      }, delay);
    } else if (reconnectAttempts >= maxReconnectAttempts) {
      console.error('Máximo número de intentos de reconexión alcanzado');
      if (callbacks.onConnectionError) {
        callbacks.onConnectionError();
      }
    }
  };
  
  // Ping periódico para mantener conexión activa
  const pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: "ping",
        timestamp: new Date().toISOString()
      }));
    }
  }, 30000);
  
  return {
    socket: ws,
    close: () => {
      clearInterval(pingInterval);
      ws.close(1000);
    }
  };
};

// Ejemplo de uso
const monitor = monitorWorkflowExecution(
  "execution-uuid",
  "workflow-uuid",
  authToken,
  tenantId,
  {
    onUpdate: (data) => {
      console.log(`Progreso: ${data.progress * 100}% - Paso actual: ${data.current_step}`);
      updateProgressBar(data.progress);
    },
    onStepCompleted: (data) => {
      console.log(`Paso completado: ${data.step_name}`);
      updateWorkflowDiagram(data.step_id, 'completed');
    },
    onError: (data) => {
      console.error(`Error en paso ${data.error.step_name}: ${data.error.message}`);
      showErrorNotification(data.error.message);
    },
    onCompleted: (data) => {
      console.log(`Workflow completado con estado: ${data.status}`);
      showCompletionMessage(data.status, data.output);
      monitor.close();
    },
    onConnectionError: () => {
      showErrorNotification("Error de conexión con el servidor de workflows");
    }
  }
);
```

## Editor Visual de Workflows (Componentes Frontend)

Para facilitar la integración con un editor visual de workflows en el frontend, el Workflow Engine Service proporciona endpoints especiales para validar componentes individuales de un workflow:

```
POST /api/workflows/validate-step
```

**Headers requeridos:**
- `Authorization: Bearer {jwt_token}`
- `X-Tenant-ID: {tenant_id}`
- `Content-Type: application/json`

**Cuerpo de solicitud:**
```json
{
  "step": {
    "id": "decision",
    "type": "condition",
    "name": "Check Enrichment Success",
    "config": {
      "conditions": [
        {
          "condition": "$.enrich_data.success == true",
          "next": "output_success"
        }
      ],
      "default": "output_failure"
    }
  },
  "context": {
    "available_steps": ["input", "lookup", "enrich_data", "output_success", "output_failure"],
    "input_schema": {
      // Esquema de entrada del workflow
    }
  }
}
```

**Respuesta exitosa (200):**
```json
{
  "valid": true,
  "warnings": [
    {
      "message": "La expresión podría simplificarse a '$.enrich_data.success'",
      "code": "expression_simplification"
    }
  ]
}
```

## Consideraciones por Tier de Servicio

| Característica | Free Tier | Professional Tier | Enterprise Tier |
|----------------|-----------|-------------------|-----------------|
| Número máximo de workflows | 5 | 50 | Ilimitados |
| Pasos por workflow | Hasta 10 | Hasta 30 | Ilimitados |
| Tipos de pasos | Básicos | Avanzados | Personalizados + Todos |
| Ejecuciones concurrentes | 2 | 10 | Configurable |
| Historia de ejecuciones | 7 días | 30 días | 1 año + |
| Versionado | No | Sí (básico) | Completo |
| Tiempo máx. ejecución | 5 min | 30 min | Configurable |
| Plantillas | Básicas (5) | Todas (20+) | Todas + Personalizadas |
| Logs detallados | No | Sí | Extendidos |
| Monitoreo en tiempo real | Limitado | Completo | Avanzado |

### Limitaciones Específicas

#### Free Tier
- Sólo permite workflows con pasos básicos (input, output, condición y herramientas simples)
- Sin soporte para webhooks o triggers externos
- Máximo 100 ejecuciones por día
- Sin acceso a plantillas avanzadas o personalizadas

#### Professional Tier
- Incluye pasos avanzados (bucles, procesos paralelos, agregación)
- Soporte para webhooks y triggers programados
- Máximo 1,000 ejecuciones por día
- Acceso a todas las plantillas estándar

#### Enterprise Tier
- Soporte para workflows distribuidos
- Integración con sistemas externos mediante adaptadores personalizados
- Ejecuciones ilimitadas
- Workflows con alta disponibilidad y failover

## Buenas Prácticas para el Frontend

1. **Implementar un Editor Visual de Workflows**:
   - Ofrecer una interfaz de "arrastrar y soltar" para definir workflows
   - Validar cada paso en tiempo real usando la API de validación
   - Proporcionar previsualización de la ejecución del workflow

2. **Mostrar Progreso en Tiempo Real**:
   - Crear visualizaciones interactivas del progreso de ejecución
   - Resaltar el paso actual en un diagrama del workflow
   - Proporcionar logs en vivo durante ejecuciones de prueba

3. **Optimizar para Workflows Complejos**:
   - Implementar búsqueda y filtrado en workflows con muchos pasos
   - Ofrecer zoom y navegación en diagramas grandes
   - Permitir agrupación lógica de pasos relacionados

4. **Gestionar Versiones**:
   - Mostrar diferencias entre versiones
   - Implementar sistema de publicación con notas de versión
   - Proporcionar opción de revertir a versiones anteriores
