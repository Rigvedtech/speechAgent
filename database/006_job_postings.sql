-- Job openings / positions created by recruiters (source of truth for job title).

CREATE TABLE job_postings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES organization (id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    job_title           VARCHAR(255) NOT NULL,
    jd_text             TEXT,
    jd_document_id      UUID REFERENCES documents (id) ON DELETE SET NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'open',
    continue_threshold  NUMERIC(4, 2) NOT NULL DEFAULT 5.50,
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT job_postings_status_valid CHECK (
        status IN ('draft', 'open', 'closed', 'filled')
    ),
    CONSTRAINT job_postings_title_nonempty CHECK (LENGTH(TRIM(job_title)) >= 2),
    CONSTRAINT job_postings_jd_min_len CHECK (
        jd_text IS NULL OR LENGTH(TRIM(jd_text)) >= 100
    )
);

CREATE INDEX idx_job_postings_organization ON job_postings (organization_id);
CREATE INDEX idx_job_postings_created_by ON job_postings (created_by);
CREATE INDEX idx_job_postings_status ON job_postings (organization_id, status)
    WHERE is_active = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_job_postings_title_trgm ON job_postings
    USING GIN (job_title gin_trgm_ops);

ALTER TABLE document_extractions
    ADD CONSTRAINT document_extractions_job_posting_id_fkey
    FOREIGN KEY (job_posting_id) REFERENCES job_postings (id) ON DELETE SET NULL;

CREATE INDEX idx_document_extractions_job_posting ON document_extractions (job_posting_id);

COMMENT ON TABLE job_postings IS 'Recruiter-owned job requisitions; interview sessions link here for title search and reporting.';
COMMENT ON COLUMN job_postings.continue_threshold IS 'Minimum rolling average to continue interview for this role.';
