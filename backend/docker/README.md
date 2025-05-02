# Imágenes Docker Personalizadas

Este directorio contiene las configuraciones para crear imágenes Docker personalizadas de servicios de infraestructura utilizados en nuestra aplicación.

## Estructura

```
docker/
├── ollama/               # Configuración personalizada para Ollama
│   ├── Dockerfile        # Imagen personalizada de Ollama
│   └── scripts/          # Scripts de inicialización y configuración
│       ├── download_models.sh
│       └── start_ollama.sh
├── redis/                # Configuración personalizada para Redis
│   ├── Dockerfile        # Imagen personalizada de Redis
│   └── redis.conf        # Configuración optimizada de Redis
└── services/             # Dockerfiles de nuestros microservicios
```

## Imágenes Personalizadas

### Ollama

La imagen personalizada de Ollama proporciona las siguientes mejoras:

1. **Reducción de logs de licencia**: Filtra los largos mensajes de licencia que dificultan la depuración
2. **Pre-descarga de modelos**: Los modelos necesarios se descargan durante la construcción de la imagen
3. **Configuración optimizada**: Ajustes específicos para nuestro caso de uso
4. **Healthcheck mejorado**: Verificación de salud más confiable

### Redis

La imagen personalizada de Redis incluye:

1. **Configuración optimizada**: Ajustes de memoria y rendimiento para nuestras necesidades
2. **Persistencia configurada**: Estrategia de persistencia adecuada para nuestro caso de uso
3. **Healthcheck robusto**: Verificación de salud para garantizar disponibilidad

## Uso

Las imágenes se construyen automáticamente al ejecutar `docker-compose up -d` debido a los cambios en el archivo docker-compose.yml que apuntan a estos Dockerfiles personalizados en lugar de usar imágenes públicas directamente.

## Beneficios

Este enfoque proporciona varias ventajas:

1. **Mayor control**: Podemos personalizar aspectos clave de estos servicios
2. **Mejor observabilidad**: Logs más limpios y configuraciones específicas
3. **Reproducibilidad**: Entornos consistentes en desarrollo y producción
4. **Rendimiento optimizado**: Configuraciones ajustadas a nuestras necesidades
5. **Pre-carga de datos**: Modelos y configuraciones preparados durante la construcción

## Mantenimiento

Para actualizar estas imágenes:

1. Modifica los Dockerfiles o archivos de configuración según sea necesario
2. Reconstruye las imágenes: `docker-compose build ollama redis`
3. Reinicia los servicios: `docker-compose up -d ollama redis`
