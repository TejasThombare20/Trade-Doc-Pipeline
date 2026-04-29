-- Jobs: a user-initiated upload bundle. One job groups N trade documents
-- that share a rule book and are processed sequentially after the user
-- clicks "Start processing". Rule books are NOT part of any job.

CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rule_book_id    UUID NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    status          TEXT NOT NULL CHECK (status IN (
                        'pending', 'processing', 'completed',
                        'partial_failure', 'failed'
                    )),
    document_count  INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_tenant ON jobs(tenant_id, created_at DESC);
CREATE INDEX idx_jobs_tenant_active ON jobs(tenant_id, is_active);

-- Add job_id to documents. Nullable: rule books have no job.
ALTER TABLE documents ADD COLUMN job_id UUID REFERENCES jobs(id) ON DELETE CASCADE;
CREATE INDEX idx_documents_job ON documents(job_id);

-- Backfill: every existing trade document becomes its own one-doc job.
-- Rule books are skipped (job_id stays NULL).
DO $$
DECLARE
    doc RECORD;
    new_job_id UUID;
    rb_id UUID;
BEGIN
    FOR doc IN
        SELECT id, tenant_id, status, created_at
        FROM documents
        WHERE type = 'document' AND job_id IS NULL
    LOOP
        -- Pick any rule book for this tenant (active first, then any).
        SELECT id INTO rb_id
        FROM documents
        WHERE tenant_id = doc.tenant_id AND type = 'rule_book'
        ORDER BY is_active DESC, created_at DESC
        LIMIT 1;

        -- Skip orphans: a doc whose tenant has no rule book at all.
        IF rb_id IS NULL THEN
            CONTINUE;
        END IF;

        INSERT INTO jobs (tenant_id, rule_book_id, status, document_count, started_at, completed_at, created_at, updated_at)
        VALUES (
            doc.tenant_id,
            rb_id,
            CASE
                WHEN doc.status = 'completed' THEN 'completed'
                WHEN doc.status = 'failed' THEN 'failed'
                ELSE 'processing'
            END,
            1,
            doc.created_at,
            CASE WHEN doc.status IN ('completed', 'failed') THEN doc.created_at ELSE NULL END,
            doc.created_at,
            doc.created_at
        )
        RETURNING id INTO new_job_id;

        UPDATE documents SET job_id = new_job_id WHERE id = doc.id;
    END LOOP;
END $$;
