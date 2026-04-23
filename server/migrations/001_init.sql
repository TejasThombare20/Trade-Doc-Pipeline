-- Nova trade-doc pipeline: initial multi-tenant schema.
-- Every tenant-scoped table carries tenant_id; queries must filter on it.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tenants: the isolation boundary. One company using the platform = one tenant.
-- Auth is tenant-level (no users table); a session carries tenant_id + role.
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Customers are the tenant's end-customers. Rule-book documents belong to a customer.
CREATE TABLE customers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    code            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);
CREATE INDEX idx_customers_tenant ON customers(tenant_id);


-- Unified documents table: both trade documents and rule-book PDFs.
-- type distinguishes them; extracted_rules is only populated for rule_book.
-- session_id links this document to its pipeline_sessions row.
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    session_id      UUID,
    type            TEXT NOT NULL CHECK (type IN ('document', 'rule_book')),
    storage_key     TEXT NOT NULL,
    original_name   TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    doc_type        TEXT,
    status          TEXT NOT NULL CHECK (status IN (
                        'uploaded', 'preprocessing', 'extracting',
                        'validating', 'deciding', 'completed', 'failed'
                    )),
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    extracted_rules JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_tenant_customer ON documents(tenant_id, customer_id);
CREATE INDEX idx_documents_tenant_type ON documents(tenant_id, type);
CREATE INDEX idx_documents_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_created ON documents(tenant_id, created_at DESC);
CREATE INDEX idx_documents_session ON documents(session_id);

-- Only one active rule_book per (tenant, customer).
CREATE UNIQUE INDEX idx_documents_one_active_rule_book
    ON documents(tenant_id, customer_id)
    WHERE type = 'rule_book' AND is_active = TRUE;

-- Pipeline session: the rollup across all steps of one agentic run.
-- One row per (document, attempt). pipeline_status reflects the session as a whole.

CREATE TABLE pipeline_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN ('document', 'rule_book')),
    pipeline_status TEXT NOT NULL CHECK (pipeline_status IN ('pending', 'success', 'fail')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    total_tokens_in INTEGER NOT NULL DEFAULT 0,
    total_tokens_out INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pipeline_sessions_document ON pipeline_sessions(document_id);
CREATE INDEX idx_pipeline_sessions_tenant ON pipeline_sessions(tenant_id, started_at DESC);

-- Per-step audit log. One row per step attempt; retries write new rows.
-- step_type: parsing (library-based, mode='manual', tokens NULL)
--            extraction | validation | decision (LLM, mode='llm')
-- response: step-specific payload — parser output for parsing, raw LLM response for LLM steps.
CREATE TABLE pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES pipeline_sessions(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN ('document', 'rule_book')),
    step_type       TEXT NOT NULL CHECK (step_type IN ('parsing', 'extraction', 'validation', 'decision')),
    mode            TEXT NOT NULL CHECK (mode IN ('manual', 'llm')),
    status          TEXT NOT NULL CHECK (status IN ('pending', 'success', 'fail')),
    response        JSONB,
    total_tokens_in INTEGER,
    total_tokens_out INTEGER,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pipeline_runs_session ON pipeline_runs(session_id, started_at);
CREATE INDEX idx_pipeline_runs_document ON pipeline_runs(document_id);
CREATE INDEX idx_pipeline_runs_tenant ON pipeline_runs(tenant_id, started_at DESC);

-- Extractor output: LLM tool call + processed result. Outcome/fields derived from tool_output in code.
CREATE TABLE extractions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES pipeline_sessions(id) ON DELETE CASCADE,
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    tool_content    JSONB NOT NULL,
    tool_output     JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_extractions_document ON extractions(document_id);
CREATE INDEX idx_extractions_session ON extractions(session_id);

-- Validator output.
CREATE TABLE validations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES pipeline_sessions(id) ON DELETE CASCADE,
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    tool_content    JSONB NOT NULL,
    tool_output     JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_validations_document ON validations(document_id);
CREATE INDEX idx_validations_session ON validations(session_id);

-- Router/decision output.
CREATE TABLE decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    session_id      UUID NOT NULL REFERENCES pipeline_sessions(id) ON DELETE CASCADE,
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    tool_content    JSONB NOT NULL,
    tool_output     JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_decisions_document ON decisions(document_id);
CREATE INDEX idx_decisions_session ON decisions(session_id);

-- NOTE: schema_migrations table is created by the migration runner itself (migrate.py).
