FROM supabase/postgres:15.1.0.129

# Variables de entorno para la configuración inicial
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_USER=postgres
ENV POSTGRES_DB=postgres

# Copiar scripts de inicialización
COPY ./scripts/init-db.sh /docker-entrypoint-initdb.d/
COPY ./scripts/supabase-schema.sql /docker-entrypoint-initdb.d/

# Asegurar que los scripts tienen permisos de ejecución
RUN chmod +x /docker-entrypoint-initdb.d/init-db.sh

# Configurar healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD pg_isready -U postgres -d postgres || exit 1

# Exponer puerto PostgreSQL
EXPOSE 5432
