-- =============================================
-- INIT_3_TOKEN_FUNCTIONS.SQL - FUNCIONES PARA CONTABILIZACIÓN DE TOKENS
-- =============================================
-- Este archivo define las funciones unificadas para tracking de tokens,
-- incluyendo contabilización, idempotencia, y consulta.
-- Fecha: 2025-05-08

-- ===========================================
-- PARTE 1: FUNCIONES AUXILIARES Y TRIGGERS
-- ===========================================

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
-- PARTE 2: FUNCIONES PRINCIPALES DE TRACKING
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

-- ===========================================
-- PARTE 3: FUNCIONES DE COMPATIBILIDAD
-- ===========================================

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

-- ===========================================
-- PARTE 4: FUNCIONES DE CONSULTA
-- ===========================================

-- Función que retorna las estadísticas de tokens (total, LLM y embedding)
CREATE OR REPLACE FUNCTION ai.get_token_stats(p_tenant_id UUID)
RETURNS TABLE (
    token_usage INTEGER,
    embedding_token_usage INTEGER,
    llm_tokens INTEGER,
    embedding_tokens INTEGER,
    fine_tuning_tokens INTEGER,
    total_token_usage INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(ts.token_usage, 0) as token_usage,
        COALESCE(ts.embedding_token_usage, 0) as embedding_token_usage,
        COALESCE(ts.llm_tokens, 0) as llm_tokens,
        COALESCE(ts.embedding_tokens, 0) as embedding_tokens,
        COALESCE(ts.fine_tuning_tokens, 0) as fine_tuning_tokens,
        COALESCE(ts.llm_tokens, 0) + COALESCE(ts.embedding_tokens, 0) + COALESCE(ts.fine_tuning_tokens, 0) as total_token_usage
    FROM ai.tenant_stats ts
    WHERE ts.tenant_id = p_tenant_id;
END;
$$;

-- Función para obtener estadísticas de tokens por período
CREATE OR REPLACE FUNCTION ai.get_token_usage_stats(
    tenant_id UUID,
    period TEXT DEFAULT 'daily',
    start_date DATE DEFAULT (CURRENT_DATE - INTERVAL '30 days')::DATE,
    end_date DATE DEFAULT CURRENT_DATE
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    result JSONB;
BEGIN
    IF period = 'daily' THEN
        WITH stats AS (
            SELECT 
                date,
                token_type::TEXT,
                SUM(tokens) as tokens
            FROM ai.daily_token_usage
            WHERE tenant_id = $1
            AND date BETWEEN start_date AND end_date
            GROUP BY date, token_type
            ORDER BY date
        )
        SELECT jsonb_build_object(
            'period', 'daily',
            'tenant_id', tenant_id,
            'stats', jsonb_object_agg(date, token_data)
        ) INTO result
        FROM (
            SELECT 
                date,
                jsonb_object_agg(token_type, tokens) as token_data
            FROM stats
            GROUP BY date
        ) t;
        
        -- Si no hay datos, devolver estructura vacía
        IF result IS NULL THEN
            result := jsonb_build_object(
                'period', 'daily',
                'tenant_id', tenant_id,
                'stats', '{}'::jsonb
            );
        END IF;
        
    ELSIF period = 'monthly' THEN
        WITH stats AS (
            SELECT 
                year_month,
                token_type::TEXT,
                tokens
            FROM ai.monthly_token_usage
            WHERE tenant_id = $1
            AND year_month BETWEEN to_char(start_date, 'YYYY-MM') AND to_char(end_date, 'YYYY-MM')
            ORDER BY year_month
        )
        SELECT jsonb_build_object(
            'period', 'monthly',
            'tenant_id', tenant_id,
            'stats', jsonb_object_agg(year_month, token_data)
        ) INTO result
        FROM (
            SELECT 
                year_month,
                jsonb_object_agg(token_type, tokens) as token_data
            FROM stats
            GROUP BY year_month
        ) t;
        
        -- Si no hay datos, devolver estructura vacía
        IF result IS NULL THEN
            result := jsonb_build_object(
                'period', 'monthly',
                'tenant_id', tenant_id,
                'stats', '{}'::jsonb
            );
        END IF;
    ELSE
        -- Período no soportado
        result := jsonb_build_object(
            'error', 'Período no soportado. Use "daily" o "monthly".',
            'period', period,
            'tenant_id', tenant_id,
            'stats', '{}'::jsonb
        );
    END IF;
    
    RETURN result;
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object(
        'error', SQLERRM,
        'period', period,
        'tenant_id', tenant_id,
        'stats', '{}'::jsonb
    );
END;
$$;

-- Función para obtener el propietario de un agente (para token accounting)
CREATE OR REPLACE FUNCTION ai.get_agent_owner(p_agent_id UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_owner_tenant_id UUID;
BEGIN
    SELECT tenant_id INTO v_owner_tenant_id
    FROM ai.agent_configs
    WHERE agent_id = p_agent_id;
    
    RETURN v_owner_tenant_id;
END;
$$;
