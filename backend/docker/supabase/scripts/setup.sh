#!/bin/bash
set -e

# Script de configuración para Supabase
echo "Configurando base de datos para el sistema RAG..."

# Esperar a que PostgreSQL esté completamente disponible
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" -h localhost; do
  echo "Esperando a que PostgreSQL esté disponible..."
  sleep 1
done

# Crear el usuario y la base de datos de la aplicación
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Crear usuario de la aplicación
    CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password';
    
    -- Crear base de datos
    CREATE DATABASE nooble3_db;
    
    -- Otorgar permisos
    GRANT ALL PRIVILEGES ON DATABASE nooble3_db TO app_user;
EOSQL

echo "Base de datos y usuario creados correctamente."

# Configurar extensiones y esquemas
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname nooble3_db <<-EOSQL
    -- Activar extensiones necesarias
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pg_trgm";
    CREATE EXTENSION IF NOT EXISTS "vector";
    
    -- Crear esquemas
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE SCHEMA IF NOT EXISTS storage;
    
    -- Otorgar permisos
    GRANT ALL ON SCHEMA public TO app_user;
    GRANT ALL ON SCHEMA auth TO app_user;
    GRANT ALL ON SCHEMA storage TO app_user;
    
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON TABLES TO app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON TABLES TO app_user;
EOSQL

echo "Configuración de Supabase completada."
