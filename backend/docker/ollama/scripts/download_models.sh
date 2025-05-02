#!/bin/bash
set -e

# Script para pre-descargar modelos de Ollama durante la construcción de la imagen
# Evita descargas durante el startup y mejora el tiempo de inicialización

echo "Pre-descargando modelos de embeddings..."

# Modelos de embeddings
ollama pull nomic-embed-text

# Modelo de inferencia liviano para servicios que requieren LLM
echo "Pre-descargando modelo de inferencia liviano..."
ollama pull qwen3:1.7b

# Otros modelos que se utilicen en la aplicación pueden agregarse aquí

echo "Todos los modelos descargados correctamente"
