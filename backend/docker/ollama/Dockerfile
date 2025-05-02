FROM ollama/ollama:0.6.7

# Establecer variables de entorno para reducir logs
ENV OLLAMA_LOG_LEVEL=warn
ENV OLLAMA_VERBOSE=false

# Crear directorio para scripts personalizados
WORKDIR /app

# Copiar scripts de inicialización
COPY ./scripts/download_models.sh /app/
COPY ./scripts/start_ollama.sh /app/

# Dar permisos de ejecución a los scripts
RUN chmod +x /app/download_models.sh /app/start_ollama.sh

# No pre-descargamos los modelos durante la construcción
# Los modelos se descargarán al iniciar el contenedor

# Establecer un healthcheck propio
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:11434/api/health || exit 1

# Usar nuestro script de inicio personalizado
CMD ["/app/start_ollama.sh"]
