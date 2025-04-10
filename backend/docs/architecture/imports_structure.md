# Arquitectura de Importaciones

## Estructura de Dependencias y Buenas Prácticas

Este documento establece las guías para evitar importaciones circulares y mantener una estructura de dependencias clara en el proyecto.

## 1. Jerarquía de Módulos

Hemos establecido la siguiente jerarquía para evitar importaciones circulares:

1. **Módulos de Configuración Base**
   - `common/config/settings.py`
   - `common/config/tiers.py`
   - `common/config/schema.py`

2. **Módulos de Utilidades**
   - `common/errors/`
   - `common/logging/`
   - `common/context/`

3. **Módulos de Infraestructura**
   - `common/db/`
   - `common/cache/`

4. **Módulos de Autenticación y Autorización**
   - `common/auth/`
   - `common/models/`

5. **Servicios de Aplicación**
   - Todos los servicios funcionales (`embedding-service`, `ingestion-service`, etc.)

## 2. Reglas de Importación

Para mantener la jerarquía limpia y evitar ciclos:

1. **Importaciones hacia abajo:** Los módulos de nivel superior pueden importar módulos de nivel inferior en la jerarquía, pero no al revés.

2. **Importaciones dinámicas:** Cuando sea necesario romper esta regla, utilizar importaciones dinámicas dentro de las funciones:

```python
# ❌ Evitar a nivel de módulo
from ..auth.models import validate_model_access  # Puede causar ciclo

# ✅ Mejor dentro de la función
def my_function():
    from ..auth.models import validate_model_access
    # Resto del código
```

3. **Separación de definiciones y uso:** Define estructuras de datos en niveles bajos y la lógica que las utiliza en niveles más altos.

## 3. Pautas Específicas

### 3.1 Módulos de Configuración

Los módulos en `common/config/` representan la base de la aplicación y no deben importar de otros módulos excepto:

- Módulos estándar de Python
- Excepciones definidas en `common/errors/`
- Importaciones dinámicas dentro de funciones cuando sea absolutamente necesario

### 3.2 Módulos de Autenticación

Los módulos en `common/auth/` pueden utilizar los módulos de configuración, pero para evitar ciclos:

- Importar `tiers.py` solo dentro de funciones
- No permitir que `config` importe directamente desde `auth`

### 3.3 Sugerencias para Tests

- Usar mocks para dependencias circulares en los tests
- Definir interfaces claras que permitan el uso de dobles de prueba

## 4. Ejemplos Prácticos

### 4.1 Correcto: Importación Dinámica

```python
# En un archivo que necesita configuración pero puede crear ciclo
def validate_model(model_id: str, tier: str):
    # Importación dinámica para romper el ciclo
    from ..config.tiers import get_available_models
    
    available_models = get_available_models(tier)
    return model_id in available_models
```

### 4.2 Incorrecto: Importación a Nivel de Módulo que Crea Ciclo

```python
# ❌ Evitar este patrón
from ..config.settings import get_settings  # En un módulo del que settings.py importa

def some_function():
    settings = get_settings()
    # ...
```

### 4.3 Correcto: Uso de Inyección de Dependencias

```python
# ✅ Mejor enfoque
def process_data(data, settings=None):
    if settings is None:
        from ..config.settings import get_settings
        settings = get_settings()
    
    # Procesar datos con settings
```

## 5. Resolución de Problemas Comunes

### 5.1 Detección de Importaciones Circulares

Las importaciones circulares suelen presentarse como:
- `ImportError: cannot import name X`
- `AttributeError: module has no attribute Y`

Para resolverlas:
1. Identifica el ciclo
2. Aplica importaciones dinámicas
3. Considera refactorizar la estructura para eliminar la necesidad de importación

### 5.2 Uso de Señales o Eventos

Para casos complejos, considerar un sistema de eventos donde los módulos se comunican a través de un bus de eventos en lugar de importaciones directas.

## 6. Conclusión

Mantener una estructura clara de dependencias no solo evita errores difíciles de diagnosticar, sino que también mejora la mantenibilidad del código al hacer explícitas las relaciones entre módulos.

Recuerda: La configuración está en la base de todo, no debe depender de otros módulos de la aplicación.
