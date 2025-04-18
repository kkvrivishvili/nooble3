#!/bin/bash
# Script para inicializar y esperar a que Ollama esté listo

set -e

# Función para comprobar si Ollama está listo
check_ollama() {
  curl --silent --fail http://${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}/api/tags > /dev/null
  return $?
}

# Solo intentar inicializar Ollama si está configurado
if [ "${USE_OLLAMA}" = "true" ]; then
  echo "Esperando a que Ollama esté disponible en ${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}..."
  
  # Esperamos hasta 120 segundos
  max_attempts=60
  counter=0
  
  # Verificar si Ollama está disponible
  until check_ollama || [ $counter -eq $max_attempts ]; do
    echo "Esperando a que Ollama esté disponible... ($counter/$max_attempts)"
    sleep 2
    counter=$((counter+1))
  done
  
  if [ $counter -eq $max_attempts ]; then
    echo "¡Advertencia! Ollama no está disponible después de esperar. El servicio continuará, pero las funcionalidades que dependen de Ollama podrían fallar."
  else
    echo "Ollama está disponible."
    
    # Si está configurado para descargar modelos
    if [ "${OLLAMA_PULL_MODELS}" = "true" ]; then
      echo "Verificando modelos de Ollama..."
      
      # Obtener modelos configurados
      EMBEDDING_MODEL=${DEFAULT_OLLAMA_EMBEDDING_MODEL:-"nomic-embed-text"}
      LLM_MODEL=${DEFAULT_OLLAMA_LLM_MODEL:-"llama3:1b"}
      
      # Verificar y descargar modelos si es necesario
      echo "Verificando modelo de embeddings: $EMBEDDING_MODEL"
      curl -s -X POST \
        -H "Content-Type: application/json" \
        --data "{\"name\":\"$EMBEDDING_MODEL\"}" \
        http://${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}/api/show || {
        echo "Descargando modelo de embeddings: $EMBEDDING_MODEL"
        curl -s http://${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}/api/pull -d "{\"name\":\"$EMBEDDING_MODEL\"}"
      }
      
      echo "Verificando modelo LLM: $LLM_MODEL"
      curl -s -X POST \
        -H "Content-Type: application/json" \
        --data "{\"name\":\"$LLM_MODEL\"}" \
        http://${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}/api/show || {
        echo "Descargando modelo LLM: $LLM_MODEL"
        curl -s http://${OLLAMA_HOST:-ollama}:${OLLAMA_PORT:-11434}/api/pull -d "{\"name\":\"$LLM_MODEL\"}"
      }
    fi
  fi
else
  echo "Ollama no está habilitado (USE_OLLAMA=false). Omitiendo inicialización."
fi

# Continuar con el comando original
echo "Iniciando servicio principal..."
exec "$@"