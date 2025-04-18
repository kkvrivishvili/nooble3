#!/bin/bash
# Script para verificar el estado de todos los servicios

# Colores para salida
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Verificando estado de los servicios..."

# Función para verificar un servicio
check_service() {
  local service_name="$1"
  local url="$2"
  
  echo -n "Verificando ${service_name}... "
  
  response=$(curl -s -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null)
  
  if [ "$response" = "200" ]; then
    echo -e "${GREEN}OK${NC} (código $response)"
    return 0
  else
    echo -e "${RED}FALLO${NC} (código $response)"
    return 1
  fi
}

# Comprobar Redis
echo -n "Verificando Redis... "
if docker exec -it $(docker ps -qf "name=redis") redis-cli ping | grep -q "PONG"; then
  echo -e "${GREEN}OK${NC}"
else
  echo -e "${RED}FALLO${NC}"
fi

# Comprobar Ollama
echo -n "Verificando Ollama... "
if curl -s