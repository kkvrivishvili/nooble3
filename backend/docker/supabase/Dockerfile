FROM supabase/postgres:15.1.0.129

# Variables de entorno para la configuración inicial
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_USER=postgres
ENV POSTGRES_DB=postgres

# Copiar scripts de inicialización en el orden correcto
COPY ./scripts/setup.sh /docker-entrypoint-initdb.d/10-setup.sh
COPY ./scripts/supabase-schema.sql /docker-entrypoint-initdb.d/20-schema.sql

# Asegurar que los scripts tienen permisos de ejecución
RUN chmod +x /docker-entrypoint-initdb.d/10-setup.sh

# Configurar healthcheck
HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=10 \
  CMD pg_isready -U postgres -d postgres || exit 1

# Exponer puerto PostgreSQL
EXPOSE 5432
