FROM redis:7.4.3-alpine

# Copiar configuración personalizada
COPY redis.conf /usr/local/etc/redis/redis.conf

# Establecer directorios de datos con permisos adecuados
RUN mkdir -p /data && \
    chown redis:redis /data

# Configurar healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD redis-cli ping || exit 1

# Usar configuración personalizada en lugar de la predeterminada
CMD [ "redis-server", "/usr/local/etc/redis/redis.conf" ]
