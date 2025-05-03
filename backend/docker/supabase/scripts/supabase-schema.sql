-- Schema para sistema RAG con soporte multitenancy
-- Adaptado para el patrón cache-aside y sistema de embebidos

-- Las extensiones ya se han configurado en setup.sh

-- Tabla de tenants
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    tier VARCHAR(50) NOT NULL DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}'::jsonb
);

-- Insertar tenant por defecto
INSERT INTO public.tenants (tenant_id, name, tier) 
VALUES ('default', 'Default Tenant', 'free')
ON CONFLICT (tenant_id) DO NOTHING;

-- Tabla de colecciones
CREATE TABLE IF NOT EXISTS public.collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    collection_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}'::jsonb,
    UNIQUE(tenant_id, collection_id)
);

-- Tabla de documentos
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    collection_id VARCHAR(255) NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    title VARCHAR(512),
    content TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(tenant_id, collection_id, document_id),
    FOREIGN KEY (tenant_id, collection_id) REFERENCES public.collections(tenant_id, collection_id)
);

-- Tabla de chunks de documentos (para embeddings)
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    collection_id VARCHAR(255) NOT NULL,
    document_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(1536), -- Ajustar dimensión según modelo
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, collection_id, chunk_id),
    FOREIGN KEY (tenant_id, collection_id, document_id) REFERENCES public.documents(tenant_id, collection_id, document_id) ON DELETE CASCADE
);

-- Tabla para tracking de uso de tokens
CREATE TABLE IF NOT EXISTS public.token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    agent_id VARCHAR(255),
    conversation_id VARCHAR(255),
    collection_id VARCHAR(255),
    token_type VARCHAR(50) NOT NULL, -- 'llm', 'embedding', 'fine_tuning'
    operation VARCHAR(50) NOT NULL, -- 'query', 'ingestion', etc.
    model VARCHAR(255) NOT NULL,
    tokens INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para configuraciones de agentes
CREATE TABLE IF NOT EXISTS public.agent_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    agent_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    instructions TEXT,
    model VARCHAR(255) NOT NULL,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(tenant_id, agent_id)
);

-- Tabla para métricas de caché
CREATE TABLE IF NOT EXISTS public.cache_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES public.tenants(tenant_id),
    agent_id VARCHAR(255),
    data_type VARCHAR(50) NOT NULL, -- 'embedding', 'query_result', etc.
    metric_type VARCHAR(50) NOT NULL, -- 'cache_hit', 'cache_miss', etc.
    value NUMERIC NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para búsqueda eficiente
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_collection 
ON public.document_chunks(tenant_id, collection_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_content_hash 
ON public.document_chunks(content_hash);

CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_date 
ON public.token_usage(tenant_id, timestamp);

-- Índice para búsqueda vectorial (más eficiente)
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_cosine 
ON public.document_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Funciones para búsqueda vectorial por similitud
CREATE OR REPLACE FUNCTION search_documents(
    p_tenant_id VARCHAR(255),
    p_collection_id VARCHAR(255),
    p_embedding vector,
    p_limit INTEGER DEFAULT 4
)
RETURNS TABLE (
    chunk_id VARCHAR(255),
    document_id VARCHAR(255),
    content TEXT,
    metadata JSONB,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.chunk_id,
        dc.document_id,
        dc.content,
        dc.metadata,
        1 - (dc.embedding <=> p_embedding) AS similarity
    FROM 
        public.document_chunks dc
    WHERE 
        dc.tenant_id = p_tenant_id
        AND dc.collection_id = p_collection_id
    ORDER BY 
        dc.embedding <=> p_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;
