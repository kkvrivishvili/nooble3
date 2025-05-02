#!/bin/bash
#!/bin/bash

# Script personalizado para iniciar Ollama e instalar modelos necesarios

# Establecer variables de entorno para reducir verbosidad si no están ya definidas
export OLLAMA_LOG_LEVEL=${OLLAMA_LOG_LEVEL:-warn}
export OLLAMA_VERBOSE=${OLLAMA_VERBOSE:-false}

echo "Iniciando Ollama con nivel de log: $OLLAMA_LOG_LEVEL"

# Iniciar Ollama en segundo plano
ollama serve &
SERVE_PID=$!

# Esperar a que Ollama esté disponible
echo "Esperando a que el servicio Ollama esté listo..."
until curl -s -o /dev/null -w '' http://localhost:11434/api/health; do
    echo "Esperando a Ollama..."
    sleep 2
done

echo "Servicio Ollama iniciado correctamente."

# Descargar modelos necesarios
echo "Descargando modelos necesarios..."
/app/download_models.sh

echo "Configuración completada, manteniendo el servicio Ollama activo"

# Traer Ollama al primer plano
wait $SERVE_PID
