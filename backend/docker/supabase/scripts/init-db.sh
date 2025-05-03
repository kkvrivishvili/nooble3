#!/bin/bash
set -e

# Este script inicializa la base de datos de Supabase con la configuración necesaria
# para el entorno de desarrollo local

echo "Iniciando configuración de base de datos Supabase..."

# Esperar a que Postgres esté completamente disponible
until pg_isready -U postgres -d postgres; do
  echo "Esperando que PostgreSQL esté disponible..."
  sleep 1
done

# Crear la base de datos y el usuario para la aplicación si no existen
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Crear usuario de aplicación si no existe
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
            CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password';
        END IF;
    END
    \$\$;

    -- Crear base de datos de la aplicación si no existe
    SELECT 'CREATE DATABASE nooble3_db'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nooble3_db');

    -- Otorgar permisos al usuario de la aplicación
    GRANT ALL PRIVILEGES ON DATABASE nooble3_db TO app_user;
EOSQL

# Cambiar a la base de datos de la aplicación para crear esquema
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "nooble3_db" <<-EOSQL
    -- Crear esquema de la aplicación
    CREATE SCHEMA IF NOT EXISTS public;
    CREATE SCHEMA IF NOT EXISTS auth;
    CREATE SCHEMA IF NOT EXISTS storage;

    -- Asignar permisos al usuario de la aplicación
    GRANT ALL ON SCHEMA public TO app_user;
    GRANT ALL ON SCHEMA auth TO app_user;
    GRANT ALL ON SCHEMA storage TO app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON TABLES TO app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON TABLES TO app_user;
EOSQL

# Ejecutar el archivo SQL con el esquema principal
echo "Aplicando esquema principal de la base de datos..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "nooble3_db" -f /docker-entrypoint-initdb.d/supabase-schema.sql

echo "Configuración de la base de datos completada."
