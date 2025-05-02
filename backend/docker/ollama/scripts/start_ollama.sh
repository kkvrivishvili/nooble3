#!/bin/bash
set -e

# Script personalizado para iniciar Ollama con configuraciones optimizadas
# y evitar mensajes de licencia largos en los logs

# Establecer variables de entorno para reducir verbosidad si no están ya definidas
export OLLAMA_LOG_LEVEL=${OLLAMA_LOG_LEVEL:-warn}
export OLLAMA_VERBOSE=${OLLAMA_VERBOSE:-false}

echo "Iniciando Ollama con nivel de log: $OLLAMA_LOG_LEVEL"

# Verificar modelos pre-descargados
echo "Verificando modelos disponibles..."
ollama list 2>/dev/null | grep -v "license" | grep -v "terms" || echo "No hay modelos listados"

# Iniciar Ollama con salida filtrada para evitar licencias extensas
exec ollama serve "$@" 2>&1 | grep -v -i "license" | grep -v -i "terms and conditions"
