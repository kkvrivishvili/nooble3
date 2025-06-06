# Estándares de Estructura de Base de Datos

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Convenciones de Nombrado](#2-convenciones-de-nombrado)
3. [Estructura de Tablas](#3-estructura-de-tablas)
4. [Tipos de Datos](#4-tipos-de-datos)
5. [Relaciones](#5-relaciones)
6. [Índices](#6-índices)
7. [Estados y Enumeraciones](#7-estados-y-enumeraciones)
8. [Manejo Multi-tenant](#8-manejo-multi-tenant)
9. [Referencias entre Servicios](#9-referencias-entre-servicios)
10. [Diccionario de Datos](#10-diccionario-de-datos)

## 1. Introducción

Este documento establece los estándares y mejores prácticas para la estructura de bases de datos en la plataforma Nooble AI. Estos estándares deben aplicarse a todos los servicios para mantener la consistencia, facilitar el mantenimiento y garantizar la integridad de los datos.

## 2. Convenciones de Nombrado

### 2.1 Esquemas

- Los nombres de esquemas deben ser en formato `snake_case`
- Deben ser nombres completos y descriptivos, no abreviaciones
- Ejemplos:
  - ✅ `agent_execution`
  - ✅ `workflow_engine`
  - ❌ `agent_mgmt` (abreviación)
  - ❌ `orchestrator` (demasiado genérico)

### 2.2 Tablas

- Los nombres de tablas deben ser en formato `snake_case`
- Deben estar en plural para representar colecciones
- El esquema debe ser incluido al referenciar tablas en SQL: `esquema.tabla`
- Ejemplos:
  - ✅ `agent_execution.executions`
  - ✅ `workflow_engine.workflow_definitions`
  - ❌ `AgentMgmt.agent` (formato incorrecto, singular)

### 2.3 Columnas

- Los nombres de columnas deben ser en formato `snake_case`
- Deben ser descriptivos y auto-explicativos
- Los identificadores primarios deben ser nombrados `id`
- Las claves foráneas deben seguir el formato `entidad_id`
- Ejemplos:
  - ✅ `created_at`, `user_id`, `document_count`
  - ❌ `CreatedAt`, `userid`, `doc_cnt` (formato inconsistente o abreviaciones)

## 3. Estructura de Tablas

### 3.1 Campos Estándar

Todas las tablas deben incluir los siguientes campos estándar:

```sql
id UUID PRIMARY KEY,
tenant_id UUID NOT NULL,
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE,
```

### 3.2 Campos Comunes Adicionales

Para tablas que registran autoría:
```sql
created_by UUID,
updated_by UUID,
```

Para tablas con estado:
```sql
status VARCHAR(50) NOT NULL,
```

Para tablas que representan versiones:
```sql
version INTEGER NOT NULL,
```

### 3.3 Orden de Campos

Los campos deben seguir este orden estándar:
1. Identificadores primarios
2. Identificadores foráneos e identificadores de negocio
3. Campos de datos principales
4. Campos de metadatos
5. Campos de timestamps y auditoría

## 4. Tipos de Datos

### 4.1 Identificadores

- Todos los identificadores primarios y foráneos deben ser `UUID`
- Ejemplos:
  - ✅ `id UUID PRIMARY KEY`
  - ❌ `id SERIAL PRIMARY KEY`
  - ❌ `id VARCHAR(36) PRIMARY KEY`

### 4.2 Cadenas de Texto

- Para nombres cortos: `VARCHAR(100)`
- Para nombres largos o títulos: `VARCHAR(255)`
- Para contenido o descripciones: `TEXT`
- Para códigos o estados: `VARCHAR(50)`

### 4.3 Fechas y Tiempos

- Usar `TIMESTAMP WITH TIME ZONE` para todas las fechas y tiempos
- Ejemplos:
  - ✅ `created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()`
  - ❌ `created_at TIMESTAMP` (sin zona horaria)

### 4.4 Datos Estructurados

- Usar `JSONB` para datos estructurados
- Ejemplos:
  - ✅ `configuration JSONB`
  - ❌ `configuration TEXT` (no estructurado)

## 5. Relaciones

### 5.1 Claves Foráneas

- Cada clave foránea debe especificar el comportamiento `ON DELETE`
- Opciones recomendadas:
  - `ON DELETE CASCADE` para tablas asociadas que no tienen sentido sin el padre
  - `ON DELETE RESTRICT` para proteger relaciones críticas
  - Ejemplo:
    ```sql
    FOREIGN KEY (agent_id) REFERENCES agent_management.agents (id) ON DELETE CASCADE
    ```

### 5.2 Referencias entre Servicios

- Las referencias entre servicios deben documentarse explícitamente
- Si es posible, utilizar tablas de mapeo para relaciones complejas
- Ejemplo de documentación:
  ```sql
  -- Reference: This tool_id references tool_registry.tools.id (cross-service reference)
  tool_id UUID NOT NULL
  ```

## 6. Índices

### 6.1 Convenciones de Nombrado

- Los nombres de índices deben seguir el formato: `idx_tabla_columna(s)`
- Para índices compuestos, incluir todas las columnas en el nombre
- Ejemplos:
  - ✅ `idx_agents_tenant_id`
  - ✅ `idx_documents_tenant_id_status`
  - ❌ `agents_idx_1` (no descriptivo)

### 6.2 Índices Estándar

- Todas las tablas deben tener índices para:
  - Clave primaria (automático)
  - Clave foránea
  - Campo `tenant_id`
  - Campo `status` (si existe)
  - Campos utilizados frecuentemente en filtros o joins

## 7. Estados y Enumeraciones

### 7.1 Estados Comunes

Para campos de estado de entidad:
- `active`: Entidad activa y disponible
- `inactive`: Entidad desactivada temporalmente
- `deleted`: Entidad marcada como eliminada (soft delete)

Para campos de estado de ejecución:
- `pending`: Esperando ejecución
- `running`: En ejecución actualmente
- `completed`: Ejecución completada exitosamente
- `failed`: Ejecución finalizada con errores
- `canceled`: Ejecución cancelada

## 8. Manejo Multi-tenant

- Todas las tablas deben incluir `tenant_id` como campo obligatorio
- Todas las consultas deben filtrar por `tenant_id` para asegurar aislamiento de datos
- Todos los índices deben considerar `tenant_id` como primer campo para consultas comunes

## 9. Referencias entre Servicios

### 9.1 Definición de Referencias

Cuando una tabla hace referencia a datos en otro servicio:

1. Documentar claramente la referencia
2. Considerar si se requiere una tabla de mapeo
3. Establecer estrategia de manejo de integridad a nivel de aplicación

### 9.2 Tabla de Referencias entre Servicios

| Servicio Origen | Tabla Origen | Campo | Servicio Destino | Tabla Destino | Campo |
|----------------|--------------|-------|-----------------|---------------|-------|
| agent_management | agent_tools | tool_id | tool_registry | tools | id |
| agent_execution | executions | agent_id | agent_management | agents | id |
| conversation | conversations | session_id | agent_orchestrator | sessions | id |

## 10. Diccionario de Datos

### 10.1 Campos Comunes y sus Tipos

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| id | UUID | Identificador único | 123e4567-e89b-12d3-a456-426614174000 |
| tenant_id | UUID | Identificador del tenant | 123e4567-e89b-12d3-a456-426614174000 |
| created_at | TIMESTAMP WITH TIME ZONE | Fecha de creación | 2023-01-15 14:30:00+00 |
| updated_at | TIMESTAMP WITH TIME ZONE | Fecha de actualización | 2023-01-15 14:30:00+00 |
| status | VARCHAR(50) | Estado del registro | active |
| created_by | UUID | Usuario que creó el registro | 123e4567-e89b-12d3-a456-426614174000 |
| updated_by | UUID | Usuario que actualizó el registro | 123e4567-e89b-12d3-a456-426614174000 |
| name | VARCHAR(255) | Nombre descriptivo | "Agente asistente principal" |
| description | TEXT | Descripción detallada | "Este agente se encarga de..." |
| configuration | JSONB | Configuración en formato JSON | {"key": "value"} |

### 10.2 Tablas Comunes por Servicio

Cada servicio debe implementar estas tablas siguiendo los patrones establecidos:

- **Entidades Principales**: Almacenan la definición base de cada entidad de negocio
- **Historial/Versiones**: Almacenan versiones históricas de entidades versionadas
- **Relaciones**: Mapean relaciones entre entidades
- **Ejecuciones**: Registran eventos de ejecución y su estado

---

Este documento será actualizado periódicamente para reflejar nuevas decisiones de arquitectura y mejores prácticas identificadas durante el desarrollo.
