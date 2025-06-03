-- ===========================================
-- FASE 2: IMPLEMENTACIÓN DE IDEMPOTENCIA
-- ===========================================

-- Crear tabla para control de idempotencia
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

-- Crear función para limpieza automática de registros antiguos
CREATE OR REPLACE FUNCTION ai.cleanup_token_idempotency()
RETURNS INTEGER AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM ai.token_idempotency 
    WHERE created_at < NOW() - INTERVAL '24 hours'
    RETURNING COUNT(*) INTO v_deleted;
    
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql;

-- Crear trabajo programado para limpieza diaria (si existe la extensión pg_cron)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'cleanup-token-idempotency',
            '0 3 * * *',  -- 3 AM todos los días
            $$SELECT ai.cleanup_token_idempotency()$$
        );
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_cron no disponible, la limpieza deberá configurarse de otra manera';
END $$;

-- ===========================================
-- FASE 3: PROCEDIMIENTO UNIFICADO
-- ===========================================

-- Función unificada para tracking de tokens
CREATE OR REPLACE FUNCTION ai.track_token_usage(
    p_tenant_id UUID,
    p_tokens INTEGER,
    p_token_type ai.token_type DEFAULT 'llm'::ai.token_type,
    p_operation ai.operation_type DEFAULT NULL,
    p_model TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb,
    p_idempotency_key TEXT DEFAULT NULL,
    p_agent_id UUID DEFAULT NULL,
    p_conversation_id UUID DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    already_processed BOOLEAN;
    v_model TEXT;
    v_operation ai.operation_type;
    v_owner_tenant_id UUID;
BEGIN
    -- Validaciones básicas
    IF p_tokens <= 0 THEN
        RETURN TRUE; -- No hay tokens para contabilizar
    END IF;
    
    -- Normalizar valores para evitar NULL en campos importantes
    v_model := COALESCE(p_model, 'unknown');
    v_operation := COALESCE(p_operation, 'query'::ai.operation_type);
    
    -- Verificar y resolver tenant propietario (para casos de agentes compartidos)
    IF p_agent_id IS NOT NULL THEN
        -- Intentar determinar el verdadero propietario del agente
        SELECT tenant_id INTO v_owner_tenant_id
        FROM ai.agent_configs
        WHERE agent_id = p_agent_id;
        
        -- Si el agente existe y tiene un propietario diferente,
        -- usar ese tenant_id para la atribución de tokens
        IF v_owner_tenant_id IS NOT NULL AND v_owner_tenant_id != p_tenant_id THEN
            -- Registrar la atribución en metadatos
            p_metadata := p_metadata || jsonb_build_object(
                'attribution', jsonb_build_object(
                    'requester_tenant_id', p_tenant_id,
                    'owner_tenant_id', v_owner_tenant_id,
                    'agent_id', p_agent_id
                )
            );
            
            -- Usar el tenant propietario para la contabilización
            p_tenant_id := v_owner_tenant_id;
        END IF;
    END IF;
    
    -- Verificar idempotencia si se proporciona clave
    IF p_idempotency_key IS NOT NULL THEN
        SELECT EXISTS(
            SELECT 1 FROM ai.token_idempotency 
            WHERE idempotency_key = p_idempotency_key
            AND created_at > NOW() - INTERVAL '24 hours'
        ) INTO already_processed;
        
        IF already_processed THEN
            RETURN TRUE; -- Ya se procesó esta operación
        END IF;
    END IF;
    
    -- Actualizar estadísticas en tenant_stats (mantener retrocompatibilidad)
    IF p_token_type = 'llm'::ai.token_type THEN
        -- Actualizar contadores LLM
        UPDATE ai.tenant_stats 
        SET 
            token_usage = token_usage + p_tokens,
            llm_tokens = llm_tokens + p_tokens,
            last_activity = NOW()
        WHERE tenant_id = p_tenant_id;
    ELSIF p_token_type = 'embedding'::ai.token_type THEN
        -- Actualizar contadores de embedding
        UPDATE ai.tenant_stats 
        SET 
            embedding_token_usage = embedding_token_usage + p_tokens,
            embedding_tokens = embedding_tokens + p_tokens,
            last_activity = NOW()
        WHERE tenant_id = p_tenant_id;
    ELSIF p_token_type = 'fine_tuning'::ai.token_type THEN
        -- Actualizar contadores de fine tuning
        UPDATE ai.tenant_stats 
        SET 
            fine_tuning_tokens = fine_tuning_tokens + p_tokens,
            last_activity = NOW()
        WHERE tenant_id = p_tenant_id;
    END IF;
    
    -- Si no existe el registro, crearlo
    IF NOT FOUND THEN
        INSERT INTO ai.tenant_stats (
            tenant_id, 
            token_usage, 
            embedding_token_usage,
            llm_tokens,
            embedding_tokens,
            fine_tuning_tokens,
            last_activity
        )
        VALUES (
            p_tenant_id, 
            CASE WHEN p_token_type = 'llm'::ai.token_type THEN p_tokens ELSE 0 END,
            CASE WHEN p_token_type = 'embedding'::ai.token_type THEN p_tokens ELSE 0 END,
            CASE WHEN p_token_type = 'llm'::ai.token_type THEN p_tokens ELSE 0 END,
            CASE WHEN p_token_type = 'embedding'::ai.token_type THEN p_tokens ELSE 0 END,
            CASE WHEN p_token_type = 'fine_tuning'::ai.token_type THEN p_tokens ELSE 0 END,
            NOW()
        );
    END IF;
    
    -- Enriquecer metadatos con información contextual
    p_metadata := p_metadata || jsonb_build_object(
        'tracking_timestamp', extract(epoch from now()),
        'agent_id', p_agent_id,
        'conversation_id', p_conversation_id
    );
    
    -- Registrar en la tabla detallada de uso diario
    BEGIN
        INSERT INTO ai.daily_token_usage (
            tenant_id,
            token_type,
            tokens,
            operation,
            model,
            metadata
        )
        VALUES (
            p_tenant_id,
            p_token_type,
            p_tokens,
            v_operation,
            v_model,
            p_metadata
        )
        ON CONFLICT (tenant_id, date, token_type, operation, model)
        DO UPDATE SET
            tokens = ai.daily_token_usage.tokens + p_tokens,
            metadata = ai.daily_token_usage.metadata || p_metadata,
            updated_at = NOW();
            
        -- El trigger update_monthly_stats se encargará de actualizar
        -- automáticamente la tabla monthly_token_usage
    EXCEPTION WHEN OTHERS THEN
        -- En caso de error, intentar una inserción más básica
        INSERT INTO ai.daily_token_usage (
            tenant_id,
            token_type,
            tokens,
            metadata
        )
        VALUES (
            p_tenant_id,
            p_token_type,
            p_tokens,
            jsonb_build_object('error_recovery', true)
        )
        ON CONFLICT (tenant_id, date, token_type, operation, model)
        DO UPDATE SET
            tokens = ai.daily_token_usage.tokens + p_tokens,
            updated_at = NOW();
    END;
    
    -- Registrar idempotencia si se proporcionó clave
    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO ai.token_idempotency (
            idempotency_key,
            tenant_id,
            tokens,
            token_type,
            operation,
            model,
            metadata
        )
        VALUES (
            p_idempotency_key,
            p_tenant_id,
            p_tokens,
            p_token_type,
            v_operation,
            v_model,
            p_metadata
        );
    END IF;
    
    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    -- Registrar error pero no fallar la transacción
    RAISE NOTICE 'Error en track_token_usage: %', SQLERRM;
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Función wrapper para mantener compatibilidad con el código existente
CREATE OR REPLACE FUNCTION ai.increment_token_usage(p_tenant_id UUID, p_tokens INTEGER)
RETURNS VOID AS $$
BEGIN
    PERFORM ai.track_token_usage(
        p_tenant_id := p_tenant_id,
        p_tokens := p_tokens,
        p_token_type := 'llm'::ai.token_type
    );
END;
$$ LANGUAGE plpgsql;

-- Función wrapper para mantener compatibilidad con el código existente
CREATE OR REPLACE FUNCTION ai.increment_embedding_token_usage(p_tenant_id UUID, p_tokens INTEGER)
RETURNS VOID AS $$
BEGIN
    PERFORM ai.track_token_usage(
        p_tenant_id := p_tenant_id,
        p_tokens := p_tokens,
        p_token_type := 'embedding'::ai.token_type
    );
END;
$$ LANGUAGE plpgsql;
