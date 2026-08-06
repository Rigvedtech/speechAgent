-- Bulk JD or CV upload jobs and per-file items.

CREATE TABLE IF NOT EXISTS upload_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    batch_type      VARCHAR(10) NOT NULL,
    job_posting_id  UUID REFERENCES job_postings (id) ON DELETE SET NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'queued',
    total_count     INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    fail_count      INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT upload_batches_type_valid CHECK (batch_type IN ('jd', 'cv')),
    CONSTRAINT upload_batches_status_valid CHECK (
        status IN ('queued', 'processing', 'done', 'failed', 'cancelled')
    ),
    CONSTRAINT upload_batches_counts_nonneg CHECK (
        total_count >= 0 AND success_count >= 0 AND fail_count >= 0
    ),
    CONSTRAINT upload_batches_cv_requires_job CHECK (
        batch_type <> 'cv' OR job_posting_id IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS upload_batch_items (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id          UUID NOT NULL REFERENCES upload_batches (id) ON DELETE CASCADE,
    original_filename VARCHAR(512),
    storage_path      TEXT,
    mime_type         VARCHAR(127),
    file_size_bytes   BIGINT,
    status            VARCHAR(20) NOT NULL DEFAULT 'queued',
    document_id       UUID REFERENCES documents (id) ON DELETE SET NULL,
    candidate_id      UUID REFERENCES candidates (id) ON DELETE SET NULL,
    job_posting_id    UUID REFERENCES job_postings (id) ON DELETE SET NULL,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,

    CONSTRAINT upload_batch_items_status_valid CHECK (
        status IN ('queued', 'processing', 'ready', 'failed', 'skipped')
    )
);

CREATE INDEX IF NOT EXISTS idx_upload_batches_org ON upload_batches (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_upload_batches_status ON upload_batches (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_upload_batches_job ON upload_batches (job_posting_id)
    WHERE job_posting_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_upload_batch_items_batch ON upload_batch_items (batch_id, status);
CREATE INDEX IF NOT EXISTS idx_upload_batch_items_document ON upload_batch_items (document_id)
    WHERE document_id IS NOT NULL;

COMMENT ON TABLE upload_batches IS
    'Bulk JD or CV upload job; CV batches must reference job_posting_id.';
COMMENT ON COLUMN upload_batches.batch_type IS
    'jd = create requirements from files; cv = attach resumes under selected JD.';
COMMENT ON TABLE upload_batch_items IS
    'One uploaded file within a batch; tracks pipeline status to documents/candidates.';
