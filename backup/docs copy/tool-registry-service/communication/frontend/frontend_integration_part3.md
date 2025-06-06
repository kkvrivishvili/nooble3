# Integración del Frontend con Tool Registry Service - Parte 3

## Ejemplos de Código

### Listar Herramientas Disponibles (JavaScript)

```javascript
const fetchAvailableTools = async (authToken, tenantId) => {
  try {
    const response = await fetch('https://api.domain.com/api/tools', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId
      }
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error fetching available tools:', error);
    throw error;
  }
};
```

### Registrar Nueva Herramienta (JavaScript)

```javascript
const registerNewTool = async (toolData, authToken, tenantId) => {
  try {
    const response = await fetch('https://api.domain.com/api/tools/register', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(toolData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error registering new tool:', error);
    throw error;
  }
};
```

### Validar Herramienta (JavaScript)

```javascript
const validateTool = async (toolId, validationData, authToken, tenantId) => {
  try {
    const response = await fetch(`https://api.domain.com/api/tools/${toolId}/validate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'X-Tenant-ID': tenantId,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(validationData)
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error.message);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error validating tool:', error);
    throw error;
  }
};
```

### Escuchar Actualizaciones de Herramientas (WebSocket)

```javascript
const listenToToolUpdates = (authToken, tenantId) => {
  const ws = new WebSocket(`wss://api.domain.com/api/tools/ws`);
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  
  ws.onopen = () => {
    reconnectAttempts = 0;
    ws.send(JSON.stringify({
      action: "authenticate",
      token: authToken,
      tenant_id: tenantId
    }));
    
    // Opcionalmente suscribirse a herramientas específicas
    ws.send(JSON.stringify({
      action: "subscribe",
      tool_ids: ["search-tool", "calculator-tool"]
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.event) {
      case "tool_status_updated":
        // Actualizar estado de herramienta en UI
        updateToolStatus(data.tool_id, data.new_status);
        break;
      
      case "tool_validation_completed":
        // Mostrar resultado de validación
        displayValidationResult(data.validation_id, data.tool_id, data.status, data.issues);
        break;
        
      case "tool_execution":
        // Actualizar logs de ejecución (solo admins)
        updateExecutionLogs(data.tool_id, data.execution_id, data.status);
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
        listenToToolUpdates(authToken, tenantId);
      }, delay);
    } else if (reconnectAttempts >= maxReconnectAttempts) {
      console.error('Máximo número de intentos de reconexión alcanzado');
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
```

## Consideraciones por Tier de Servicio

### Matrix de Funcionalidades por Tier

| Funcionalidad | Free Tier | Professional Tier | Enterprise Tier |
|--------------|-----------|-------------------|-----------------|
| Herramientas predefinidas | Básicas (5) | Avanzadas (15) | Todas (25+) |
| Herramientas personalizadas | No | Hasta 5 | Ilimitadas |
| Asignación de herramientas | Manual | Manual + Sugerencias | Automática + Manual |
| Rate limits | Estrictos | Moderados | Configurables |
| Timeout máximo | 5 segundos | 15 segundos | 60 segundos |
| Validación avanzada | No | Sí | Sí + Pruebas complejas |
| Integración con APIs externas | No | Básica | Avanzada + OAuth2 |

### Limitaciones de Acceso por Tier

#### Free Tier

- Solo puede usar herramientas básicas (`search`, `calculator`, etc.)
- Rate limit: 100 llamadas a herramientas por hora
- Timeout máximo: 5 segundos
- Sin acceso a herramientas de terceros

Ejemplo de respuesta para un tenant en Free tier:
```json
{
  "tenant_id": "free-tenant",
  "tier": "free",
  "available_tools": [
    {"tool_id": "search-tool", "name": "Search Tool", "category": "data"},
    {"tool_id": "calculator", "name": "Calculator", "category": "utility"},
    {"tool_id": "datetime", "name": "Date & Time", "category": "utility"},
    {"tool_id": "dictionary", "name": "Dictionary", "category": "data"},
    {"tool_id": "simple-web", "name": "Simple Web Access", "category": "web"}
  ],
  "custom_tools": [],
  "total_tools": 5
}
```

#### Professional Tier

- Acceso a herramientas avanzadas (`advanced-search`, `data-analysis`, etc.)
- Rate limit: 1,000 llamadas a herramientas por hora
- Timeout máximo: 15 segundos
- Posibilidad de crear hasta 5 herramientas personalizadas

#### Enterprise Tier

- Acceso a todas las herramientas disponibles
- Herramientas personalizadas ilimitadas
- Rate limits configurables
- Timeout máximo: 60 segundos
- Integración con sistemas propios mediante OAuth2

## Buenas Prácticas para el Frontend

1. **Verificación Dinámica de Disponibilidad**:
   ```javascript
   // Verificar si una herramienta está disponible antes de mostrarla en la UI
   const isToolAvailable = (toolId, availableTools) => {
     return availableTools.some(tool => tool.tool_id === toolId && tool.status === 'active');
   };
   ```

2. **Caché de Configuración de Herramientas**:
   ```javascript
   // Almacenar configuraciones en caché por un tiempo limitado
   const toolConfigCache = new Map();
   
   const getToolConfig = async (toolId, authToken, tenantId) => {
     const cacheKey = `${toolId}_${tenantId}`;
     
     if (toolConfigCache.has(cacheKey)) {
       const cached = toolConfigCache.get(cacheKey);
       if (Date.now() - cached.timestamp < 5 * 60 * 1000) { // 5 minutos
         return cached.config;
       }
     }
     
     const config = await fetchToolConfig(toolId, authToken, tenantId);
     toolConfigCache.set(cacheKey, {
       config,
       timestamp: Date.now()
     });
     
     return config;
   };
   ```

3. **Formularios Dinámicos para Parámetros de Herramientas**:
   ```javascript
   // Generar formularios basados en el esquema de entrada
   const generateToolForm = (inputSchema) => {
     return Object.entries(inputSchema.properties).map(([key, prop]) => {
       return {
         name: key,
         label: prop.description || key,
         type: getInputType(prop.type),
         required: inputSchema.required.includes(key),
         default: prop.default,
         options: prop.enum
       };
     });
   };
   
   const getInputType = (schemaType) => {
     const typeMap = {
       string: 'text',
       integer: 'number',
       number: 'number',
       boolean: 'checkbox',
       array: 'multi-select',
       object: 'json-editor'
     };
     
     return typeMap[schemaType] || 'text';
   };
   ```

4. **Manejo de Reintentos Inteligente**:
   ```javascript
   const executeToolWithRetry = async (toolId, params, authToken, tenantId, maxRetries = 3) => {
     let attempt = 0;
     
     while (attempt < maxRetries) {
       try {
         return await executeToolCall(toolId, params, authToken, tenantId);
       } catch (error) {
         attempt++;
         if (error.code === 'rate_limited' && attempt < maxRetries) {
           // Esperar con backoff exponencial
           await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempt)));
           continue;
         }
         throw error;
       }
     }
   };
   ```
