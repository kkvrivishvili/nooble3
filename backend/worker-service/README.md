# Worker Service

Servicio para la gestión de tareas programadas y procesos en segundo plano, incluyendo la reconciliación de tokens, consolidación de contadores y auditorías periódicas.

## Funcionalidades

- Reconciliación diaria de tokens pendientes
- Consolidación semanal de contadores entre Redis y base de datos
- Auditoría mensual de contadores
- API para gestión y monitorización de tareas

## Arquitectura

El servicio utiliza [APScheduler](https://apscheduler.readthedocs.io/) para la ejecución de tareas programadas, junto con FastAPI para exponer endpoints de gestión y monitorización.

### Componentes Principales

- **Scheduler**: Sistema centralizado para programar y ejecutar tareas
- **Reconciliación**: Procesamiento de tokens pendientes y sincronización
- **Monitoring**: Endpoints para supervisar la salud y estado del sistema

## Configuración

El servicio utiliza la configuración centralizada desde el módulo `common/config`. Las principales variables de entorno son:

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `RECONCILIATION_SCHEDULE_DAILY` | Cron para reconciliación diaria | `0 2 * * *` |
| `RECONCILIATION_SCHEDULE_WEEKLY` | Cron para consolidación semanal | `0 3 * * 0` |
| `RECONCILIATION_SCHEDULE_MONTHLY` | Cron para auditoría mensual | `0 4 1 * *` |
| `RECONCILIATION_ALERT_THRESHOLD` | Umbral para alertas | `1000` |
| `ENABLE_USAGE_TRACKING` | Habilitar tracking | `True` |

## Uso

### Configuración del Entorno

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
export REDIS_URL=redis://localhost:6379/0
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-supabase-key
```

### Ejecución

```bash
# Desarrollo
uvicorn main:app --reload

# Producción
uvicorn main:app --host 0.0.0.0 --port 8080
```

## API Endpoints

- `GET /health`: Verificación de salud del servicio
- `GET /status`: Estado actual del scheduler y tareas programadas

## Integración con Otros Servicios

El worker-service se integra con los siguientes componentes:

- **Redis**: Para acceso a contadores y conjuntos de datos pendientes
- **Supabase**: Para persistencia y sincronización de datos
- **Sistema de Alertas**: Para notificar sobre problemas en el proceso de reconciliación
