#!/bin/bash

# Script para configuración inicial de Ollama
# Este script no se usará como CMD/ENTRYPOINT
# Sirve como referencia de los comandos necesarios para inicializar Ollama

# IMPORTANTE: Este script no debería sobrescribir el comportamiento de la imagen
# base de Ollama, ya que ya tiene su propio ENTRYPOINT/CMD que ejecutará 'ollama serve'

# Para descargar modelos, usar estos comandos:
# ollama pull nomic-embed-text
# ollama pull qwen3:1.7b

# Este archivo se mantiene como referencia pero no se usará directamente
# La descarga de modelos la haremos a través del servicio 'ollama-init'
