-- =============================================
-- TOKEN_TRACKING_UPGRADE.SQL - MEJORAS AL SISTEMA DE TRACKING DE TOKENS
-- =============================================
-- Este archivo implementa mejoras para el sistema de tracking de tokens,
-- incluyendo estandarización de tipos, idempotencia y procedimientos unificados.
-- Fecha: 2025-05-08
-- ===========================================

-- ===========================================
-- FASE 1: ESTANDARIZACIÓN DE TIPOS
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

-- Crear una tabla diaria de uso de tokens más detallada
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

-- Crear una tabla de resumen mensual para consultas rápidas de facturación
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

-- Actualizar tenant_stats para alinearlo con los nuevos tipos
ALTER TABLE ai.tenant_stats 
ADD COLUMN IF NOT EXISTS llm_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS embedding_tokens INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS fine_tuning_tokens INTEGER DEFAULT 0;

-- Migrar datos existentes si hay
DO $$
BEGIN
    -- Migrar token_usage a llm_tokens si existen
    UPDATE ai.tenant_stats 
    SET llm_tokens = token_usage 
    WHERE token_usage > 0 AND llm_tokens = 0;
    
    -- Migrar embedding_token_usage a embedding_tokens si existen
    UPDATE ai.tenant_stats 
    SET embedding_tokens = embedding_token_usage 
    WHERE embedding_token_usage > 0 AND embedding_tokens = 0;
END
$$;

-- Crear función para actualizar automáticamente las estadísticas mensuales
CREATE OR REPLACE FUNCTION ai.update_monthly_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Insertar o actualizar resumen mensual
    INSERT INTO ai.monthly_token_usage (
        tenant_id, year_month, token_type, tokens, metadata
    )
    VALUES (
        NEW.tenant_id,
        to_char(NEW.date, 'YYYY-MM'),
        NEW.token_type,
        NEW.tokens,
        jsonb_build_object('last_update', NOW(), 'source', 'daily_update')
    )
    ON CONFLICT (tenant_id, year_month, token_type)
    DO UPDATE SET
        tokens = ai.monthly_token_usage.tokens + NEW.tokens,
        metadata = ai.monthly_token_usage.metadata || 
                  jsonb_build_object('last_update', NOW()),
        updated_at = NOW();
        
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Crear trigger para actualización automática
DROP TRIGGER IF EXISTS trg_update_monthly_stats ON ai.daily_token_usage;
CREATE TRIGGER trg_update_monthly_stats
AFTER INSERT ON ai.daily_token_usage
FOR EACH ROW
EXECUTE FUNCTION ai.update_monthly_stats();
