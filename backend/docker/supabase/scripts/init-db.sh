#!/bin/bash
set -e

# Este script inicializa la base de datos de Supabase con la configuración necesaria
# para el entorno de desarrollo local

echo "Iniciando configuración de base de datos Supabase..."

# Asegurarse que Postgres esté completamente disponible
pg_isready -U postgres -h localhost

# Crear la base de datos
echo "Creando base de datos nooble3_db..."
psql -U postgres -c "DROP DATABASE IF EXISTS nooble3_db WITH (FORCE);"
sleep 1
psql -U postgres -c "CREATE DATABASE nooble3_db;"

# Crear el usuario de la aplicación
echo "Creando usuario app_user..."
psql -U postgres -c "DROP ROLE IF EXISTS app_user;"
psql -U postgres -c "CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password';"

# Otorgar permisos al usuario en la base de datos
echo "Otorgando permisos al usuario app_user sobre la base de datos nooble3_db..."
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE nooble3_db TO app_user;"

# Conectar a la base de datos y crear los esquemas
echo "Creando esquemas en nooble3_db..."
psql -U postgres -d nooble3_db -c "CREATE SCHEMA IF NOT EXISTS public;"
psql -U postgres -d nooble3_db -c "CREATE SCHEMA IF NOT EXISTS auth;"
psql -U postgres -d nooble3_db -c "CREATE SCHEMA IF NOT EXISTS storage;"

# Otorgar permisos sobre los esquemas
echo "Otorgando permisos sobre los esquemas..."
psql -U postgres -d nooble3_db -c "GRANT ALL ON SCHEMA public TO app_user;"
psql -U postgres -d nooble3_db -c "GRANT ALL ON SCHEMA auth TO app_user;"
psql -U postgres -d nooble3_db -c "GRANT ALL ON SCHEMA storage TO app_user;"
psql -U postgres -d nooble3_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;"
psql -U postgres -d nooble3_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT ALL ON TABLES TO app_user;"
psql -U postgres -d nooble3_db -c "ALTER DEFAULT PRIVILEGES IN SCHEMA storage GRANT ALL ON TABLES TO app_user;"

# Ejecutar el archivo SQL con el esquema principal
echo "Aplicando esquema principal de la base de datos..."
psql -U postgres -d nooble3_db -f /scripts/supabase-schema.sql

echo "Configuración de la base de datos completada."
