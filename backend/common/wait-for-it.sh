#!/bin/bash
# wait-for-it.sh: Script para esperar que un host/puerto esté disponible
# Se usa para esperar a que los servicios dependientes estén listos

set -e

host="$1"
port="$2"
shift 2
cmd="$@"

echo "Esperando a que $host:$port esté disponible..."

until nc -z -w5 "$host" "$port"; do
  >&2 echo "El servicio en $host:$port no está disponible aún - esperando..."
  sleep 2
done

echo "$host:$port está disponible, continuando..."

# Ejecutar el comando proporcionado
exec $cmd