FROM ollama/ollama:0.6.7

# Establecer variables de entorno para reducir logs
ENV OLLAMA_LOG_LEVEL=info
ENV OLLAMA_VERBOSE=false

# Variable para configurar si se deben descargar los modelos automáticamente
ENV OLLAMA_PULL_MODELS=true

# Variable para definir qué modelos descargar
ENV OLLAMA_MODELS="nomic-embed-text qwen3:1.7b"

# Crear directorio para scripts personalizados
WORKDIR /app

# Copiar scripts de inicialización
COPY ./scripts/download_models.sh /app/

# Dar permisos de ejecución a los scripts 
RUN chmod +x /app/download_models.sh

# Script para descargar modelos automáticamente después de iniciar Ollama
RUN echo '#!/bin/sh\n\
# Script de inicio que inicia Ollama y luego descarga modelos automáticamente\n\
# Ejecutamos ollama serve como proceso de fondo\n\
ollama serve &\n\
SERVE_PID=$!\n\
\n\
# Esperamos a que el API esté disponible\n\
echo "Esperando a que el servicio Ollama esté listo..."\n\
max_attempts=30\n\
attempt=0\n\
\n\
while [ $attempt -lt $max_attempts ]; do\n\
    if curl -s -f http://localhost:11434/api/health > /dev/null 2>&1; then\n\
        echo "Servicio Ollama disponible."\n\
        break\n\
    fi\n\
    \n\
    attempt=$((attempt+1))\n\
    echo "Intento $attempt de $max_attempts. Esperando a que Ollama esté disponible..."\n\
    sleep 2\n\
done\n\
\n\
# Si OLLAMA_PULL_MODELS está habilitado, descargamos los modelos\n\
if [ "$OLLAMA_PULL_MODELS" = "true" ]; then\n\
    echo "Descargando modelos configurados: $OLLAMA_MODELS"\n\
    for model in $OLLAMA_MODELS; do\n\
        echo "Descargando modelo: $model"\n\
        ollama pull $model\n\
    done\n\
fi\n\
\n\
# Esperamos a que el proceso principal termine\n\
wait $SERVE_PID\n\
' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

# Establecer un healthcheck propio
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:11434/api/health || exit 1

# Usar nuestro script de entrypoint personalizado
ENTRYPOINT ["/app/entrypoint.sh"]
