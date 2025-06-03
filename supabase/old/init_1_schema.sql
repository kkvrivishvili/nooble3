-- =============================================
-- INIT_1_SCHEMA.SQL - DEFINICIONES DE ESQUEMA Y TABLAS PRINCIPALES
-- =============================================
-- Este archivo establece el esquema base y las tablas principales del sistema multi-tenant.
-- Incluye la creación de esquemas, extensiones necesarias, y tablas fundamentales.
-- Fecha: 2025-05-08

-- ===========================================
-- PARTE 1: EXTENSIONES Y ESQUEMAS
-- ===========================================

-- Asegurar que las extensiones necesarias estén disponibles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Intentar agregar extensión pgvector para manejo de vectores (embeddings)
-- NOTA: Si esta extensión no está disponible, es necesario instalarla en el sistema
-- antes de ejecutar la parte de agentes y colecciones. Ver instrucciones de instalación.
DO $
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS "pgvector";
        RAISE NOTICE 'Extensión pgvector instalada correctamente';
    EXCEPTION
        WHEN OTHERS THEN
            RAISE WARNING 'No se pudo instalar la extensión pgvector. Error: %', SQLERRM;
            RAISE WARNING 'La extensión pgvector es necesaria para la funcionalidad de embeddings vectoriales.';
            RAISE WARNING 'Instale pgvector en el sistema antes de continuar con los scripts que requieran esta funcionalidad.';
    END;
END
$;

-- Crear esquemas si no existen
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS vectors;

-- ===========================================
-- PARTE 2: TIPOS ENUMERADOS
-- ===========================================

-- Crear tipos enumerados para estandarizar valores
DO $$
BEGIN
    -- Verificar si el tipo token_type ya existe
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'token_type') THEN
        CREATE TYPE ai.token_type AS ENUM ('llm', 'embedding', 'fine_tuning');
    END IF;
    
    -- Verificar si el tipo operation_type ya existe
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'operation_type') THEN
        CREATE TYPE ai.operation_type AS ENUM (
            'query', 'chat', 'summarize', 'vector_search', 
            'generation', 'classification', 'extraction'
        );
    END IF;
END
$$;

-- ===========================================
-- PARTE 3: TABLAS PRINCIPALES
-- ===========================================

-- Tabla de tenants (organizaciones)
CREATE TABLE IF NOT EXISTS public.tenants (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Tabla de configuraciones por tenant
CREATE TABLE IF NOT EXISTS public.tenant_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT tenant_config_unique UNIQUE (tenant_id, key)
);

-- Tabla de estadísticas de uso por tenant
CREATE TABLE IF NOT EXISTS ai.tenant_stats (
    tenant_id UUID PRIMARY KEY REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    token_usage INTEGER DEFAULT 0,
    embedding_token_usage INTEGER DEFAULT 0,
    llm_tokens INTEGER DEFAULT 0,
    embedding_tokens INTEGER DEFAULT 0,
    fine_tuning_tokens INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    vector_count INTEGER DEFAULT 0,
    knowledge_base_count INTEGER DEFAULT 0,
    agent_count INTEGER DEFAULT 0,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ===========================================
-- PARTE 4: TABLAS DE TRACKING DE TOKENS
-- ===========================================

-- Tabla diaria de uso de tokens más detallada
CREATE TABLE IF NOT EXISTS ai.daily_token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    token_type ai.token_type NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    operation ai.operation_type,
    model TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT daily_token_usage_unique UNIQUE (tenant_id, date, token_type, operation, model)
);

-- Crear índices para consultas eficientes
CREATE INDEX IF NOT EXISTS idx_daily_token_usage_tenant ON ai.daily_token_usage(tenant_id);
CREATE INDEX IF NOT EXISTS idx_daily_token_usage_date ON ai.daily_token_usage(date);
CREATE INDEX IF NOT EXISTS idx_daily_token_usage_type ON ai.daily_token_usage(token_type);
CREATE INDEX IF NOT EXISTS idx_daily_token_usage_model ON ai.daily_token_usage(model);

-- Tabla de resumen mensual para consultas rápidas de facturación
CREATE TABLE IF NOT EXISTS ai.monthly_token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    year_month TEXT NOT NULL, -- formato 'YYYY-MM'
    token_type ai.token_type NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT monthly_token_usage_unique UNIQUE (tenant_id, year_month, token_type)
);

-- Crear índices para consultas eficientes
CREATE INDEX IF NOT EXISTS idx_monthly_token_usage_tenant ON ai.monthly_token_usage(tenant_id);
CREATE INDEX IF NOT EXISTS idx_monthly_token_usage_yearmonth ON ai.monthly_token_usage(year_month);
CREATE INDEX IF NOT EXISTS idx_monthly_token_usage_type ON ai.monthly_token_usage(token_type);

-- Tabla para control de idempotencia de tokens
CREATE TABLE IF NOT EXISTS ai.token_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    tokens INTEGER NOT NULL,
    token_type ai.token_type NOT NULL,
    operation ai.operation_type,
    model TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Crear índices para expiración y limpieza
CREATE INDEX IF NOT EXISTS idx_token_idempotency_created 
ON ai.token_idempotency(created_at);

CREATE INDEX IF NOT EXISTS idx_token_idempotency_tenant 
ON ai.token_idempotency(tenant_id);

-- Inicialización de tablas y default data pueden ir en secciones posteriores