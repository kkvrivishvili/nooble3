#!/bin/bash
set -e

echo "Esperando a que el servicio Ollama esté disponible..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s -f http://ollama:11434/api/health > /dev/null; then
        echo "Servicio Ollama disponible."
        break
    fi
    
    attempt=$((attempt+1))
    echo "Intento $attempt de $max_attempts. Esperando a que Ollama esté disponible..."
    sleep 5
done

if [ $attempt -eq $max_attempts ]; then
    echo "Error: No se pudo conectar con Ollama después de $max_attempts intentos."
    exit 1
fi

echo "Descargando modelos necesarios para la aplicación..."

# Descargar modelo de embeddings
echo "Descargando modelo de embeddings: nomic-embed-text"
curl -X POST http://ollama:11434/api/pull -d '{"name": "nomic-embed-text"}'

# Descargar modelo LLM
echo "Descargando modelo LLM: qwen3:1.7b"
curl -X POST http://ollama:11434/api/pull -d '{"name": "qwen3:1.7b"}'

echo "Configuración de modelos completada."
