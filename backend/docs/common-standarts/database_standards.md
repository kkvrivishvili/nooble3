# Estándares de Acceso y Gestión de Base de Datos

*Versión: 1.0.0*  
*Última actualización: 2025-06-03*  
*Responsable: Equipo Nooble Backend*

## Índice
1. [Introducción](#1-introducción)
2. [Arquitectura de Bases de Datos](#2-arquitectura-de-bases-de-datos)
3. [Módulo Común DB](#3-módulo-común-db)
4. [Convenciones de Nombrado](#4-convenciones-de-nombrado)
5. [Acceso Multi-tenant](#5-acceso-multi-tenant)
6. [Operaciones Asíncronas](#6-operaciones-asíncronas)
7. [Transacciones y Consistencia](#7-transacciones-y-consistencia)
8. [Migraciones](#8-migraciones)
9. [Implementación en Servicios](#9-implementación-en-servicios)

## 1. Introducción

Este documento establece los estándares para el acceso y gestión de bases de datos en todos los microservicios de la plataforma Nooble AI. El objetivo es garantizar un acceso uniforme, seguro y eficiente a los datos, así como mantener la integridad y aislamiento multi-tenant en toda la plataforma.

### 1.1 Principios Generales

- **Consistencia**: Patrones de acceso uniformes en todos los servicios
- **Aislamiento**: Estricta separación de datos entre tenants
- **Eficiencia**: Optimización de consultas y conexiones
- **Seguridad**: Prevención de inyección SQL y acceso no autorizado
- **Trazabilidad**: Registro de operaciones críticas en la base de datos

## 2. Arquitectura de Bases de Datos

### 2.1 Bases de Datos Primarias

| Base de Datos | Propósito | Servicios Usuarios |
|---------------|-----------|-------------------|
| PostgreSQL | Datos relacionales y estado del sistema | Todos los servicios |
| Supabase | Almacenamiento vectorial para RAG | Query Service, Embedding Service |
| Redis | Caché, colas y estado distribuido | Todos los servicios |

### 2.2 Separación de Responsabilidades

Cada servicio debe:
- Gestionar únicamente sus propias tablas y esquemas
- Definir interfaces claras para el acceso a sus datos
- Evitar acceder directamente a tablas de otros servicios

## 3. Módulo Común DB

El módulo `backend/common/db` proporciona abstracciones estándar:

### 3.1 Componentes Principales

```
common/db/
├── __init__.py       # Exporta clases principales
├── storage.py        # Abstracciones para almacenamiento
├── supabase.py       # Cliente Supabase para vectores
├── tables.py         # Definiciones de tablas compartidas
└── rpc.py            # Funciones RPC para comunicación DB
```

### 3.2 Clases y Abstracciones Principales

- **DbClient**: Cliente base para acceso a PostgreSQL
- **SupabaseVectorClient**: Cliente para operaciones vectoriales
- **BaseModel**: Modelo base para todos los modelos de datos
- **TenantModel**: Modelo base para entidades multi-tenant

## 4. Convenciones de Nombrado

### 4.1 Tablas y Esquemas

| Elemento | Convención | Ejemplos |
|----------|------------|----------|
| Esquemas | snake_case, por servicio | `agent_mgmt`, `workflow_engine` |
| Tablas | snake_case, plural | `agents`, `workflow_definitions` |
| Columnas | snake_case | `created_at`, `user_id` |
| Índices | `idx_{tabla}_{columnas}` | `idx_agents_tenant_id`, `idx_tasks_status` |
| Restricciones | `{tipo}_{tabla}_{columnas}` | `pk_agents_id`, `fk_tasks_agent_id` |

### 4.2 Campos Estándar

Todas las tablas principales deben incluir:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | uuid | Identificador único primario |
| tenant_id | uuid | ID del tenant (obligatorio) |
| created_at | timestamp | Momento de creación |
| updated_at | timestamp | Última actualización |
| created_by | uuid | Usuario creador |
| status | varchar/enum | Estado del recurso |

## 5. Acceso Multi-tenant

### 5.1 Filtrado Automático por Tenant

Todas las consultas deben incluir filtrado por tenant:

```python
async def get_agents(tenant_id: str):
    """Obtiene todos los agentes de un tenant."""
    query = """
        SELECT * FROM agent_mgmt.agents
        WHERE tenant_id = $1 AND status != 'deleted'
    """
    return await db.fetch_all(query, tenant_id)
```

### 5.2 Middleware de Aislamiento

Se debe implementar middleware que:
- Verifique el tenant_id en cada solicitud
- Lo añada al contexto de la solicitud
- Valide permisos de acceso al tenant

```python
async def tenant_middleware(request: Request, call_next):
    tenant_id = extract_tenant_id(request)
    if not tenant_id:
        raise MissingTenantError("Se requiere tenant_id")
    
    request.state.tenant_id = tenant_id
    response = await call_next(request)
    return response
```

## 6. Operaciones Asíncronas

### 6.1 Clientes Asíncronos

Todos los accesos a bases de datos deben ser asíncronos:

```python
async def create_agent(tenant_id: str, agent_data: dict):
    """Crea un nuevo agente de forma asíncrona."""
    query = """
        INSERT INTO agent_mgmt.agents (id, tenant_id, name, description, status)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """
    agent_id = str(uuid.uuid4())
    await db.execute(
        query,
        agent_id,
        tenant_id,
        agent_data["name"],
        agent_data.get("description", ""),
        "active"
    )
    return agent_id
```

### 6.2 Grupos de Conexiones

Cada servicio debe configurar grupos de conexiones apropiados:

```python
# Configuración de pool de conexiones
db_pool = create_pool(
    host=config.DB_HOST,
    port=config.DB_PORT,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME,
    min_size=config.DB_POOL_MIN_SIZE,
    max_size=config.DB_POOL_MAX_SIZE
)
```

## 7. Transacciones y Consistencia

### 7.1 Manejo de Transacciones

Usar transacciones para operaciones multi-paso:

```python
async def update_agent_and_metadata(agent_id: str, tenant_id: str, data: dict):
    """Actualiza un agente y sus metadatos en una transacción."""
    async with db.transaction():
        # Actualizar datos del agente
        await update_agent(agent_id, tenant_id, data["agent"])
        
        # Actualizar metadatos
        await update_metadata(agent_id, tenant_id, data["metadata"])
```

### 7.2 Consistencia Eventual

Para operaciones entre servicios:
- Usar mensajes/eventos para propagación de cambios
- Implementar idempotencia para manejar duplicados
- Diseñar para consistencia eventual

## 8. Migraciones

### 8.1 Gestión de Migraciones

Cada servicio debe gestionar sus migraciones:

```
service/
├── migrations/
│   ├── 001_initial_schema.sql
│   ├── 002_add_status_column.sql
│   └── 003_create_indexes.sql
├── migration.py      # Script de ejecución
```

### 8.2 Principios de Migración

- Migraciones incrementales y versionadas
- Compatibilidad hacia atrás cuando sea posible
- Scripts idempotentes (verificar antes de actuar)
- Scripts de rollback para cambios críticos

## 9. Implementación en Servicios

### 9.1 Inicialización

Cada servicio debe inicializar su cliente DB al arranque:

```python
# En service/startup.py
from common.db import DbClient, setup_db_pool

async def startup_db():
    """Inicializa la conexión a la base de datos."""
    pool = await setup_db_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )
    
    service.db = DbClient(pool)
    logger.info("Conexión a base de datos inicializada")
```

### 9.2 Acceso en Repositorios

Estructurar acceso a datos en repositorios:

```python
# En service/repositories/agents.py
class AgentRepository:
    def __init__(self, db_client):
        self.db = db_client
    
    async def find_by_id(self, agent_id: str, tenant_id: str):
        """Encuentra un agente por ID y tenant."""
        query = """
            SELECT * FROM agent_mgmt.agents 
            WHERE id = $1 AND tenant_id = $2
        """
        return await self.db.fetch_one(query, agent_id, tenant_id)
```

### 9.3 Registro de Operaciones

Las operaciones críticas deben registrarse:

```python
async def delete_agent(agent_id: str, tenant_id: str, user_id: str):
    """Elimina un agente (marcado lógico)."""
    query = """
        UPDATE agent_mgmt.agents
        SET status = 'deleted', updated_at = NOW(), updated_by = $3
        WHERE id = $1 AND tenant_id = $2
    """
    result = await db.execute(query, agent_id, tenant_id, user_id)
    
    # Registrar la operación
    await log_operation(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_type="agent",
        resource_id=agent_id,
        operation="delete"
    )
    
    return result.rowcount > 0
```
