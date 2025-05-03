#!/bin/bash
set -e

# Script de inicialización personalizado para Supabase
echo "Iniciando servicio Supabase con entrypoint personalizado..."

# Ejecutar el entrypoint original de Postgres para iniciar el servicio
/usr/local/bin/docker-entrypoint.sh postgres "$@" &
PG_PID=$!

# Función para esperar a que PostgreSQL esté listo
wait_for_postgres() {
  echo "Esperando a que PostgreSQL esté completamente listo..."
  
  # Número máximo de intentos y contador
  max_attempts=60
  attempts=0
  
  # Esperar hasta que PostgreSQL esté aceptando conexiones
  until pg_isready -U postgres -d postgres -h 127.0.0.1 -p 5432 > /dev/null 2>&1; do
    attempts=$((attempts+1))
    if [ $attempts -ge $max_attempts ]; then
      echo "Error: PostgreSQL no está disponible después de $max_attempts intentos. Abortando."
      exit 1
    fi
    echo "Intento $attempts de $max_attempts - PostgreSQL aún no está listo. Esperando..."
    sleep 1
  done
  
  echo "PostgreSQL está listo y aceptando conexiones."
}

# Esperar a que PostgreSQL esté completamente listo antes de intentar inicializar
wait_for_postgres

# Verificar si la base de datos nooble3_db ya existe
echo "Verificando si la base de datos ya está inicializada..."
DB_EXISTS=$(psql -U postgres -t -c "SELECT 1 FROM pg_database WHERE datname='nooble3_db'" | tr -d ' ')

if [ "$DB_EXISTS" != "1" ]; then
  echo "La base de datos nooble3_db no existe. Ejecutando script de inicialización..."
  # Ejecutar el script de inicialización
  /scripts/init-db.sh
  echo "Inicialización completada."
else
  echo "Base de datos nooble3_db ya existe. Omitiendo inicialización."
fi

# Esperar a que el proceso de PostgreSQL termine
echo "Servicio PostgreSQL en ejecución. PID: $PG_PID"
wait $PG_PID
